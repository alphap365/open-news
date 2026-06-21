"""High-level endpoints: get article, search news, live news from remote feeds."""

import logging
from typing import List, Dict, Optional

from .get_article import get_article as _get_article
from .get_url import from_rss, from_google_news
from .get_rss import get_feed_list, discover_rss_feed

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Simplified public API
# ------------------------------------------------------------------

def get_article(url: str, timeout: int = 15, js: bool = False) -> Dict:
    """Fetch full article content, metadata, images, videos."""
    return _get_article(url, timeout, js=js)


def search(query: str, limit: int = 10) -> List[Dict]:
    """Search Google News for a query."""
    return from_google_news(query, limit)


def live_news(category: str = "news", country: Optional[str] = None, limit_per_feed: Optional[int] = None) -> List[Dict]:
    """
    Fetch recent articles from curated RSS feeds (open-feeds repository).

    Args:
        category: 'news', 'business', 'politics', 'geopolitics'
        country: If given, use country-specific feeds (e.g., 'india', 'usa')
        limit_per_feed: Max articles per feed (default from remote config)
    """
    feed_data = get_feed_list(category, country)
    feeds = feed_data.get("feeds", [])
    if not feeds:
        logger.warning(f"No feeds for category={category}, country={country}")
        return []

    limit = limit_per_feed or feed_data.get("max_articles_per_feed", 8)
    all_articles = []
    for feed in feeds:
        feed_url = feed.get("url")
        feed_name = feed.get("name", "Unknown")
        if not feed_url:
            continue
        articles = from_rss(feed_url, limit=limit)
        for art in articles:
            art["source"] = feed_name
        all_articles.extend(articles)

    logger.info(f"Fetched {len(all_articles)} articles from {len(feeds)} feeds")
    return all_articles


def discover_and_get(website_url: str, limit: int = 10) -> List[Dict]:
    """Discover RSS feed from a website and fetch its articles."""
    rss_url = discover_rss_feed(website_url)
    if not rss_url:
        logger.warning(f"No RSS feed found for {website_url}")
        return []
    return from_rss(rss_url, limit)


# Legacy aliases (backward compatibility) — both names are fully supported
# public API, not deprecated. New code may use either; these longer names
# are kept since early adopters and existing scripts depend on them.
fetch_article = get_article
search_news = search
get_live_news = live_news
get_articles_from_website_rss = discover_and_get