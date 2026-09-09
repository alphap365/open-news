"""
open-news: A modern news article aggregation and extraction library.
"""

import logging
from .api import (
    fetch,
    search,
    get_article,
    discover_and_get,
    search_site,
)
from .processing.batch import batch_summarize
from .processing.summarizer import summarize_text

__version__ = "1.0.0"

# Prevent "No handler found" warnings if the user doesn't configure logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "fetch",
    "search",
    "get_article",
    "discover_and_get",
    "search_site",
    "batch_summarize",
    "summarize_text",
]