from open_news.config import SearchConfig
from open_news.feeds import googlenews_engine


def test_search_raw_returns_decoded_article_url(monkeypatch):
    class FakeFeed:
        entries = [{
            "title": "Example story - Example Source",
            "link": "https://news.google.com/rss/articles/redirect",
            "published": "2026-09-09",
            "summary": "Example summary",
            "source": {"title": "Example Source"},
        }]

    monkeypatch.setattr(googlenews_engine.feedparser, "parse", lambda url: FakeFeed())
    monkeypatch.setattr(
        googlenews_engine,
        "resolve_url",
        lambda url: "https://example.com/story",
    )

    result = googlenews_engine.search_raw(SearchConfig(query="example", max_results=1))

    assert result[0]["url"] == "https://example.com/story"