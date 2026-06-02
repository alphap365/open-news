"""Minimal news fetching package: article text, RSS/Google News URLs, feed discovery, batch processing."""

from .main import fetch_article, search_news, get_live_news, get_articles_from_website_rss
from .batch_processor import fetch_and_summarize_batch, fetch_and_summarize_search_results

__all__ = [
    "fetch_article",
    "search_news",
    "get_live_news",
    "get_articles_from_website_rss",
    "fetch_and_summarize_batch",
    "fetch_and_summarize_search_results",
]
