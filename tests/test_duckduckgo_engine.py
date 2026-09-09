import sys
import types

from open_news.config import FetchConfig
from open_news.feeds.duckduckgo_engine import fetch_raw


def test_fetch_raw_uses_current_ddgs_query_parameter(monkeypatch):
    calls = {}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def news(self, **kwargs):
            calls.update(kwargs)
            return [{
                "title": "Technology update",
                "url": "https://example.com/story",
                "source": "Example",
                "date": "2026-09-09",
                "body": "A technology story",
            }]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))

    result = fetch_raw(FetchConfig(category="tech", location="in", max_results=1))

    assert result[0]["title"] == "Technology update"
    assert calls["query"] == "technology"
    assert calls["region"] == "in-en"
    assert "keywords" not in calls