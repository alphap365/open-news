from open_news.processing.dedupe import normalize_url, dedupe_articles

def test_normalize_url_strips_tracking():
    url = "https://www.cnn.com/story?utm_source=fb&utm_medium=social"
    assert normalize_url(url) == "cnn.com/story"

def test_normalize_url_resolves_google_news(mocker):
    # Patch resolve_url to avoid real network calls
    mocker.patch("open_news.processing.dedupe.resolve_url", return_value="https://real.com/article")
    gnews_url = "https://news.google.com/redirect?url=xyz"
    assert normalize_url(gnews_url) == "real.com/article"

def test_dedupe_exact_url():
    articles = [
        {"url": "https://a.com/story", "title": "A"},
        {"url": "https://a.com/story?utm_source=x", "title": "B"},  # now stripped
        {"url": "https://b.com/story", "title": "C"},
    ]
    result = dedupe_articles(articles, fuzzy=False)
    assert len(result) == 2

def test_dedupe_fuzzy_title(sample_articles_list):
    # "AI takes over" and "AI takes over the world" should cluster
    result = dedupe_articles(sample_articles_list, fuzzy=True)
    assert len(result) < 3  # Should drop at least one