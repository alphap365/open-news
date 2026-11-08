"""Group related coverage into stories while preserving every source article."""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Union

from ..utils.textutil import normalize_title as _normalize_title
from .dedupe import _source_names, dedupe_articles
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
        age_hours = max(
            0.0, (datetime.now(timezone.utc) - newest).total_seconds() / 3600.0
        )
        recency = 1.0 / (1.0 + age_hours / 24.0)
    else:
        recency = 0.5
    rank_scores = [
        a["_rank_score"]
        for a in members
        if isinstance(a.get("_rank_score"), (int, float))
    ]
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


def cluster_to_article(cluster: Dict) -> Dict:
    """Return a representative article enriched with its related coverage."""
    representative = cluster["representative"]
    article = dict(representative)
    article.update(
        {
            "sources": list(cluster["sources"]),
            "similar_articles": [
                dict(member)
                for member in cluster["articles"]
                if member is not representative
            ],
            "cluster_id": cluster["id"],
            "cluster_size": cluster["size"],
            "cluster_score": cluster["score"],
            "first_seen": cluster["first_seen"],
            "last_seen": cluster["last_seen"],
        }
    )
    return article


def _expand_story_articles(articles: List[Dict]) -> List[Dict]:
    expanded = []
    story_fields = {
        "similar_articles",
        "cluster_id",
        "cluster_size",
        "cluster_score",
        "first_seen",
        "last_seen",
    }
    for article in articles:
        cluster_members = article.get("articles")
        cluster_representative = article.get("representative")
        if isinstance(cluster_members, list) and isinstance(
            cluster_representative, dict
        ):
            expanded.extend(
                dict(member) for member in cluster_members if isinstance(member, dict)
            )
            continue
        representative = {
            key: value for key, value in article.items() if key not in story_fields
        }
        expanded.append(representative)
        related = article.get("similar_articles")
        if isinstance(related, list):
            expanded.extend(
                dict(member) for member in related if isinstance(member, dict)
            )
    return expanded


def cluster_articles(
    articles: List[Dict],
    threshold: float = DEFAULT_THRESHOLD,
    min_cluster_size: int = 1,
    topic: Optional[Union[str, List[str]]] = None,
    topic_mode: str = "any",
    search_in: Optional[List[str]] = None,
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

    working = dedupe_articles(_expand_story_articles(list(articles)))
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
        dates = [
            d for d in (_parse_date(m) for m in members) if d is not None and d.year > 1
        ]
        first_seen = min(dates).isoformat() if dates else None
        last_seen = max(dates).isoformat() if dates else None
        sources = sorted({name for member in members for name in _source_names(member)})
        clusters.append(
            {
                "id": 0,
                "label": rep.get("title") or "",
                "topic": topic
                if isinstance(topic, str)
                else (", ".join(topic) if topic else None),
                "size": len(members),
                "score": _cluster_score(members),
                "sources": sources,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "representative": rep,
                "articles": members,
            }
        )

    if sort_by == "size":
        clusters.sort(key=lambda c: c["size"], reverse=True)
    elif sort_by == "date":
        clusters.sort(key=lambda c: c["last_seen"] or "", reverse=True)
    else:
        clusters.sort(key=lambda c: c["score"], reverse=True)
    for i, c in enumerate(clusters):
        c["id"] = i

    logger.info(
        "Clustered %d articles -> %d clusters (threshold=%.2f)",
        len(working),
        len(clusters),
        threshold,
    )
    return clusters
