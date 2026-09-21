"""Story clustering by title similarity.

Composes the existing pieces:
  * dedupe_articles()  — URL-level exact dedupe runs first
  * filter_articles()  — optional topic narrowing (feature 2)
  * rank_articles()    — optional per-article scoring (feature 3)

Unlike dedupe (which drops duplicates), clustering keeps every article
and labels which story it belongs to, so downstream code can show
"N sources reporting this" or rank by cluster size.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Union

from ..utils.textutil import normalize_title as _normalize_title
from .dedupe import dedupe_articles
from .ranker import _parse_date
from .token_filter import filter_articles

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.75


class _UnionFind:
    __slots__ = ("parent", "rank")

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _similar(a: str, b: str, threshold: float) -> bool:
    if not a or not b:
        return False
    sm = SequenceMatcher(None, a, b)
    if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
        return False
    return sm.ratio() >= threshold


def _cluster_score(members: List[Dict]) -> float:
    size = len(members)
    if size == 0:
        return 0.0
    newest = max((_parse_date(a) for a in members), default=None)
    if newest is not None and newest.tzinfo is not None and newest.year > 1:
        age_hours = max(0.0, (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0)
        recency = 1.0 / (1.0 + age_hours / 24.0)
    else:
        recency = 0.5
    rank_scores = [a["_rank_score"] for a in members
                   if isinstance(a.get("_rank_score"), (int, float))]
    mean_rank = sum(rank_scores) / len(rank_scores) if rank_scores else 0.0
    return math.log1p(size) * (0.5 + 0.5 * recency) + mean_rank


def _pick_representative(members: List[Dict]) -> Dict:
    def key(a: Dict):
        rs = a.get("_rank_score")
        rs = rs if isinstance(rs, (int, float)) else 0.0
        dt = _parse_date(a)
        try:
            ts = -dt.timestamp() if dt.year > 1 else 0.0
        except (OSError, OverflowError, ValueError):
            ts = 0.0
        text_len = len(a.get("text") or a.get("description") or "")
        return (-rs, ts, -text_len)
    return min(members, key=key)


def cluster_articles(
    articles: List[Dict],
    threshold: float = DEFAULT_THRESHOLD,
    min_cluster_size: int = 1,
    topic: Optional[Union[str, List[str]]] = None,
    topic_mode: str = "any",
    search_in: Optional[List[str]] = None,
    dedupe: bool = True,
    rank_query: Optional[str] = None,
    rank_method: str = "auto",
    sort_by: str = "score",
    drop_singletons: bool = False,
) -> List[Dict]:
    """Group articles into story clusters by title similarity.

    Args:
        threshold: 0..1 title-similarity cutoff. Higher = tighter.
        min_cluster_size: Drop clusters smaller than this.
        topic / topic_mode / search_in: Optional narrowing via feature 2.
        dedupe: Run exact URL-level dedupe first (default True).
        rank_query / rank_method: If `rank_query` given, run rank_articles()
            internally so representatives are chosen by relevance, not just
            earliest date.
        sort_by: 'score' (default) | 'size' | 'date'.
        drop_singletons: Convenience for min_cluster_size=2.

    Returns:
        List of cluster dicts: {id, label, topic, size, score, sources,
        first_seen, last_seen, representative, articles}.
    """
    if not articles:
        return []

    working = list(articles)
    if dedupe:
        working = dedupe_articles(working)
    if topic:
        working = filter_articles(
            working, topic=topic, topic_mode=topic_mode, search_in=search_in
        )
    if not working:
        return []

    if rank_query:
        from .rank import rank_articles
        working = rank_articles(
            working, query=rank_query, method=rank_method, search_in=search_in
        )

    titles = [_normalize_title(a.get("title", "")) for a in working]
    uf = _UnionFind(len(working))
    for i in range(len(working)):
        if not titles[i]:
            continue
        for j in range(i + 1, len(working)):
            if not titles[j]:
                continue
            if _similar(titles[i], titles[j], threshold):
                uf.union(i, j)

    buckets: Dict[int, List[Dict]] = {}
    for i, art in enumerate(working):
        buckets.setdefault(uf.find(i), []).append(art)

    min_size = 2 if drop_singletons else max(1, min_cluster_size)

    clusters: List[Dict] = []
    for root, members in buckets.items():
        if len(members) < min_size:
            continue
        rep = _pick_representative(members)
        dates = [d for d in (_parse_date(m) for m in members)
                 if d is not None and d.year > 1]
        first_seen = min(dates).isoformat() if dates else None
        last_seen = max(dates).isoformat() if dates else None
        sources = sorted({
            (m.get("source") or m.get("meta", {}).get("site_name") or "")
            for m in members
        } - {""})
        clusters.append({
            "id": 0,
            "label": rep.get("title") or "",
            "topic": topic if isinstance(topic, str)
                     else (", ".join(topic) if topic else None),
            "size": len(members),
            "score": _cluster_score(members),
            "sources": sources,
            "first_seen": first_seen,
            "last_seen": last_seen,
            "representative": rep,
            "articles": members,
        })

    if sort_by == "size":
        clusters.sort(key=lambda c: c["size"], reverse=True)
    elif sort_by == "date":
        clusters.sort(key=lambda c: c["last_seen"] or "", reverse=True)
    else:
        clusters.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(clusters):
        c["id"] = i

    logger.info("Clustered %d articles -> %d clusters (threshold=%.2f)",
                len(working), len(clusters), threshold)
    return clusters