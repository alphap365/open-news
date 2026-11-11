"""Offline contract tests for article batch summarization."""

from unittest.mock import AsyncMock, patch

from open_news.processing import batch


def test_search_and_summarize_forwards_max_results():
    captured = {}

    async def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return []

    with patch("open_news.api._search_async", side_effect=fake_search):
        batch.search_and_summarize("anything", limit=7)

    assert captured["query"] == "anything"
    assert captured["max_results"] == 7, (
        f"expected max_results=7, got {captured.get('max_results')!r}; "
        f"full kwargs: {captured!r}"
    )
    assert "limit" not in captured, (
        "search_and_summarize forwarded `limit=` to api.search, which "
        "does not accept it"
    )


def _stub_article_fetch():
    """Patch the async article fetch function imported by batch.py."""
    stub = {"text": "body text long enough for a summary", "title": "Same"}
    return patch(
        "open_news.processing.batch._get_article_async",
        new_callable=AsyncMock,
        return_value=stub,
    )


def test_search_and_summarize_calls_search_exactly_once():
    """search_and_summarize reuses the already grouped story results."""
    call_count = {"n": 0}

    async def fake_search(query, **kwargs):
        call_count["n"] += 1
        return [{"title": "Same", "url": "https://a.com/1"}]

    with patch(
        "open_news.api._search_async", side_effect=fake_search
    ), _stub_article_fetch():
        batch.search_and_summarize("query", limit=2)

    assert call_count["n"] == 1, (
        f"search() called {call_count['n']} times; must be exactly 1. "
        f"Search should be called once and its story representatives reused."
    )
