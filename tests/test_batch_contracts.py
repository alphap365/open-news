"""Offline contract tests for open_news.processing.batch.

These exist because a real bug (batch.search_and_summarize forwarding
`limit=` to api.search, whose parameter is `max_results=`) got through
every prior test. The fix is trivial; the value is in making sure it
can't come back.
"""

from contextlib import nullcontext
from unittest.mock import AsyncMock, patch

from open_news.processing import batch


def test_search_and_summarize_forwards_max_results():
    captured = {}

    def fake_search(query, **kwargs):
        captured["query"] = query
        captured.update(kwargs)
        return []

    with patch("open_news.api.search", side_effect=fake_search):
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


def _stub_fetch():
    """Return a context manager that stubs whichever fetch function
    batch.py imported — sync (get_article) or async (get_article_async).

    Patching the module-local name (batch.get_article_async) is required
    because `from X import Y` binds Y into the importing module's
    namespace; patching the source module wouldn't intercept the call."""
    stub = {"text": "body text long enough for a summary", "title": "Same"}
    if hasattr(batch, "get_article_async"):
        return patch(
            "open_news.processing.batch.get_article_async",
            new_callable=AsyncMock,
            return_value=stub,
        )
    if hasattr(batch, "get_article"):
        return patch(
            "open_news.processing.batch.get_article",
            return_value=stub,
        )
    return nullcontext()


def test_search_and_summarize_calls_search_exactly_once():
    """search_and_summarize reuses the already grouped story results."""
    call_count = {"n": 0}

    def fake_search(query, **kwargs):
        call_count["n"] += 1
        return [{"title": "Same", "url": "https://a.com/1"}]

    with patch("open_news.api.search", side_effect=fake_search), _stub_fetch():
        batch.search_and_summarize("query", limit=2)

    assert call_count["n"] == 1, (
        f"search() called {call_count['n']} times; must be exactly 1. "
        f"Search should be called once and its story representatives reused."
    )
