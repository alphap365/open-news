"""High-level endpoints: get article, search news, live news, site search."""

import logging
from typing import List, Dict, Optional

from .fetch.article import get_article as _get_article
from .feeds.sources import from_rss, from_google_news, search_site as _search_site
from .feeds.registry import get_feed_list, discover_rss_feed, clear_feed_cache as _clear_feed_cache
from .processing.dedupe import dedupe_articles

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


def search_site(keyword: str, domain: str, limit: int = 10) -> List[Dict]:
    """Search for a keyword scoped to a single news domain."""
    return _search_site(keyword, domain, limit)


def live_news(
    category: str = "news",
    country: Optional[str] = None,
    limit_per_feed: Optional[int] = None,
    force_refresh: bool = False,
    dedupe: bool = True,
    dedupe_fuzzy: bool = False,
) -> List[Dict]:
    """
    Fetch recent articles from curated RSS feeds (open-feeds registry).

    Args:
        category: 'news', 'business', 'politics', 'geopolitics'
        country: If given, use country-specific feeds (e.g., 'india', 'usa').
            Takes precedence over category when both are given.
        limit_per_feed: Max articles per feed (default from remote config)
        force_refresh: Bypass the 24h feed-list cache and refetch now.
        dedupe: Remove duplicate articles across feeds (e.g. the same
            story from a direct outlet RSS and a merged Google News RSS
            entry). Default True.
        dedupe_fuzzy: Also collapse near-duplicate titles across different
            URLs (same story, different outlets). Slower — O(n^2) on
            article count, capped internally. Default False.
    """
    feed_data = get_feed_list(category, country, use_cache=not force_refresh)
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

    if dedupe:
        before = len(all_articles)
        all_articles = dedupe_articles(all_articles, fuzzy=dedupe_fuzzy)
        logger.info(f"Dedupe: {before} -> {len(all_articles)}")

    return all_articles


def discover_and_get(website_url: str, limit: int = 10, dedupe: bool = True) -> List[Dict]:
    """Discover RSS feed from a website and fetch its articles."""
    rss_url = discover_rss_feed(website_url)
    if not rss_url:
        logger.warning(f"No RSS feed found for {website_url}")
        return []
    articles = from_rss(rss_url, limit)
    if dedupe:
        articles = dedupe_articles(articles)
    return articles


def clear_feed_cache(category: Optional[str] = None, country: Optional[str] = None) -> None:
    """Clear cached feed-list data. No args wipes the entire cache."""
    _clear_feed_cache(category=category, country=country)


# Legacy aliases (backward compatibility) — both names are fully supported
# public API, not deprecated. New code may use either; these longer names
# are kept since early adopters and existing scripts depend on them.
fetch_article = get_article
search_news = search
get_live_news = live_news
get_articles_from_website_rss = discover_and_get