"""Minimal news fetching package: article text, images, videos, RSS,
Google News, site search, batch summarization, dedupe."""

from .api import (
    get_article,
    search,
    search_site,
    live_news,
    discover_and_get,
    clear_feed_cache,
    # legacy aliases
    fetch_article,
    search_news,
    get_live_news,
    get_articles_from_website_rss,
)
from .processing.batch import batch_summarize, search_and_summarize
from .processing.batch import fetch_and_summarize_batch, fetch_and_summarize_search_results  # legacy
from .processing.dedupe import dedupe_articles
from .feeds.registry import list_categories, list_countries

__all__ = [
    "get_article",
    "search",
    "search_site",
    "live_news",
    "discover_and_get",
    "clear_feed_cache",
    "batch_summarize",
    "search_and_summarize",
    "dedupe_articles",
    "list_categories",
    "list_countries",
    # legacy
    "fetch_article",
    "search_news",
    "get_live_news",
    "get_articles_from_website_rss",
    "fetch_and_summarize_batch",
    "fetch_and_summarize_search_results",
]

__version__ = "0.2.0"