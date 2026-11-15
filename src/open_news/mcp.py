import asyncio
from typing import Any, Awaitable, Dict, List, Optional, cast

from fastmcp import FastMCP

from open_news import (
    batch_summarize,
    cluster_articles,
    discover_and_get,
    fetch,
    filter_articles,
    get_article as _get_article,
    rank_articles,
    search,
    search_site,
    summarize_text,
    to_csv,
    to_json,
    to_jsonld,
    to_markdown,
    to_text,
)

mcp = FastMCP("Open News")

_EXPORT_FORMATS = ("markdown", "json", "jsonld", "csv", "text")


def _exporter_for(name: str) -> Optional[Any]:
    """Resolve an exporter at call time so the mapping stays patchable."""
    exporters: Dict[str, Any] = {
        "markdown": to_markdown,
        "json": to_json,
        "jsonld": to_jsonld,
        "csv": to_csv,
        "text": to_text,
    }
    return exporters.get(name)


@mcp.tool
async def search_news(
    query: str,
    country: str = "US",
    max_results: int = 10,
    time_limit: str = "d",
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Search Google News for articles matching a query.

    ``start_date``/``end_date`` accept ``YYYY-MM-DD`` and take precedence
    over ``time_limit``.
    """
    return await cast(
        Awaitable[List[Dict[str, Any]]],
        search(
            query=query,
            country=country,
            max_results=max_results,
            time_limit=time_limit,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            start_date=start_date,
            end_date=end_date,
            language=language,
            whitelist=whitelist,
            blacklist=blacklist,
            async_=True,
        ),
    )


@mcp.tool
async def fetch_news(
    category: str = "general",
    location: Optional[str] = None,
    max_results: int = 10,
    time_limit: str = "d",
    language: Optional[str] = None,
    full_content: bool = False,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch current news for a category or location.

    ``full_content`` crawls and extracts each surviving article, which is
    noticeably slower but yields article text and metadata.
    """
    return await cast(
        Awaitable[List[Dict[str, Any]]],
        fetch(
            category=category,
            location=location,
            max_results=max_results,
            time_limit=time_limit,
            language=language,
            full_content=full_content,
            whitelist=whitelist,
            blacklist=blacklist,
            async_=True,
        ),
    )


@mcp.tool
async def get_article(url: str, timeout: int = 15, js: bool = False) -> Dict[str, Any]:
    """Fetch an article and extract its text and metadata."""
    return await cast(
        Awaitable[Dict[str, Any]],
        _get_article(url, timeout=timeout, js=js, async_=True),
    )


@mcp.tool
async def search_site_news(
    keyword: str,
    domain: str,
    limit: int = 10,
    query_mode: str = "any",
    language: Optional[str] = None,
    full_content: bool = False,
) -> List[Dict[str, Any]]:
    """Search for news about a keyword from one publisher domain."""
    return await asyncio.to_thread(
        search_site,
        keyword,
        domain,
        limit=limit,
        query_mode=query_mode,
        language=language,
        full_content=full_content,
    )


@mcp.tool
async def discover_site_news(
    website_url: str,
    limit: int = 10,
    prefer_rss: bool = True,
    max_pages: Optional[int] = None,
    max_depth: Optional[int] = None,
    full_content: bool = False,
) -> List[Dict[str, Any]]:
    """Discover recent articles from a news website or feed URL."""
    return await asyncio.to_thread(
        discover_and_get,
        website_url,
        limit=limit,
        prefer_rss=prefer_rss,
        max_pages=max_pages,
        max_depth=max_depth,
        full_content=full_content,
    )


@mcp.tool
async def summarize_articles(
    urls: List[str],
    sentence_count: int = 3,
    include_full_text: bool = False,
    timeout_per_article: int = 30,
) -> List[Dict[str, Any]]:
    """Fetch and summarize articles from a list of URLs."""
    return await cast(
        Awaitable[List[Dict[str, Any]]],
        batch_summarize(
            urls,
            sentence_count=sentence_count,
            include_full_text=include_full_text,
            timeout_per_article=timeout_per_article,
            async_=True,
        ),
    )


@mcp.tool
def summarize_text_content(text: str, sentence_count: int = 3) -> str:
    """Create a short extractive summary of supplied article text."""
    return summarize_text(text, sentence_count=sentence_count)


@mcp.tool
def filter_news(
    articles: List[Dict[str, Any]],
    query: Optional[str] = None,
    topic: Optional[str] = None,
    topic_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    search_in: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter article records by query, topic, and excluded terms."""
    return filter_articles(
        articles,
        query=query,
        topic=topic,
        topic_mode=topic_mode,
        exclude_terms=exclude_terms,
        search_in=search_in,
    )


@mcp.tool
def rank_news(
    articles: List[Dict[str, Any]],
    query: str,
    method: str = "auto",
    top_k: Optional[int] = None,
    search_in: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Rank article records by relevance to a query."""
    return rank_articles(
        articles,
        query=query,
        method=method,
        top_k=top_k,
        search_in=search_in,
    )


@mcp.tool
def cluster_news(
    articles: List[Dict[str, Any]],
    threshold: float = 0.72,
    drop_singletons: bool = False,
    min_cluster_size: int = 1,
    sort_by: str = "score",
    rank_query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Group similar article records into story clusters."""
    return cluster_articles(
        articles,
        threshold=threshold,
        drop_singletons=drop_singletons,
        min_cluster_size=min_cluster_size,
        sort_by=sort_by,
        rank_query=rank_query,
    )


@mcp.tool
def export_news(
    articles: List[Dict[str, Any]],
    format: str = "markdown",
    path: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Serialize article records to markdown, json, jsonld, csv, or text.

    Returns the serialized string; when ``path`` is given the same content is
    also written there.
    """
    exporter = _exporter_for(format)
    if exporter is None:
        raise ValueError(
            f"unsupported format {format!r}; "
            f"expected one of {sorted(_EXPORT_FORMATS)}"
        )
    kwargs: Dict[str, Any] = {}
    if path:
        kwargs["path"] = path
    if title and format == "markdown":
        kwargs["title"] = title
    return exporter(articles, **kwargs)


def main() -> None:
    mcp.run()


__all__ = ["main", "mcp"]


if __name__ == "__main__":
    main()
