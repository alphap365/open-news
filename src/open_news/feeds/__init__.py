"""News-source integrations and legacy feed-engine exports."""

from .feed_engine import (
    FeedCache,
    FeedConfig,
    FeedEngine,
    FeedError,
    FeedProfileRequiredError,
)

__all__ = [
    "FeedConfig",
    "FeedCache",
    "FeedEngine",
    "FeedError",
    "FeedProfileRequiredError",
]
