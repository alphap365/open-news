import re
from functools import lru_cache
from typing import Dict, List, Optional, Union

from ..utils.textutil import WORD, nfc

# Whitespace-separated tokens, or "quoted phrases" kept whole.
_TOKEN_RE = re.compile(r'"([^"]+)"|(\S+)')
_HYPHENS = "-\u2010\u2011\u2012\u2013\u2014\u2015"
_EDGE_PUNCT = ".,;:!?()[]{}\"'"


def _query_terms(query: str) -> List[str]:
    terms = []
    for quoted, bare in _TOKEN_RE.findall(nfc(query)):
        term = (quoted or bare.strip(_EDGE_PUNCT)).strip()
        if term:
            terms.append(term)
    return terms


@lru_cache(maxsize=1024)
def _boundary_pattern(term: str) -> "re.Pattern":
    """Match `term` as a whole token. Lookarounds instead of ``\\b`` so terms
    that start/end with symbols ("C++", "$AAPL") and Indic words with
    combining marks behave. "covid-19" also matches "covid 19"."""
    def esc(t: str) -> str:
        return re.escape(t).replace(r"\ ", r"\s+")

    variants = {esc(term)}
    spaced = re.sub(f"[{_HYPHENS}]+", " ", term)
    if spaced != term:
        variants.add(esc(spaced))
    alt = "|".join(sorted(variants, key=len, reverse=True))
    return re.compile(rf"(?<!{WORD})(?:{alt})(?!{WORD})", re.IGNORECASE)


def _field_text(article: Dict, search_in: List[str]) -> str:
    parts = []
    if "title" in search_in:
        parts.append(article.get("title", ""))
    if "description" in search_in:
        parts.append(article.get("description", ""))
    if "body" in search_in:
        parts.append(article.get("text", ""))
    return nfc(" ".join(p for p in parts if p))


def matches_query(article: Dict, query: str, query_mode: str, search_in: List[str]) -> bool:
    """Precise word-boundary confirmation after the engine's own (looser) search."""
    text = _field_text(article, search_in)
    if not text:
        return True  # nothing to check against; don't punish missing fields

    if query_mode == "exact_phrase":
        phrase = nfc(query).strip().strip('"').strip()
        return bool(_boundary_pattern(phrase).search(text)) if phrase else True

    terms = _query_terms(query)
    if not terms:
        return True
    hits = (_boundary_pattern(t).search(text) for t in terms)
    return all(hits) if query_mode == "all" else any(hits)


def excludes_terms(article: Dict, exclude_terms: Optional[List[str]], search_in: List[str]) -> bool:
    """True if the article does NOT contain any excluded term."""
    if not exclude_terms:
        return True
    text = _field_text(article, search_in)
    if not text:
        return True
    for t in exclude_terms:
        t = nfc(t).strip().strip('"').strip()
        if t and _boundary_pattern(t).search(text):
            return False
    return True


def filter_articles(
    articles: List[Dict],
    query: Optional[str] = None,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    search_in: Optional[List[str]] = None,
    topic: Union[str, List[str], None] = None,
    topic_mode: str = "any",
) -> List[Dict]:
    """query + exclude_terms + topic filtering.

    `query` and `topic` are independent (ANDed). `topic` defaults to
    'any' semantics and matches category/keywords in addition to
    title/description/text."""
    search_in = search_in or ["title", "description"]
    kept = []
    for art in articles:
        if query and not matches_query(art, query, query_mode, search_in):
            continue
        if not excludes_terms(art, exclude_terms, search_in):
            continue
        if topic and not matches_topic(art, topic, topic_mode):
            continue
        kept.append(art)
    return kept

def _topic_terms(topic: Union[str, List[str], None]) -> List[str]:
    if not topic:
        return []
    if isinstance(topic, str):
        if "," in topic:
            return [t.strip() for t in topic.split(",") if t.strip()]
        return [topic.strip()]
    return [str(t).strip() for t in topic if t and str(t).strip()]


def _topic_text(article: Dict) -> str:
    parts = [
        article.get("title", ""),
        article.get("description", ""),
        article.get("text", ""),
        article.get("category", ""),
    ]
    kw = article.get("keywords")
    if isinstance(kw, list):
        parts.extend(str(k) for k in kw if k)
    elif isinstance(kw, str) and kw:
        parts.append(kw)
    return nfc(" ".join(p for p in parts if p))


def matches_topic(article: Dict, topic: Union[str, List[str], None],
                  topic_mode: str = "any") -> bool:
    """Topic filter — broader field coverage than matches_query()."""
    terms = _topic_terms(topic)
    if not terms:
        return True
    text = _topic_text(article)
    if not text:
        return True  # missing fields never penalized

    if topic_mode == "exact_phrase":
        phrase = nfc(" ".join(terms)).strip()
        return bool(_boundary_pattern(phrase).search(text)) if phrase else True

    hits = (_boundary_pattern(t).search(text) for t in terms)
    return all(hits) if topic_mode == "all" else any(hits)