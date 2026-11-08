import logging
from datetime import datetime, timezone
from typing import Dict, List

from ..utils.dates import parse_datetime

logger = logging.getLogger(__name__)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _parse_date(article: Dict) -> datetime:
    raw = (
        article.get("published")
        or article.get("publish_date")
        or article.get("published_at")
    )
    return parse_datetime(raw) or _EPOCH


def sort_articles(articles: List[Dict], sort_by: str = "date") -> List[Dict]:
    if not articles:
        return articles

    if sort_by == "date":
        return sorted(articles, key=_parse_date, reverse=True)

    if sort_by == "relevance":
        return articles  # engine order already is relevance order

    if sort_by == "popularity":
        return sorted(
            articles,
            key=lambda article: (
                len(article.get("sources", []))
                if isinstance(article.get("sources"), (list, tuple, set))
                else 1
            ),
            reverse=True,
        )

    logger.warning(f"Unknown sort_by={sort_by!r}, returning unsorted")
    return articles
