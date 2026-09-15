"""
open-news: A modern news article aggregation and extraction library.
"""

import logging
from .api import (
    fetch,
    search,
    stream_search,
    get_article,
    discover_and_get,
    search_site,
)
from .processing.batch import batch_summarize, search_and_summarize
from .processing.summarizer import summarize_text, summarize_with_keywords
from .processing.dedupe import dedupe_articles

__version__ = "1.0.2a1"

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "fetch",
    "search",
    "stream_search",
    "get_article",
    "discover_and_get",
    "search_site",
    "batch_summarize",
    "search_and_summarize",
    "summarize_text",
    "summarize_with_keywords",
    "dedupe_articles",
]