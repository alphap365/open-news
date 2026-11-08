from datetime import datetime, timedelta, timezone

import pytest

from open_news import (
    FeedConfig,
    FeedEngine,
    FeedProfileRequiredError,
)
from open_news.cache import UserProfile


class MemoryCache:
    def __init__(self):
        self.values = {}
        self.set_calls = []

    def get(self, namespace, key, default=None):
        return self.values.get((namespace, key), default)

    def set(self, namespace, key, value, ttl=None):
        self.values[(namespace, key)] = value
        self.set_calls.append((namespace, key, value, ttl))


def _article(title, **fields):
    return {"title": title, **fields}


def test_feed_config_defaults_and_custom_values():
    assert FeedConfig() == FeedConfig(cache_ttl=300, max_items=50)
    assert FeedConfig(cache_ttl=60, max_items=12).cache_ttl == 60
    assert FeedConfig(cache_ttl=60, max_items=12).max_items == 12


def test_build_empty_articles_returns_empty_without_loading_profile(mocker):
    load_profile = mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
    )
    engine = FeedEngine(MemoryCache())

    assert engine.build([], personalized=True) == []
    load_profile.assert_not_called()


def test_build_generic_feed_ranks_by_freshness_without_mutating_input(mocker):
    cache = MemoryCache()
    engine = FeedEngine(cache)
    fresh = _article("Fresh", published_at="2025-01-02T00:00:00+00:00")
    stale = _article("Stale", published_at="2020-01-02T00:00:00+00:00")
    score = mocker.patch.object(
        engine,
        "_freshness_score",
        side_effect=lambda value: 1.0 if value.startswith("2025") else 0.1,
    )

    result = engine.build([stale, fresh])

    assert [item["title"] for item in result] == ["Fresh", "Stale"]
    assert [item["_feed_score"] for item in result] == [1.0, 0.1]
    assert "_feed_score" not in fresh
    assert "_feed_score" not in stale
    assert score.call_count == 2
    assert cache.set_calls == []


def test_build_generic_feed_uses_configured_limit():
    engine = FeedEngine(MemoryCache(), FeedConfig(max_items=2))
    articles = [
        _article("NASA launches a new telescope"),
        _article("Local football team wins final"),
        _article("Gardeners prepare for spring"),
        _article("New restaurant opens downtown"),
    ]

    result = engine.build(articles)

    assert len(result) == 2


def test_generic_feed_does_not_require_a_cache_backend():
    result = FeedEngine().build([_article("NASA launches new telescope")])

    assert len(result) == 1


def test_build_groups_similar_coverage_into_a_story():
    engine = FeedEngine(MemoryCache())
    articles = [
        {
            "title": "City approves a new clean energy plan",
            "url": "https://one.example/energy-plan",
            "source": "One News",
            "published": "2025-01-02T00:00:00Z",
        },
        {
            "title": "City approves new clean energy plan",
            "url": "https://two.example/clean-energy",
            "source": "Two News",
            "published": "2025-01-01T00:00:00Z",
        },
    ]

    result = engine.build(articles)

    assert len(result) == 1
    assert result[0]["cluster_size"] == 2
    assert result[0]["sources"] == ["One News", "Two News"]
    assert result[0]["similar_articles"][0]["url"] == "https://two.example/clean-energy"


def test_build_explicit_limit_overrides_configured_limit():
    engine = FeedEngine(MemoryCache(), FeedConfig(max_items=1))
    articles = [
        _article("NASA launches a telescope"),
        _article("Football team wins final"),
        _article("Restaurant opens downtown"),
    ]

    assert len(engine.build(articles, limit=2)) == 2


def test_build_zero_limit_returns_no_items():
    engine = FeedEngine(MemoryCache())

    assert engine.build([_article("Story")], limit=0) == []


def test_build_personalized_feed_scores_all_profile_preferences(mocker):
    cache = MemoryCache()
    engine = FeedEngine(cache)
    profile = UserProfile(
        user_id="reader",
        interests=("climate", "energy"),
        categories=("science", "environment"),
        languages=("en",),
        preferred_sources=("trusted news",),
    )
    mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
        return_value=profile,
    )
    mocker.patch.object(engine, "_freshness_score", return_value=0.5)
    articles = [
        _article(
            "Climate energy",
            description="",
            categories=["Science", "Environment"],
            language="EN",
            source="Trusted News",
            published_at="2025-01-01",
        ),
        _article(
            "Local report",
            categories=[],
            language="fr",
            source="Other",
            published_at="2025-01-01",
        ),
    ]

    result = engine.build(articles, user_id="reader", personalized=True)

    assert [item["title"] for item in result] == [
        "Climate energy",
        "Local report",
    ]
    assert result[0]["_feed_score"] == pytest.approx(0.95)
    assert result[1]["_feed_score"] == pytest.approx(0.05)


def test_build_personalized_feed_uses_title_description_and_summary(mocker):
    cache = MemoryCache()
    engine = FeedEngine(cache)
    profile = UserProfile(user_id="reader", interests=("climate", "energy"))
    mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
        return_value=profile,
    )
    mocker.patch.object(engine, "_freshness_score", return_value=0.0)
    article = _article(
        "Climate policy",
        description="energy investment",
        summary="",
    )

    result = engine.build([article], user_id="reader", personalized=True)

    assert result[0]["_feed_score"] == pytest.approx(0.55)


def test_build_personalized_feed_excludes_blocked_sources(mocker):
    engine = FeedEngine(MemoryCache())
    profile = UserProfile(
        user_id="reader",
        blocked_sources=("blocked news",),
    )
    mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
        return_value=profile,
    )

    result = engine.build(
        [
            _article("Keep", source="Allowed News"),
            _article("Drop", source="Blocked News"),
        ],
        user_id="reader",
        personalized=True,
    )

    assert [item["title"] for item in result] == ["Keep"]


def test_personalized_feed_requires_user_id():
    engine = FeedEngine(MemoryCache())

    with pytest.raises(
        FeedProfileRequiredError,
        match="user_id is required",
    ):
        engine.build([_article("Story")], personalized=True)


def test_personalized_feed_requires_cache_backend():
    engine = FeedEngine()

    with pytest.raises(
        FeedProfileRequiredError,
        match="cache backend is required",
    ):
        engine.build([_article("Story")], user_id="reader", personalized=True)


def test_personalized_feed_requires_a_cached_profile(mocker):
    cache = MemoryCache()
    load_profile = mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
        return_value=None,
    )
    engine = FeedEngine(cache)

    with pytest.raises(
        FeedProfileRequiredError,
        match="No valid cached profile",
    ):
        engine.build([_article("Story")], user_id="reader", personalized=True)

    load_profile.assert_called_once_with(cache, "reader")


def test_personalized_feed_caches_result_with_configured_ttl(mocker):
    cache = MemoryCache()
    engine = FeedEngine(cache, FeedConfig(cache_ttl=45))
    profile = UserProfile(user_id="reader", interests=("climate",))
    mocker.patch(
        "open_news.processing.feed_engine.load_user_profile",
        return_value=profile,
    )

    result = engine.build(
        [_article("Climate update")],
        user_id="reader",
        personalized=True,
    )

    assert len(cache.set_calls) == 1
    namespace, key, cached, ttl = cache.set_calls[0]
    assert (namespace, key, ttl) == ("calculated_feed", "reader", 45)
    assert cached["items"] == result
    assert isinstance(cached["generated_at"], float)


def test_generic_feed_does_not_cache_result():
    cache = MemoryCache()
    engine = FeedEngine(cache)

    engine.build([_article("Story")], user_id="reader")

    assert cache.set_calls == []


def test_get_cached_feed_reads_calculated_feed_namespace():
    cache = MemoryCache()
    cached = {"generated_at": 123.0, "items": [_article("Cached")]}
    cache.values[("calculated_feed", "reader")] = cached
    engine = FeedEngine(cache)

    assert engine.get_cached_feed("reader") == cached


@pytest.mark.parametrize(
    ("published_at", "expected"),
    [
        (None, 0.0),
        ("not-a-date", 0.0),
        (datetime.now(timezone.utc) + timedelta(days=1), 1.0),
    ],
)
def test_freshness_score_handles_missing_invalid_and_future_dates(
    published_at,
    expected,
):
    assert FeedEngine._freshness_score(published_at) == pytest.approx(expected)


def test_freshness_score_decays_with_age():
    now = datetime.now(timezone.utc)
    recent = FeedEngine._freshness_score(now - timedelta(hours=24))
    older = FeedEngine._freshness_score(now - timedelta(hours=48))

    assert 0 < older < recent < 1
    assert older == pytest.approx(recent**2)
