import logging
from .api import (
    fetch, search, fetch_async, search_async,
    stream_fetch, stream_search,
    get_article, discover_and_get, search_site,
    cluster_articles, rank_articles, filter_articles,
)
from .fetch.article import get_article_async
from .processing.batch import (
    batch_summarize, batch_summarize_async,
    search_and_summarize, search_and_summarize_async,
)
from .processing.summarizer import summarize_text, summarize_with_keywords
from .processing.dedupe import dedupe_articles

from . import export
from .export import to_markdown, to_json

__version__ = "1.0.5"

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    # sync
    "fetch", "search", "stream_fetch", "stream_search",
    "get_article", "discover_and_get", "search_site",
    "batch_summarize", "search_and_summarize",
    "summarize_text", "summarize_with_keywords",
    "dedupe_articles",
    "cluster_articles", "rank_articles", "filter_articles",
    "export", "to_markdown", "to_json",
    # async
    "fetch_async", "search_async",
    "get_article_async",
    "batch_summarize_async", "search_and_summarize_async",
]