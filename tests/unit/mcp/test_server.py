import asyncio
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("fastmcp")

from open_news.mcp import (
    cluster_news,
    discover_site_news,
    export_news,
    fetch_news,
    filter_news,
    get_article,
    mcp,
    rank_news,
    search_news,
    search_site_news,
    summarize_articles,
    summarize_text_content,
)


def test_mcp_registers_news_tools():
    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "cluster_news",
        "discover_site_news",
        "export_news",
        "fetch_news",
        "filter_news",
        "get_article",
        "rank_news",
        "search_news",
        "search_site_news",
        "summarize_articles",
        "summarize_text_content",
    }


def test_search_news_uses_library_api(mocker):
    search = mocker.patch(
        "open_news.mcp.search",
        new_callable=AsyncMock,
        return_value=[{"title": "News"}],
    )

    result = asyncio.run(search_news("technology", country="IN", max_results=3))

    assert result == [{"title": "News"}]
    search.assert_awaited_once_with(
        query="technology",
        country="IN",
        max_results=3,
        time_limit="d",
        query_mode="any",
        exclude_terms=None,
        start_date=None,
        end_date=None,
        language=None,
        whitelist=None,
        blacklist=None,
        async_=True,
    )


def test_search_news_forwards_filters_and_window(mocker):
    search = mocker.patch(
        "open_news.mcp.search",
        new_callable=AsyncMock,
        return_value=[],
    )

    asyncio.run(
        search_news(
            "climate",
            query_mode="all",
            exclude_terms=["sports"],
            start_date="2026-01-01",
            end_date="2026-02-01",
            language="en",
            whitelist=["reuters.com"],
            blacklist=["example.com"],
        )
    )

    kwargs = search.await_args.kwargs
    assert kwargs["query_mode"] == "all"
    assert kwargs["exclude_terms"] == ["sports"]
    assert kwargs["start_date"] == "2026-01-01"
    assert kwargs["end_date"] == "2026-02-01"
    assert kwargs["whitelist"] == ["reuters.com"]
    assert kwargs["blacklist"] == ["example.com"]


def test_fetch_news_uses_library_api(mocker):
    fetch = mocker.patch(
        "open_news.mcp.fetch",
        new_callable=AsyncMock,
        return_value=[{"title": "News"}],
    )

    result = asyncio.run(fetch_news(category="tech", location="IN", max_results=3))

    assert result == [{"title": "News"}]
    fetch.assert_awaited_once_with(
        category="tech",
        location="IN",
        max_results=3,
        time_limit="d",
        language=None,
        full_content=False,
        whitelist=None,
        blacklist=None,
        async_=True,
    )


def test_get_article_uses_library_api(mocker):
    get = mocker.patch(
        "open_news.mcp._get_article",
        new_callable=AsyncMock,
        return_value={"title": "News"},
    )

    result = asyncio.run(get_article("https://example.com/news"))

    assert result == {"title": "News"}
    get.assert_awaited_once_with(
        "https://example.com/news",
        timeout=15,
        js=False,
        async_=True,
    )


def test_search_site_news_runs_library_api_in_thread(mocker):
    search = mocker.patch(
        "open_news.mcp.search_site",
        return_value=[{"title": "News"}],
    )

    result = asyncio.run(search_site_news("technology", "example.com", limit=3))

    assert result == [{"title": "News"}]
    search.assert_called_once_with(
        "technology",
        "example.com",
        limit=3,
        query_mode="any",
        language=None,
        full_content=False,
    )


def test_discover_site_news_runs_library_api_in_thread(mocker):
    discover = mocker.patch(
        "open_news.mcp.discover_and_get",
        return_value=[{"title": "News"}],
    )

    result = asyncio.run(discover_site_news("https://example.com", limit=3))

    assert result == [{"title": "News"}]
    discover.assert_called_once_with(
        "https://example.com",
        limit=3,
        prefer_rss=True,
        max_pages=None,
        max_depth=None,
        full_content=False,
    )


def test_summarize_articles_uses_library_api(mocker):
    summarize = mocker.patch(
        "open_news.mcp.batch_summarize",
        new_callable=AsyncMock,
        return_value=[{"summary": "News"}],
    )

    result = asyncio.run(
        summarize_articles(["https://example.com/news"], sentence_count=2)
    )

    assert result == [{"summary": "News"}]
    summarize.assert_awaited_once_with(
        ["https://example.com/news"],
        sentence_count=2,
        include_full_text=False,
        timeout_per_article=30,
        async_=True,
    )


def test_processing_tools_use_library_api(mocker):
    filter_call = mocker.patch(
        "open_news.mcp.filter_articles",
        return_value=[{"title": "Filtered"}],
    )
    rank_call = mocker.patch(
        "open_news.mcp.rank_articles",
        return_value=[{"title": "Ranked"}],
    )
    cluster_call = mocker.patch(
        "open_news.mcp.cluster_articles",
        return_value=[{"label": "Cluster"}],
    )
    summarize_call = mocker.patch(
        "open_news.mcp.summarize_text",
        return_value="Summary",
    )
    articles = [{"title": "News"}]

    assert filter_news(articles, topic="climate") == [{"title": "Filtered"}]
    filter_call.assert_called_once_with(
        articles,
        query=None,
        topic="climate",
        topic_mode="any",
        exclude_terms=None,
        search_in=None,
    )
    assert rank_news(articles, "climate", top_k=2) == [{"title": "Ranked"}]
    rank_call.assert_called_once_with(
        articles,
        query="climate",
        method="auto",
        top_k=2,
        search_in=None,
    )
    assert cluster_news(articles, threshold=0.8) == [{"label": "Cluster"}]
    cluster_call.assert_called_once_with(
        articles,
        threshold=0.8,
        drop_singletons=False,
        min_cluster_size=1,
        sort_by="score",
        rank_query=None,
    )
    assert summarize_text_content("article text", sentence_count=2) == "Summary"
    summarize_call.assert_called_once_with("article text", sentence_count=2)


def test_export_news_serializes_records(mocker):
    markdown = mocker.patch("open_news.mcp.to_markdown", return_value="# md")
    articles = [{"title": "News"}]

    result = export_news(articles, format="markdown", title="Today")

    assert result == "# md"
    markdown.assert_called_once_with(articles, title="Today")


def test_export_news_passes_path_when_given(tmp_path, mocker):
    csv_export = mocker.patch("open_news.mcp.to_csv", return_value="title\n")
    target = str(tmp_path / "news.csv")

    assert export_news([{"title": "News"}], format="csv", path=target) == "title\n"
    csv_export.assert_called_once_with([{"title": "News"}], path=target)


def test_export_news_rejects_unknown_format():
    with pytest.raises(ValueError, match="unsupported format"):
        export_news([], format="yaml")
