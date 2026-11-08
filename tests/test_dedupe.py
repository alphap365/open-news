from open_news.processing.dedupe import dedupe_articles, normalize_url


def test_normalize_url_strips_tracking():
    url = "https://www.cnn.com/story?utm_source=fb&utm_medium=social"
    assert normalize_url(url) == "cnn.com/story"


def test_normalize_url_resolves_google_news(mocker):
    # Patch resolve_url to avoid real network calls
    mocker.patch(
        "open_news.processing.dedupe.resolve_url",
        return_value="https://real.com/article",
    )
    gnews_url = "https://news.google.com/redirect?url=xyz"
    assert normalize_url(gnews_url) == "real.com/article"


def test_dedupe_exact_url():
    articles = [
        {"url": "https://a.com/story", "title": "A"},
        {"url": "https://a.com/story?utm_source=x", "title": "B"},  # stripped
        {"url": "https://b.com/story", "title": "C"},
    ]
    result = dedupe_articles(articles, fuzzy=False)
    assert len(result) == 2


def test_dedupe_prefers_non_aggregator_on_collision():
    articles = [
        {
            "url": "https://example.com/story",
            "title": "Wire copy",
            "source": "AP News",
        },
        {
            "url": "https://example.com/story?utm_source=x",
            "title": "Direct",
            "source": "Example",
        },
    ]
    result = dedupe_articles(articles, fuzzy=False)
    assert len(result) == 1
    assert result[0]["title"] == "Direct"


def test_dedupe_writes_resolved_gnews_url_back(mocker):
    mocker.patch(
        "open_news.processing.dedupe.resolve_url",
        return_value="https://real.com/article",
    )
    articles = [
        {"url": "https://news.google.com/redirect?url=xyz", "title": "A"},
    ]
    result = dedupe_articles(articles, fuzzy=False)
    assert result[0]["url"] == "https://real.com/article"


def test_dedupe_fuzzy_title():
    articles = [
        {"url": "https://a.com/1", "title": "AI takes over the world"},
        {"url": "https://b.com/2", "title": "AI takes over world"},
        {"url": "https://c.com/3", "title": "Sports update"},
    ]
    result = dedupe_articles(articles, fuzzy=True)
    assert len(result) == 2


def test_dedupe_resolves_google_url_once_per_entry(mocker):
    """dedupe_articles must resolve each Google News URL exactly once.

    normalize_url() already calls resolve_url() internally. An explicit
    second resolve_url() per gnews URL costs a network round-trip for no
    benefit."""
    spy = mocker.patch(
        "open_news.processing.dedupe.resolve_url",
        return_value="https://real.example.com/story",
    )
    dedupe_articles(
        [{"url": "https://news.google.com/rss/articles/abc", "title": "A"}],
        fuzzy=False,
    )
    assert spy.call_count <= 1, (
        f"resolve_url called {spy.call_count} times for a single Google "
        f"News URL; must be at most 1"
    )


def test_dedupe_never_resolves_non_google_urls(mocker):
    """Direct-outlet URLs must not go through resolve_url at all."""
    spy = mocker.patch(
        "open_news.processing.dedupe.resolve_url",
        return_value="https://irrelevant.example/",
    )
    dedupe_articles(
        [
            {"url": "https://a.com/story", "title": "A"},
            {"url": "https://b.com/story", "title": "B"},
        ],
        fuzzy=False,
    )
    spy.assert_not_called()
