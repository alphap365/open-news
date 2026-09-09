import re
from typing import Dict, List, Optional

# Matches word-like tokens (letters, digits, underscore) across scripts;
# \b already works reasonably well for Latin-script terms which covers
# the vast majority of real-world queries.
_WORD_CHARS = re.compile(r"\w+", re.UNICODE)


def _boundary_pattern(term: str) -> re.Pattern:
    escaped = re.escape(term.strip())
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE | re.UNICODE)


def _field_text(article: Dict, search_in: List[str]) -> str:
    parts = []
    if "title" in search_in:
        parts.append(article.get("title", ""))
    if "description" in search_in:
        parts.append(article.get("description", ""))
    if "body" in search_in:
        parts.append(article.get("text", ""))
    return " ".join(p for p in parts if p)


def matches_query(article: Dict, query: str, query_mode: str, search_in: List[str]) -> bool:
    """
    Check whether an article's searchable text satisfies the query under
    the given mode. Used as a secondary confirmation filter after the
    engine's own search — engines can be loose about matching, this is
    the precise word-boundary check.
    """
    text = _field_text(article, search_in)
    if not text:
        return True  # nothing to check against; don't punish missing fields

    if query_mode == "exact_phrase":
        pattern = _boundary_pattern(query)
        return bool(pattern.search(text))

    terms = [t for t in _WORD_CHARS.findall(query)]
    if not terms:
        return True

    if query_mode == "all":
        return all(_boundary_pattern(t).search(text) for t in terms)

    # "any" (default)
    return any(_boundary_pattern(t).search(text) for t in terms)


def excludes_terms(article: Dict, exclude_terms: Optional[List[str]], search_in: List[str]) -> bool:
    """True if the article does NOT contain any of the excluded terms
    (i.e. it passes the exclusion filter)."""
    if not exclude_terms:
        return True
    text = _field_text(article, search_in)
    if not text:
        return True
    return not any(_boundary_pattern(t).search(text) for t in exclude_terms)


def filter_articles(
    articles: List[Dict],
    query: Optional[str] = None,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    search_in: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Apply query_mode + exclude_terms filtering. `query` is optional because
    fetch() (category/location based) has no query to re-check — only
    exclude_terms applies there.
    """
    search_in = search_in or ["title", "description"]
    kept = []
    for art in articles:
        if query and not matches_query(art, query, query_mode, search_in):
            continue
        if not excludes_terms(art, exclude_terms, search_in):
            continue
        kept.append(art)
    return kept
