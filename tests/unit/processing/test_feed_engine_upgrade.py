import time

import pytest

from open_news import FeedConfig, FeedEngine, FeedProfileRequiredError
from open_news.cache import UserProfile
from open_news.processing.feed_engine import DEFAULT_FEED_WEIGHTS


class MemoryCache:
    def __init__(self):
        self.values = {}

    def get(self, namespace, key, default=None):
        return self.values.get((namespace, key), default)

    def set(self, namespace, key, value, ttl=None):
        self.values[(namespace, key)] = value


class DeletableCache(MemoryCache):
    def __init__(self):
        super().__init__()
        self.deleted = []

    def delete(self, namespace, key):
        self.deleted.append((namespace, key))
        self.values.pop((namespace, key), None)


def _weights(**active):
    """All weights zero except the named ones."""
    weights = {key: 0.0 for key in DEFAULT_FEED_WEIGHTS}
    weights.update(active)
    return weights


def _profile(**fields):
    return UserProfile(user_id="reader", **fields)


# ----------------------------------------------------------------------
# Scoring reads the fields producers actually emit
# ----------------------------------------------------------------------


def test_category_score_uses_singular_category_field():
    engine = FeedEngine(MemoryCache(), FeedConfig(weights=_weights(category=1.0)))
    profile = _profile(categories=("science",))

    result = engine._rank_personalized(
        [{"title": "A", "category": "Science"}],
        profile,
    )

    assert result[0]["_feed_score"] == pytest.approx(1.0)


def test_category_score_also_accepts_a_categories_list():
    engine = FeedEngine(MemoryCache(), FeedConfig(weights=_weights(category=1.0)))
    profile = _profile(categories=("science", "environment"))

    result = engine._rank_personalized(
        [{"title": "A", "categories": ["Science", "Environment"]}],
        profile,
    )

    assert result[0]["_feed_score"] == pytest.approx(1.0)


def test_category_score_ignores_unrelated_categories():
    engine = FeedEngine(MemoryCache(), FeedConfig(weights=_weights(category=1.0)))
    profile = _profile(categories=("science",))

    result = engine._rank_personalized(
        [{"title": "A", "category": "Sports"}],
        profile,
    )

    assert result[0]["_feed_score"] == pytest.approx(0.0)


def test_language_score_reduces_regional_codes():
    engine = FeedEngine(MemoryCache(), FeedConfig(weights=_weights(language=1.0)))
    profile = _profile(languages=("en",))

    result = engine._rank_personalized(
        [{"title": "A", "meta": {"inLanguage": "en-GB"}}],
        profile,
    )

    assert result[0]["_feed_score"] == pytest.approx(1.0)


def test_language_score_reads_top_level_language():
    engine = FeedEngine(MemoryCache(), FeedConfig(weights=_weights(language=1.0)))
    profile = _profile(languages=("fr",))

    result = engine._rank_personalized(
        [{"title": "A", "language": "FR"}],
        profile,
    )

    assert result[0]["_feed_score"] == pytest.approx(1.0)


# ----------------------------------------------------------------------
# Blocked sources
# ----------------------------------------------------------------------


def test_blocked_source_is_removed_from_sources_and_related_coverage():
    engine = FeedEngine(MemoryCache())
    profile = _profile(blocked_sources=("blocked news",))
    story = {
        "title": "Story",
        "source": "Allowed News",
        "sources": ["Allowed News", "Blocked News"],
        "similar_articles": [
            {"title": "Blocked report", "source": "Blocked News"},
            {"title": "Second report", "source": "Other News"},
        ],
    }

    result = engine._rank_personalized([story], profile)

    assert len(result) == 1
    assert result[0]["sources"] == ["Allowed News"]
    assert [item["title"] for item in result[0]["similar_articles"]] == [
        "Second report"
    ]
    assert result[0]["cluster_size"] == 2


def test_blocked_representative_is_replaced_by_allowed_coverage():
    engine = FeedEngine(MemoryCache())
    profile = _profile(blocked_sources=("blocked news",))
    story = {
        "title": "Blocked headline",
        "source": "Blocked News",
        "sources": ["Blocked News", "Other News"],
        "similar_articles": [{"title": "Allowed headline", "source": "Other News"}],
    }

    result = engine._rank_personalized([story], profile)

    assert result[0]["title"] == "Allowed headline"
    assert result[0]["source"] == "Other News"
    assert "similar_articles" not in result[0]


def test_story_is_dropped_when_every_source_is_blocked():
    engine = FeedEngine(MemoryCache())
    profile = _profile(blocked_sources=("blocked news",))

    result = engine._rank_personalized(
        [{"title": "Only", "source": "Blocked News"}],
        profile,
    )

    assert result == []


def test_missing_sources_are_never_treated_as_blocked():
    engine = FeedEngine(MemoryCache())
    profile = _profile(blocked_sources=("blocked news",))

    result = engine._rank_personalized([{"title": "Anonymous"}], profile)

    assert len(result) == 1


# ----------------------------------------------------------------------
# Cached feed validation and invalidation
# ----------------------------------------------------------------------


def test_cached_feed_returns_fresh_entry():
    cache = MemoryCache()
    cached = {"generated_at": time.time(), "items": []}
    cache.values[("calculated_feed", "reader")] = cached
    engine = FeedEngine(cache, FeedConfig(cache_ttl=300))

    assert engine.get_cached_feed("reader") == cached


def test_cached_feed_returns_none_for_stale_entry():
    cache = MemoryCache()
    cache.values[("calculated_feed", "reader")] = {
        "generated_at": time.time() - 600,
        "items": [],
    }
    engine = FeedEngine(cache, FeedConfig(cache_ttl=300))

    assert engine.get_cached_feed("reader") is None


def test_cached_feed_validation_can_be_bypassed():
    cache = MemoryCache()
    cached = {"generated_at": time.time() - 600, "items": []}
    cache.values[("calculated_feed", "reader")] = cached
    engine = FeedEngine(cache, FeedConfig(cache_ttl=300))

    assert engine.get_cached_feed("reader", validate=False) == cached


def test_cached_feed_honours_explicit_max_age():
    cache = MemoryCache()
    cached = {"generated_at": time.time() - 600, "items": []}
    cache.values[("calculated_feed", "reader")] = cached
    engine = FeedEngine(cache, FeedConfig(cache_ttl=300))

    assert engine.get_cached_feed("reader", max_age=10_000) == cached


def test_cached_feed_without_generated_at_is_treated_as_stale():
    cache = MemoryCache()
    cache.values[("calculated_feed", "reader")] = {"items": []}
    engine = FeedEngine(cache)

    assert engine.get_cached_feed("reader") is None


def test_clear_cached_feed_deletes_when_supported():
    cache = DeletableCache()
    cache.values[("calculated_feed", "reader")] = {
        "generated_at": time.time(),
        "items": [],
    }
    engine = FeedEngine(cache)

    assert engine.clear_cached_feed("reader") is True
    assert cache.deleted == [("calculated_feed", "reader")]
    assert engine.get_cached_feed("reader") is None


def test_clear_cached_feed_reports_unsupported_backend():
    engine = FeedEngine(MemoryCache())

    assert engine.clear_cached_feed("reader") is False


def test_cached_feed_reads_require_a_backend():
    with pytest.raises(Exception, match="cache backend is required"):
        FeedEngine().get_cached_feed("reader")


# ----------------------------------------------------------------------
# Config knobs
# ----------------------------------------------------------------------


def test_feed_config_merges_partial_weights():
    config = FeedConfig(weights={"interest": 0.9})

    assert config.weights["interest"] == 0.9
    assert config.weights["category"] == DEFAULT_FEED_WEIGHTS["category"]


def test_feed_config_rejects_unknown_weight():
    with pytest.raises(ValueError, match="unknown feed weight"):
        FeedConfig(weights={"popularity": 1.0})


def test_feed_config_rejects_out_of_range_threshold():
    with pytest.raises(ValueError, match="cluster_threshold"):
        FeedConfig(cluster_threshold=1.5)


def test_feed_config_rejects_negative_weights():
    with pytest.raises(ValueError, match="non-negative"):
        FeedConfig(weights={"interest": -1.0})


def test_build_honours_drop_singletons():
    engine = FeedEngine(MemoryCache(), FeedConfig(drop_singletons=True))

    assert engine.build([{"title": "Only story"}]) == []


def test_build_requires_profile_for_personalized_feeds():
    engine = FeedEngine(MemoryCache())

    with pytest.raises(FeedProfileRequiredError):
        engine.build([{"title": "Story"}], personalized=True)
