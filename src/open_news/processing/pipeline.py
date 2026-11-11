import asyncio
import logging
from typing import Dict, List, Optional

from ..fetch.url_resolver import is_hub_url
from .cluster import cluster_articles, cluster_to_article
from .dedupe import dedupe_articles
from .domain_filter import filter_by_domain
from .language_guard import filter_by_language
from .token_filter import filter_articles

logger = logging.getLogger(__name__)

# Polite default: enough to cut a 40-article page from ~60s to ~8s while
# staying under the radar of any single outlet.
DEFAULT_ENRICH_CONCURRENCY = 8


async def _enrich_full_content_async(
    articles: List[Dict],
    js: bool = False,
    max_concurrency: int = DEFAULT_ENRICH_CONCURRENCY,
) -> List[Dict]:
    """Bounded-concurrency full-content enrichment.

    Order is preserved: results[i] corresponds to articles[i].
    Reuses a single AsyncClient so the connection pool is shared.
    """
    from ..fetch.article import _get_article_async

    if not articles:
        return articles

    sem = asyncio.Semaphore(max_concurrency)
    # Share one client across all requests — connection reuse + TLS handshake
    # savings dwarf the cost of creating a client.
    import httpx

    shared_client = httpx.AsyncClient(follow_redirects=True, timeout=15)

    async def enrich_one(art: Dict) -> Dict:
        if art.get("_full_content") is True:  # already fetched
            return art
        url = art.get("url", "")

        if is_hub_url(url):
            art["_full_content"] = False
            art["_full_content_reason"] = "hub_or_listing_page"
            return art

        try:
            async with sem:
                full = await _get_article_async(url, js=js, client=shared_client)
            if full.get("text"):
                merged = dict(art)
                for key, value in full.items():
                    if value not in (None, "", [], {}):
                        merged[key] = value
                merged["_full_content"] = True
                return merged
            art["_full_content"] = False
            art["_full_content_reason"] = "extraction_returned_no_text"
            return art
        except Exception as e:
            logger.warning("full_content fetch failed for %s: %s", url, e)
            art["_full_content"] = False
            art["_full_content_reason"] = f"fetch_error: {e}"
            return art

    try:
        enriched = await asyncio.gather(*(enrich_one(a) for a in articles))
    finally:
        await shared_client.aclose()

    empty_count = sum(1 for a in enriched if not a.get("_full_content"))
    if empty_count:
        logger.info(
            "full_content enrichment: %d/%d came back empty (see _full_content_reason)",
            empty_count,
            len(articles),
        )
    return list(enriched)


def _enrich_full_content(articles: List[Dict], js: bool = False) -> List[Dict]:
    """Sync wrapper (kept for backward compatibility with api.py / cli)."""
    return asyncio.run(_enrich_full_content_async(articles, js=js))


def run_pipeline(
    articles: List[Dict],
    max_results: int,
    language: Optional[str] = None,
    query: Optional[str] = None,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    search_in: Optional[List[str]] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    js: bool = False,
) -> List[Dict]:
    """Sync pipeline (unchanged public API)."""
    return asyncio.run(
        run_pipeline_async(
            articles,
            max_results,
            language=language,
            query=query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            search_in=search_in,
            whitelist=whitelist,
            blacklist=blacklist,
            sort_by=sort_by,
            full_content=full_content,
            js=js,
        )
    )


async def run_pipeline_async(
    articles: List[Dict],
    max_results: int,
    language: Optional[str] = None,
    query: Optional[str] = None,
    query_mode: str = "any",
    exclude_terms: Optional[List[str]] = None,
    search_in: Optional[List[str]] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    sort_by: str = "date",
    full_content: bool = False,
    js: bool = False,
) -> List[Dict]:
    before = len(articles)
    needs_body = bool(search_in and "body" in search_in and (query or exclude_terms))

    # CPU-bound filters stay sync — event loop has nothing else useful to do
    articles = filter_by_language(articles, language)
    articles = filter_by_domain(articles, whitelist=whitelist, blacklist=blacklist)
    if not needs_body:
        articles = filter_articles(
            articles,
            query=query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            search_in=search_in,
        )

    articles = dedupe_articles(articles)

    if needs_body:
        pool = await _enrich_full_content_async(articles[: max_results * 3], js=js)
        articles = filter_articles(
            pool,
            query=query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            search_in=search_in,
        )

    cluster_sort = {
        "date": "date",
        "popularity": "size",
        "relevance": "score",
    }.get(sort_by, "score")
    clusters = cluster_articles(
        articles,
        rank_query=query,
        search_in=search_in,
        sort_by=cluster_sort,
    )
    stories = [cluster_to_article(cluster) for cluster in clusters[:max_results]]

    if full_content:
        stories = await _enrich_full_content_async(stories, js=js)

    logger.info("Pipeline: %d raw -> %d stories", before, len(stories))
    return stories
