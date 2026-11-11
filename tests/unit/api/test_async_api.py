import asyncio
from unittest.mock import AsyncMock

import pytest
import open_news

from open_news import batch_summarize, fetch, get_article, search, search_and_summarize
from open_news.processing import batch


def test_legacy_async_functions_are_public_compatibility_aliases():
    assert callable(open_news.fetch_async)
    assert callable(open_news.search_async)
    assert callable(open_news.get_article_async)
    assert callable(open_news.batch_summarize_async)
    assert callable(open_news.search_and_summarize_async)


@pytest.mark.parametrize(
    ("legacy_name", "implementation_path", "args"),
    [
        ("fetch_async", "open_news.api._fetch_async", ()),
        ("search_async", "open_news.api._search_async", ("climate",)),
        (
            "get_article_async",
            "open_news.api._get_article_async",
            ("https://example.com/story",),
        ),
        (
            "batch_summarize_async",
            "open_news.api._batch_summarize_impl",
            (["https://example.com/story"],),
        ),
        (
            "search_and_summarize_async",
            "open_news.api._search_and_summarize_impl",
            ("climate",),
        ),
    ],
)
def test_legacy_async_alias_warns_and_delegates(
    mocker, legacy_name, implementation_path, args
):
    implementation = mocker.patch(
        implementation_path,
        new_callable=AsyncMock,
        return_value=[],
    )
    legacy = getattr(open_news, legacy_name)

    with pytest.warns(DeprecationWarning, match="async_=True"):
        result = asyncio.run(legacy(*args))

    assert result == []
    implementation.assert_awaited_once()


def test_fetch_async_option_returns_awaitable(mocker):
    fetch_async = mocker.patch(
        "open_news.api._fetch_async",
        new_callable=AsyncMock,
        return_value=[{"title": "Science"}],
    )

    result = asyncio.run(fetch(category="science", async_=True))

    assert result == [{"title": "Science"}]
    fetch_async.assert_awaited_once_with(
        category="science",
        location=None,
        time_limit="d",
        max_results=20,
        language=None,
        whitelist=None,
        blacklist=None,
        sort_by="date",
        full_content=False,
        search_in=None,
        js=False,
    )


def test_fetch_sync_default_is_unchanged(mocker):
    fetch_async = mocker.patch(
        "open_news.api._fetch_async",
        new_callable=AsyncMock,
        return_value=[{"title": "Science"}],
    )

    assert fetch(category="science") == [{"title": "Science"}]
    fetch_async.assert_awaited_once()


def test_fetch_async_option_rejects_streaming(mocker):
    with pytest.raises(ValueError, match="async_=True cannot be combined"):
        fetch(refresh_interval=30, async_=True)


def test_search_async_option_returns_awaitable(mocker):
    search_async = mocker.patch(
        "open_news.api._search_async",
        new_callable=AsyncMock,
        return_value=[{"title": "Climate"}],
    )

    result = asyncio.run(search("climate", country="IN", async_=True))

    assert result == [{"title": "Climate"}]
    search_async.assert_awaited_once_with(
        query="climate",
        query_mode="any",
        exclude_terms=None,
        time_limit="d",
        start_date=None,
        end_date=None,
        country="IN",
        max_results=20,
        language=None,
        whitelist=None,
        blacklist=None,
        sort_by="date",
        full_content=False,
        search_in=None,
        js=False,
    )


def test_search_async_option_rejects_streaming():
    with pytest.raises(ValueError, match="async_=True cannot be combined"):
        search("climate", refresh_interval=30, async_=True)


def test_get_article_async_option_returns_awaitable(mocker):
    get_async = mocker.patch(
        "open_news.api._get_article_async",
        new_callable=AsyncMock,
        return_value={"title": "Story"},
    )

    result = asyncio.run(
        get_article("https://example.com/story", timeout=10, async_=True)
    )

    assert result == {"title": "Story"}
    get_async.assert_awaited_once_with(
        "https://example.com/story",
        timeout=10,
        js=False,
    )


def test_batch_summarize_async_option_returns_awaitable(mocker):
    summarize_async = mocker.patch(
        "open_news.processing.batch._batch_summarize_impl",
        new_callable=AsyncMock,
        return_value=[{"summary": "Story"}],
    )

    result = asyncio.run(
        batch_summarize(["https://example.com/story"], async_=True)
    )

    assert result == [{"summary": "Story"}]
    summarize_async.assert_awaited_once_with(
        ["https://example.com/story"],
        sentence_count=3,
        include_full_text=False,
        include_images_videos=False,
        max_concurrency=5,
        timeout_per_article=30,
        js=False,
        dedupe=True,
    )


def test_search_and_summarize_async_option_returns_awaitable(mocker):
    summarize_async = mocker.patch(
        "open_news.processing.batch._search_and_summarize_impl",
        new_callable=AsyncMock,
        return_value=[{"summary": "Story"}],
    )

    result = asyncio.run(search_and_summarize("climate", async_=True))

    assert result == [{"summary": "Story"}]
    summarize_async.assert_awaited_once_with(
        "climate",
        limit=10,
        sentence_count=3,
        include_full_text=False,
        include_images_videos=False,
        max_concurrency=5,
        js=False,
    )


def test_async_search_and_summarize_uses_async_implementation(mocker):
    search_async = mocker.patch(
        "open_news.api._search_async",
        new_callable=AsyncMock,
        return_value=[{"title": "Story", "url": "https://example.com/story"}],
    )
    summarize_async = mocker.patch(
        "open_news.processing.batch._batch_summarize_impl",
        new_callable=AsyncMock,
        return_value=[
            {
                "url": "https://example.com/story",
                "status": "success",
                "summary": "Short summary",
            }
        ],
    )
    sync_search = mocker.patch("open_news.api.search")

    result = asyncio.run(batch._search_and_summarize_impl("climate", limit=2))

    assert result == [
        {
            "title": "Story",
            "url": "https://example.com/story",
            "status": "success",
            "summary": "Short summary",
        }
    ]
    search_async.assert_awaited_once_with(query="climate", max_results=2)
    summarize_async.assert_awaited_once_with(
        ["https://example.com/story"],
        sentence_count=3,
        include_full_text=False,
        include_images_videos=False,
        max_concurrency=5,
        js=False,
    )
    sync_search.assert_not_called()
