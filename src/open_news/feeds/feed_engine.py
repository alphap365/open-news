"""Compatibility exports for the feed engine moved to ``processing``."""

from ..processing.feed_engine import (
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
