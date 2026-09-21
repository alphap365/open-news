import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List

from dateutil import parser as date_parser
from ..utils.dates import parse_datetime
from ..utils.textutil import normalize_title as _normalize_title
logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.75
MIN_CLUSTER_SIZE = 2  # below this, popularity score falls back to 0 (no boost)


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _parse_date(article: Dict) -> datetime:
    raw = article.get("published") or article.get("publish_date")
    return parse_datetime(raw) or _EPOCH


def _cluster_sizes(articles: List[Dict]) -> List[int]:
    """Per article: how many near-identical titles it stands for. Starts from
    the `_cluster_size` dedupe recorded, then adds looser (0.75) matches among
    what survived. O(n^2) with cheap prefilters; meant for result-page sizes."""
    titles = [_normalize_title(a.get("title", "")) for a in articles]
    sizes = [max(1, int(a.get("_cluster_size", 1) or 1)) for a in articles]
    for i in range(len(articles)):
        if not titles[i]:
            continue
        for j in range(i + 1, len(articles)):
            if not titles[j]:
                continue
            sm = SequenceMatcher(None, titles[i], titles[j])
            if sm.real_quick_ratio() < FUZZY_THRESHOLD or sm.quick_ratio() < FUZZY_THRESHOLD:
                continue
            if sm.ratio() >= FUZZY_THRESHOLD:
                sizes[i] += 1
                sizes[j] += 1
    return sizes


def sort_articles(articles: List[Dict], sort_by: str = "date") -> List[Dict]:
    if not articles:
        return articles

    if sort_by == "date":
        return sorted(articles, key=_parse_date, reverse=True)

    if sort_by == "relevance":
        return articles  # engine order already is relevance order

    if sort_by == "popularity":
        sizes = _cluster_sizes(articles)
        scored = [
            (size if size >= MIN_CLUSTER_SIZE else 0, art)
            for size, art in zip(sizes, articles)
        ]
        # Stable sort: ties preserve original (relevance) order
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [art for _, art in scored]

    logger.warning(f"Unknown sort_by={sort_by!r}, returning unsorted")
    return articles
