"""Offline contract tests for open_news.processing.batch.

These exist because a real bug (batch.search_and_summarize forwarding
`limit=` to api.search, whose parameter is `max_results=`) got through
every prior test. The fix is trivial; the value is in making sure it
can't come back."""
from unittest.mock import patch

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