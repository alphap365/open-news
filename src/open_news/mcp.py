import asyncio
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from open_news import (
    batch_summarize,
    cluster_articles,
    discover_and_get,
    fetch,
    filter_articles,
    get_article,
    rank_articles,
    search,
    search_site,
    summarize_text,
)

mcp = FastMCP("Open News")


@mcp.tool
async def search_news(
    query: str,
    country: str = "US",
    max_results: int = 10,
    time_limit: str = "d",
) -> List[Dict[str, Any]]:
    """Search Google News for articles matching a query."""
    return await search(
        query=query,
        country=country,
        max_results=max_results,
        time_limit=time_limit,
        async_=True,
    )


@mcp.tool
async def fetch_news(
    category: str = "general",
    location: Optional[str] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch current news for a category or location."""
    return await fetch(
        category=category,
        location=location,
        max_results=max_results,
        async_=True,
    )


@mcp.tool
async def get_article(url: str, timeout: int = 15, js: bool = False) -> Dict[str, Any]:
    """Fetch an article and extract its text and metadata."""
    return await get_article(url, timeout=timeout, js=js, async_=True)


@mcp.tool
async def search_site_news(
    keyword: str,
    domain: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Search for news about a keyword from one publisher domain."""
    return await asyncio.to_thread(search_site, keyword, domain, limit=limit)


@mcp.tool
async def discover_site_news(
    website_url: str,
    limit: int = 10,
    prefer_rss: bool = True,
) -> List[Dict[str, Any]]:
    """Discover recent articles from a news website or feed URL."""
    return await asyncio.to_thread(
        discover_and_get,
        website_url,
        limit=limit,
        prefer_rss=prefer_rss,
    )


@mcp.tool
async def summarize_articles(
    urls: List[str],
    sentence_count: int = 3,
) -> List[Dict[str, Any]]:
    """Fetch and summarize articles from a list of URLs."""
    return await batch_summarize(urls, sentence_count=sentence_count, async_=True)


@mcp.tool
def summarize_text_content(text: str, sentence_count: int = 3) -> str:
    """Create a short extractive summary of supplied article text."""
    return summarize_text(text, sentence_count=sentence_count)


@mcp.tool
def filter_news(
    articles: List[Dict[str, Any]],
    query: Optional[str] = None,
    topic: Optional[str] = None,
    exclude_terms: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter article records by query, topic, and excluded terms."""
    return filter_articles(
        articles,
        query=query,
        topic=topic,
        exclude_terms=exclude_terms,
    )


@mcp.tool
def rank_news(
    articles: List[Dict[str, Any]],
    query: str,
    method: str = "auto",
    top_k: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Rank article records by relevance to a query."""
    return rank_articles(articles, query=query, method=method, top_k=top_k)


@mcp.tool
def cluster_news(
    articles: List[Dict[str, Any]],
    threshold: float = 0.72,
    drop_singletons: bool = False,
) -> List[Dict[str, Any]]:
    """Group similar article records into story clusters."""
    return cluster_articles(
        articles,
        threshold=threshold,
        drop_singletons=drop_singletons,
    )


def main() -> None:
    mcp.run()


__all__ = ["main", "mcp"]


if __name__ == "__main__":
    main()