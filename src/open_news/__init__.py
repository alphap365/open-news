import logging

from . import export
from .api import (
    batch_summarize_async,
    cluster_articles,
    discover_and_get,
    fetch,
    fetch_async,
    filter_articles,
    get_article,
    get_article_async,
    rank_articles,
    search,
    search_and_summarize_async,
    search_async,
    search_site,
    stream_fetch,
    stream_search,
)
from .cache import (
    EncryptedCache as EncryptedCache,
)
from .cache import (
    UserProfile as UserProfile,
)
from .cache import (
    load_user_profile as load_user_profile,
)
from .cache import (
    store_user_profile as store_user_profile,
)
from .export import to_csv, to_json, to_jsonld, to_markdown, to_text
from .processing.batch import (
    batch_summarize,
    search_and_summarize,
)
from .processing.dedupe import dedupe_articles
from .processing.feed_engine import (
    FeedCache,
    FeedConfig,
    FeedEngine,
    FeedError,
    FeedProfileRequiredError,
)
from .processing.summarizer import summarize_text, summarize_with_keywords

__version__ = "1.0.6"

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    # sync
    "fetch",
    "search",
    "stream_fetch",
    "stream_search",
    "get_article",
    "discover_and_get",
    "search_site",
    "batch_summarize",
    "search_and_summarize",
    "summarize_text",
    "summarize_with_keywords",
    "dedupe_articles",
    "cluster_articles",
    "FeedConfig",
    "FeedCache",
    "FeedEngine",
    "FeedError",
    "FeedProfileRequiredError",
    "rank_articles",
    "filter_articles",
    "export",
    "to_markdown",
    "to_json",
    "to_jsonld",
    "to_csv",
    "to_text",
    "fetch_async",
    "search_async",
    "get_article_async",
    "batch_summarize_async",
    "search_and_summarize_async",
]
