"""Minimal news fetching package: article text, images, videos, RSS, batch summarization."""

from .main import (
    get_article,
    search,
    live_news,
    discover_and_get,
    # legacy aliases
    fetch_article,
    search_news,
    get_live_news,
    get_articles_from_website_rss,
)
from .batch_processor import batch_summarize, search_and_summarize
from .batch_processor import fetch_and_summarize_batch, fetch_and_summarize_search_results  # legacy

__all__ = [
    "get_article",
    "search",
    "live_news",
    "discover_and_get",
    "batch_summarize",
    "search_and_summarize",
    # legacy
    "fetch_article",
    "search_news",
    "get_live_news",
    "get_articles_from_website_rss",
    "fetch_and_summarize_batch",
    "fetch_and_summarize_search_results",
]

__version__ = "0.1.2"