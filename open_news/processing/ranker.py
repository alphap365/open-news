import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List

from dateutil import parser as date_parser

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.75
MIN_CLUSTER_SIZE = 2  # below this, popularity score falls back to 0 (no boost)


def _parse_date(article: Dict) -> datetime:
    raw = article.get("published") or article.get("publish_date")
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = date_parser.parse(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _normalize_title(title: str) -> str:
    title = (title or "").lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title)


def _cluster_sizes(articles: List[Dict]) -> List[int]:
    """For each article, how many other articles (including itself) share
    a near-identical title. O(n^2) — fine at typical result-page sizes
    (tens of articles), not meant for huge batches."""
    titles = [_normalize_title(a.get("title", "")) for a in articles]
    sizes = [1] * len(articles)
    for i in range(len(articles)):
        if not titles[i]:
            continue
        for j in range(i + 1, len(articles)):
            if not titles[j]:
                continue
            if SequenceMatcher(None, titles[i], titles[j]).ratio() >= FUZZY_THRESHOLD:
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
