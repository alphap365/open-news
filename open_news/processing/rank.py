"""Relevance ranking: BM25 (bm25s) > TF-IDF > term-frequency.

Every method writes a numeric ``_rank_score`` onto each article and
returns the list re-sorted by it. Mutates in place, matching
ranker.sort_articles().
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional

from ..utils.textutil import nfc

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_METHODS = {"auto", "bm25", "tfidf", "basic"}
_DEFAULT_SEARCH_IN = ("title", "description", "text")


def _article_text(article: Dict, search_in: Iterable[str]) -> str:
    parts = []
    for field in search_in:
        val = article.get(field)
        if isinstance(val, str) and val:
            parts.append(val)
    return nfc(" ".join(parts))


def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1]


def _score_basic(texts: List[str], query_tokens: List[str]) -> List[float]:
    if not query_tokens:
        return [0.0] * len(texts)
    qset = set(query_tokens)
    return [
        float(sum(Counter(t for t in _tokenize(text) if t in qset).values()))
        for text in texts
    ]


def _score_tfidf(texts: List[str], query_tokens: List[str]) -> List[float]:
    n = len(texts)
    if n == 0 or not query_tokens:
        return [0.0] * n
    tokenized = [_tokenize(t) for t in texts]
    df: Counter = Counter()
    for toks in tokenized:
        df.update(set(toks))
    qset = set(query_tokens)
    scores: List[float] = []
    for toks in tokenized:
        if not toks:
            scores.append(0.0)
            continue
        tf = Counter(toks)
        total = len(toks)
        s = 0.0
        for q in qset:
            if q in tf:
                idf = math.log((1 + n) / (1 + df.get(q, 0))) + 1.0
                s += (tf[q] / total) * idf
        scores.append(s)
    return scores


def _score_bm25(texts: List[str], query_tokens: List[str]) -> Optional[List[float]]:
    """BM25 via bm25s. Returns None if the optional dep is missing or the
    call fails (version drift is common — always fall back, never raise)."""
    try:
        import bm25s
    except ImportError:
        return None
    try:
        corpus_tokens = bm25s.tokenize(texts)
        query_tokens_b = bm25s.tokenize([" ".join(query_tokens)])
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)
        results, scores = retriever.retrieve(query_tokens_b, k=len(texts))
        try:
            idxs = [int(x) for x in results[0]]
            scs = [float(x) for x in scores[0]]
        except (TypeError, IndexError):
            idxs = [int(x) for x in results]
            scs = [float(x) for x in scores]
        out = [0.0] * len(texts)
        for i, s in zip(idxs, scs):
            if 0 <= i < len(out):
                out[i] = s
        return out
    except Exception as e:
        logger.debug("bm25s ranking failed, falling back: %s", e)
        return None


def rank_articles(
    articles: List[Dict],
    query: Optional[str] = None,
    method: str = "auto",
    search_in: Optional[List[str]] = None,
    top_k: Optional[int] = None,
) -> List[Dict]:
    """Rank articles by relevance to `query`.

    method: 'auto' (default) | 'bm25' | 'tfidf' | 'basic'.
        'auto' tries BM25 (needs bm25s), falls back to TF-IDF transparently.
    If `query` is blank, articles gain a zero `_rank_score` and are
    returned unchanged (their existing order is preserved)."""
    if not articles:
        return []
    if method not in _METHODS:
        logger.warning("rank method=%r unknown; using 'auto'", method)
        method = "auto"

    if not query or not query.strip():
        for a in articles:
            a.setdefault("_rank_score", 0.0)
        return articles[:top_k] if top_k is not None else articles

    fields = search_in or list(_DEFAULT_SEARCH_IN)
    texts = [_article_text(a, fields) for a in articles]
    q_tokens = _tokenize(query)

    scores: Optional[List[float]] = None
    used = method
    if method in ("auto", "bm25"):
        scores = _score_bm25(texts, q_tokens)
        if scores is None:
            if method == "bm25":
                logger.warning("bm25s unavailable; falling back to tfidf")
            used = "tfidf"
    if scores is None and used in ("auto", "tfidf"):
        scores = _score_tfidf(texts, q_tokens)
        used = "tfidf"
    if scores is None:
        scores = _score_basic(texts, q_tokens)
        used = "basic"

    for a, s in zip(articles, scores):
        a["_rank_score"] = float(s)
    ranked = sorted(articles, key=lambda a: a.get("_rank_score", 0.0), reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]
    logger.info("Ranked %d articles with %s (query=%r)", len(ranked), used, query[:60])
    return ranked