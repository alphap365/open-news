import asyncio
import logging
import warnings
from datetime import date, datetime
from typing import Awaitable, Dict, Iterator, List, Optional, Union, cast

from .config import FetchConfig, SearchConfig
from .feeds.duckduckgo_engine import fetch_raw
from .feeds.googlenews_engine import search_raw, search_raw_async
from .feeds.rss_discovery import discover_rss_feed
from .feeds.sources import from_rss
from .feeds.sources import search_site as _search_site
from .fetch.article import get_article as _get_article
from .fetch.article import _get_article_async
from .fetch.crawler import crawl_site
from .processing.cluster import cluster_articles as cluster_articles
from .processing.batch import _batch_summarize_impl, _search_and_summarize_impl
from .processing.dedupe import normalize_url
from .processing.pipeline import run_pipeline, run_pipeline_async
from .processing.rank import rank_articles as rank_articles
from .processing.token_filter import (
    filter_articles as filter_articles,
)
from .utils.textutil import normalize_title

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Simplified public API
# ------------------------------------------------------------------


def _warn_async_alias(name: str, replacement: str) -> None:
    warnings.warn(
        f"{name}() is deprecated; use {replacement}(..., async_=True) instead.",
        DeprecationWarning,
        stacklevel=2,
    )


async def _fetch_async(
    category: str = "general",
    location: Optional[str] = None,
    time_limit: str = "d",
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    js: bool = False,
) -> List[Dict]:
    """Async variant of fetch(). Streaming is sync-only; use sync fetch for it."""
    config = FetchConfig(
        category=category,
        location=location,
        time_limit=time_limit,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in or ["title", "description"],
    )
    # fetch_raw is still sync internally; call it via to_thread so the loop
    # can schedule other tasks. (Further tier-by-tier async upgrades can
    # layer on top of this later.)
    raw = await asyncio.to_thread(fetch_raw, config)
    return await run_pipeline_async(
        raw,
        max_results=config.max_results,
        language=config.language,
        whitelist=config.whitelist,
        blacklist=config.blacklist,
        sort_by=config.sort_by,
        full_content=config.full_content,
        search_in=config.search_in,
        js=js,
    )


async def fetch_async(
    category: str = "general",
    location: Optional[str] = None,
    time_limit: str = "d",
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    js: bool = False,
) -> List[Dict]:
    """Deprecated alias for ``await fetch(..., async_=True)``."""
    _warn_async_alias("fetch_async", "fetch")
    return await _fetch_async(
        category=category,
        location=location,
        time_limit=time_limit,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in,
        js=js,
    )


async def _search_async(
    query: str,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    time_limit: str = "d",
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    country: Optional[str] = None,
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    js: bool = False,
) -> List[Dict]:
    """Async keyword search returning one representative article per story."""
    config = SearchConfig(
        query=query,
        query_mode=query_mode,
        exclude_terms=exclude_terms,
        time_limit=time_limit,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in or ["title", "description"],
    )
    raw = await search_raw_async(config, country=country, language=config.language)
    return await run_pipeline_async(
        raw,
        max_results=config.max_results,
        language=config.language,
        query=config.query,
        query_mode=config.query_mode,
        exclude_terms=config.exclude_terms,
        search_in=config.search_in,
        whitelist=config.whitelist,
        blacklist=config.blacklist,
        sort_by=config.sort_by,
        full_content=config.full_content,
        js=js,
    )


async def search_async(
    query: str,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    time_limit: str = "d",
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    country: Optional[str] = None,
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    js: bool = False,
) -> List[Dict]:
    """Deprecated alias for ``await search(..., async_=True)``."""
    _warn_async_alias("search_async", "search")
    return await _search_async(
        query=query,
        query_mode=query_mode,
        exclude_terms=exclude_terms,
        time_limit=time_limit,
        start_date=start_date,
        end_date=end_date,
        country=country,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in,
        js=js,
    )


def get_article(
    url: str,
    timeout: int = 15,
    js: bool = False,
    async_: bool = False,
) -> Union[Dict, Awaitable[Dict]]:
    """Fetch full article content, metadata, images, videos."""
    if async_:
        return _get_article_async(url, timeout=timeout, js=js)
    return _get_article(url, timeout, js=js)


async def get_article_async(
    url: str,
    timeout: int = 15,
    js: bool = False,
) -> Dict:
    """Deprecated alias for ``await get_article(..., async_=True)``."""
    _warn_async_alias("get_article_async", "get_article")
    return await _get_article_async(url, timeout=timeout, js=js)


async def batch_summarize_async(
    urls: List[str],
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_concurrency: int = 5,
    timeout_per_article: int = 30,
    js: bool = False,
    dedupe: bool = True,
) -> List[Dict]:
    """Deprecated alias for ``await batch_summarize(..., async_=True)``."""
    _warn_async_alias("batch_summarize_async", "batch_summarize")
    return await _batch_summarize_impl(
        urls,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_concurrency,
        timeout_per_article=timeout_per_article,
        js=js,
        dedupe=dedupe,
    )


async def search_and_summarize_async(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_concurrency: int = 5,
    js: bool = False,
) -> List[Dict]:
    """Deprecated alias for ``await search_and_summarize(..., async_=True)``."""
    _warn_async_alias("search_and_summarize_async", "search_and_summarize")
    return await _search_and_summarize_impl(
        query,
        limit=limit,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_concurrency,
        js=js,
    )


def fetch(
    category: str = "general",
    location: Optional[str] = None,
    time_limit: str = "d",
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    refresh_interval: Optional[int] = None,
    js: bool = False,
    async_: bool = False,
) -> Union[List[Dict], Iterator[List[Dict]], Awaitable[List[Dict]]]:
    """
    Live category/location news via the DuckDuckGo News engine. Always
    queries live — no disk cache — since freshness is the point. This
    replaces the old registry-backed live_news().

    Args:
        category: 'general'|'business'|'tech'|'sports'|'health'|'science'|'entertainment'
        location: country/region code, e.g. 'in', 'us' — takes precedence over category
        time_limit: 'd'|'w'|'m' recency window
        max_results: hard cap on returned story groups
        language: ISO 639-1 code, enforced via pre-download language guard
        whitelist / blacklist: domain allow/deny list
        sort_by: 'date'|'relevance'|'popularity'
        full_content: if True, crawls+extracts each surviving URL for full text
        search_in: which fields token filtering applies to (mainly relevant
            when combined with exclude_terms; fetch() has no query itself)
        refresh_interval: if set (seconds, >= 5), returns a generator that
            polls on this cadence and yields only newly-seen articles
        js: use the persistent-browser crawler backend for full_content fetches
        async_: if True, return a coroutine to await instead of blocking
    """
    config = FetchConfig(
        category=category,
        location=location,
        time_limit=time_limit,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in or ["title", "description"],
        refresh_interval=refresh_interval,
    )

    if async_ and refresh_interval:
        raise ValueError("async_=True cannot be combined with refresh_interval")

    if refresh_interval:
        return _fetch_stream(config, js=js)

    coroutine = _fetch_async(
        category=category,
        location=location,
        time_limit=time_limit,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in,
        js=js,
    )
    return coroutine if async_ else asyncio.run(coroutine)


def _fetch_stream(config: FetchConfig, js: bool) -> Iterator[List[Dict]]:
    """Generator backing fetch(refresh_interval=...): re-queries on a
    cadence, yielding only articles not seen in a previous cycle."""
    import time

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    while True:
        raw = fetch_raw(config)
        processed = run_pipeline(
            raw,
            max_results=config.max_results,
            language=config.language,
            whitelist=config.whitelist,
            blacklist=config.blacklist,
            sort_by=config.sort_by,
            full_content=config.full_content,
            search_in=config.search_in,
            js=js,
        )
        new_articles = _only_unseen(processed, seen_urls, seen_titles)
        if new_articles:
            yield new_articles
        time.sleep(
            config.refresh_interval if config.refresh_interval is not None else 60
        )


def search(
    query: str,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    time_limit: str = "d",
    start_date: Optional[Union[str, date, datetime]] = None,
    end_date: Optional[Union[str, date, datetime]] = None,
    country: Optional[str] = None,
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    refresh_interval: Optional[int] = None,
    js: bool = False,
    async_: bool = False,
) -> Union[List[Dict], Iterator[List[Dict]], Awaitable[List[Dict]]]:
    """
    Direct keyword search via Google News RSS.

    Args:
        query: search terms
        query_mode: 'any'|'all'|'exact_phrase'
        exclude_terms: word-boundary-filtered exclusion list
        time_limit: 'd'|'w'|'m' recency window. Ignored if start_date
            and/or end_date is given.
        start_date / end_date: custom date range (v1.0.2). Accepts a
            'YYYY-MM-DD' string, an ISO-8601 datetime string, or a
            date/datetime object. Either can be omitted for an open-ended
            range (e.g. start_date only = "everything since"). Takes
            precedence over time_limit. See
            docs/parameters-reference.md for accepted formats.
        country: ISO 3166-1 alpha-2 region code (e.g. "US", "IN", "GB"),
            controlling Google News' locale/region results (v1.0.2).
            Defaults to "US". See docs/parameters-reference.md for the
            full list of codes Google News recognizes.
        refresh_interval: if set (seconds, >= 5), returns a generator that
            polls this search on a cadence and yields only newly-seen
            articles each cycle — the search equivalent of
            fetch(refresh_interval=...), previously only available via
            fetch(). Prefer stream_search() if you always want a
            generator back regardless of this argument.
        async_: if True, return a coroutine to await instead of blocking
        (remaining parameters shared with fetch(), same meaning)
    """
    config = SearchConfig(
        query=query,
        query_mode=query_mode,
        exclude_terms=exclude_terms,
        time_limit=time_limit,
        start_date=start_date,
        end_date=end_date,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in or ["title", "description"],
        refresh_interval=refresh_interval,
    )

    if async_ and refresh_interval:
        raise ValueError("async_=True cannot be combined with refresh_interval")

    if refresh_interval:
        return _search_stream(config, country=country, js=js)

    coroutine = _search_async(
        query=query,
        query_mode=query_mode,
        exclude_terms=exclude_terms,
        time_limit=time_limit,
        start_date=start_date,
        end_date=end_date,
        country=country,
        max_results=max_results,
        language=language,
        whitelist=whitelist,
        blacklist=blacklist,
        sort_by=sort_by,
        full_content=full_content,
        search_in=search_in,
        js=js,
    )
    return coroutine if async_ else asyncio.run(coroutine)


def _search_stream(
    config: SearchConfig, country: Optional[str], js: bool
) -> Iterator[List[Dict]]:
    """Generator backing search(refresh_interval=...) / stream_search():
    re-queries the same keyword search on a cadence, yielding only articles
    not seen in a previous cycle. Mirrors _fetch_stream()'s shape."""
    import time

    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    while True:
        raw = search_raw(config, country=country, language=config.language)
        processed = run_pipeline(
            raw,
            max_results=config.max_results,
            language=config.language,
            query=config.query,
            query_mode=config.query_mode,
            exclude_terms=config.exclude_terms,
            search_in=config.search_in,
            whitelist=config.whitelist,
            blacklist=config.blacklist,
            sort_by=config.sort_by,
            full_content=config.full_content,
            js=js,
        )
        new_articles = _only_unseen(processed, seen_urls, seen_titles)
        if new_articles:
            yield new_articles
        time.sleep(
            config.refresh_interval if config.refresh_interval is not None else 60
        )


def _only_unseen(articles, seen_urls, seen_titles):
    fresh = []
    for story in articles:
        members = [story, *story.get("similar_articles", [])]
        urls = {
            normalize_url(article.get("url", ""))
            for article in members
            if article.get("url")
        }
        unseen_urls = urls - seen_urls
        title_key = normalize_title(story.get("title", ""))
        if urls and not unseen_urls:
            continue
        if not urls and (not title_key or title_key in seen_titles):
            continue
        seen_urls.update(urls)
        if title_key:
            seen_titles.add(title_key)
        fresh.append(story)
    return fresh


def stream_search(
    query: str,
    refresh_interval: int = 60,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    country: Optional[str] = None,
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    js: bool = False,
) -> Iterator[List[Dict]]:
    """
    Live/streaming keyword search (v1.0.2) — the search() equivalent of
    fetch(refresh_interval=...), closing the gap noted in earlier
    changelogs ("no live/streaming keyword search yet").

    Polls search() on `refresh_interval` seconds and yields only articles
    not seen in a previous cycle, same semantics as fetch()'s generator.
    A thin, always-a-generator convenience wrapper around
    search(refresh_interval=...) for callers who don't want to branch on
    the return type.

    Example:
        for new_articles in stream_search("budget 2026", refresh_interval=30):
            for a in new_articles:
                print(a["title"])
    """
    return cast(
        Iterator[List[Dict]],
        search(
            query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            country=country,
            max_results=max_results,
            language=language,
            whitelist=whitelist,
            blacklist=blacklist,
            sort_by=sort_by,
            full_content=full_content,
            refresh_interval=max(5, refresh_interval),
            js=js,
        ),
    )


def stream_fetch(
    category: str = "general",
    refresh_interval: int = 60,
    location: Optional[str] = None,
    time_limit: str = "d",
    max_results: int = 20,
    language: Optional[str] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    search_in: Optional[List[str]] = None,
    js: bool = False,
) -> Iterator[List[Dict]]:
    """
    Live/streaming category feed — the fetch() equivalent of
    stream_search(). Polls on `refresh_interval` seconds and yields only
    articles not seen in a previous cycle, same semantics as
    fetch(refresh_interval=...) and stream_search().

    Always returns a generator, so callers don't have to branch on the
    return type of fetch().

    Example:
        for new_articles in stream_fetch("tech", refresh_interval=30):
            for a in new_articles:
                print(a["title"])
    """
    return cast(
        Iterator[List[Dict]],
        fetch(
            category=category,
            location=location,
            time_limit=time_limit,
            max_results=max_results,
            language=language,
            whitelist=whitelist,
            blacklist=blacklist,
            sort_by=sort_by,
            full_content=full_content,
            search_in=search_in,
            refresh_interval=max(5, refresh_interval),
            js=js,
        ),
    )


def search_site(
    keyword: str,
    domain: str,
    limit: int = 10,
    query_mode: str = "any",
    language: Optional[str] = None,
    full_content: bool = False,
    js: bool = False,
) -> List[Dict]:
    """Search a single news domain, scoped via Google News RSS + site:,
    sharing the same filtering pipeline as search()."""
    raw = _search_site(keyword, domain, limit=limit * 2)  # over-fetch for filtering
    return run_pipeline(
        raw,
        max_results=limit,
        language=language,
        query=keyword,
        query_mode=query_mode,
        full_content=full_content,
        js=js,
    )


def discover_and_get(
    website_url: str,
    limit: int = 10,
    js: bool = False,
    max_pages: Optional[int] = None,
    max_depth: Optional[int] = None,
    prefer_rss: bool = True,
    full_content: bool = False,
) -> List[Dict]:
    """
    Discover and fetch articles from ANY news-provider URL — a homepage, a
    section page, or a direct feed. Crawling is the compulsory backbone
    here now: every call runs the from-scratch crawler (fetch/crawler.py)
    unless an RSS feed is found and prefer_rss short-circuits it.

    Args:
        website_url: Any URL on the provider's site (not necessarily the
            homepage — a section/category page works and narrows the crawl).
        limit: Max story groups to return.
        js: Use the JS-rendering crawler backend (headless browser, one
            persistent instance reused across pages) instead of the default
            fast async HTTP backend. Use for sites whose article links or
            content only appear after client-side rendering.
        max_pages: Crawl budget — how many pages the crawler will visit in
            total (not how many articles it must find). None (default)
            lets crawl_site() pick its own js-appropriate default (40 for
            the async backend, 15 for the js backend); pass a value to
            override that in either mode.
        max_depth: How many link-hops from website_url the crawler follows.
            None (default) defers to crawl_site()'s per-backend default
            (2 for async, 1 for js); pass a value to override.
        prefer_rss: If True (default), try RSS auto-discovery first as a
            cheap shortcut; only falls through to the full crawl if no feed
            is found. Set False to always crawl (e.g. if the site's RSS is
            known to be stale/incomplete compared to its actual article set).
        full_content: If True, and the RSS shortcut is used, enrich each
            RSS entry with full extracted content (text/authors/images/
            meta) via the same _enrich_full_content() step fetch()/search()
            use — so results have a consistent shape whether they came
            from the RSS path or the crawl path (crawl results already
            include full content).
    """
    if prefer_rss:
        rss_url = discover_rss_feed(website_url)
        if rss_url:
            articles = from_rss(rss_url, limit * 3)
            if articles:
                return run_pipeline(
                    articles,
                    max_results=limit,
                    full_content=full_content,
                    js=js,
                )
            logger.info(f"RSS feed at {rss_url} yielded nothing, falling back to crawl")

    articles = crawl_site(
        website_url,
        max_pages=max_pages,
        max_depth=max_depth,
        js=js,
    )
    return run_pipeline(articles, max_results=limit)


# Legacy aliases (backward compatibility) — both names are fully supported
# public API, not deprecated. New code may use either; these longer names
# are kept since early adopters and existing scripts depend on them.
fetch_article = get_article
get_articles_from_website_rss = discover_and_get
# NOTE: live_news / get_live_news / clear_feed_cache / search_news are
# retired in v1.0.0 — see docs/v1.0.0_SPEC.md migration table.
# fetch(category=..., location=...) replaces live_news().
# search(query=...) replaces the old bare search()/search_news().
