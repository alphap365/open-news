import logging
from typing import Dict, List, Optional

from ..config import FetchConfig

logger = logging.getLogger(__name__)

_CATEGORY_TO_DDG_QUERY = {
    "general": "news",
    "business": "business",
    "tech": "technology",
    "sports": "sports",
    "health": "health",
    "science": "science",
    "entertainment": "entertainment",
}


def fetch_raw(config: FetchConfig) -> List[Dict]:
    """
    Query DuckDuckGo News for a category or location feed.

    Returns list of dicts: {title, url, source, published, description}
    — same shape as the Google News engine, pre-filtering.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # deprecated fallback name
        except ImportError:
            raise RuntimeError(
                "fetch() requires the 'ddgs' package. Install with: pip install ddgs"
            )

    keywords = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = config.location or "wt-wt"
    if region != "wt-wt" and "-" not in region:
        region = f"{region}-en"

    results = []
    try:
        with DDGS() as ddgs:
            hits = ddgs.news(
                query=keywords,
                region=region,
                timelimit=config.time_limit,
                max_results=config.max_results * 2,  # over-fetch; pipeline will filter some out
            )
            for hit in hits:
                results.append({
                    "title": hit.get("title", "No title"),
                    "url": hit.get("url", ""),
                    "source": hit.get("source", "Unknown"),
                    "published": hit.get("date", ""),
                    "description": hit.get("body", "")[:500],
                })
        logger.info(f"DuckDuckGo fetch('{keywords}') returned {len(results)} raw results")
    except Exception as e:
        logger.error(f"DuckDuckGo News error for '{keywords}': {e}")

    return [r for r in results if r["url"]]
