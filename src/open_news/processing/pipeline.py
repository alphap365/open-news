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

# Body-keyword search fetches candidates in windows of
# ``max_results * _BODY_SEARCH_BATCH_FACTOR`` and keeps walking the
# candidate list until enough text-verified matches accumulate or the
# pool is exhausted. The first window matches the historical behaviour
# of fetching ``max_results * 3`` candidates up front.
_BODY_SEARCH_BATCH_FACTOR = 3

# Keys the fetcher fills in that must never replace source attribution
# the pipeline already assembled. dedupe_articles() merges same-URL
# records into ``sources`` and picks the best ``source``; the fetcher's
# ``source`` is often just a netloc fallback and would throw that away.
_SOURCE_KEYS = ("source", "sources")


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
        # Never mutate the caller's dict: annotations and merged fields
        # go on a copy, so the input objects survive the call unchanged.
        if art.get("_full_content") is True:  # already fetched
            return art
        url = art.get("url", "")

        if is_hub_url(url):
            skipped = dict(art)
            skipped["_full_content"] = False
            skipped["_full_content_reason"] = "hub_or_listing_page"
            return skipped

        try:
            async with sem:
                full = await _get_article_async(url, js=js, client=shared_client)
            if full.get("text"):
                merged = dict(art)
                for key, value in full.items():
                    if key in _SOURCE_KEYS and merged.get(key):
                        continue  # keep dedupe-merged source attribution
                    if value not in (None, "", [], {}):
                        merged[key] = value
                merged["_full_content"] = True
                return merged
            failed = dict(art)
            failed["_full_content"] = False
            failed["_full_content_reason"] = "extraction_returned_no_text"
            return failed
        except Exception as e:
            logger.warning("full_content fetch failed for %s: %s", url, e)
            failed = dict(art)
            failed["_full_content"] = False
            failed["_full_content_reason"] = f"fetch_error: {e}"
            return failed

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


def _has_search_text(article: Dict, search_in: List[str]) -> bool:
    """True when any field the token filter consults is populated.

    The token filter treats an article with no searchable text as a match
    ("don't punish missing fields"). For body-keyword confirmation that
    fallback must not count toward the max_results quota: a run of failed
    fetches would otherwise fill the quota with unverified articles and
    stop the batch loop before later candidates are even fetched.
    """
    if "title" in search_in and article.get("title"):
        return True
    if "description" in search_in and article.get("description"):
        return True
    if "body" in search_in and article.get("text"):
        return True
    return False


async def _filter_by_body_async(
    articles: List[Dict],
    max_results: int,
    *,
    query: Optional[str],
    query_mode: str,
    exclude_terms: Optional[List[str]],
    search_in: Optional[List[str]],
    js: bool = False,
) -> List[Dict]:
    """Body-keyword filtering over batch-wise enriched candidates.

    Body matches can only be checked after the full text is fetched, and
    nothing guarantees the first candidates match. Enriching a single
    ``max_results * 3`` window (the previous behaviour) truncated the
    result set whenever early candidates missed: later hits were never
    fetched. This walks the candidate list in fixed-size batches — each
    fetched with the shared bounded-concurrency helper — until
    ``max_results`` text-verified matches accumulate or the candidates
    run out.

    Articles whose fetch failed keep their ``_full_content_reason`` and
    stay in the output (the token filter does not punish missing
    fields), but they do not count toward the quota, so failures never
    stop the loop from reaching later candidates.
    """
    if max_results <= 0 or not articles:
        return []

    fields = search_in or ["title", "description"]
    batch_size = max_results * _BODY_SEARCH_BATCH_FACTOR
    matched: List[Dict] = []
    confirmed = 0
    for start in range(0, len(articles), batch_size):
        pool = await _enrich_full_content_async(
            articles[start : start + batch_size], js=js
        )
        for art in filter_articles(
            pool,
            query=query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            search_in=search_in,
        ):
            matched.append(art)
            if _has_search_text(art, fields):
                confirmed += 1
        if confirmed >= max_results:
            break
    return matched


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
        articles = await _filter_by_body_async(
            articles,
            max_results,
            query=query,
            query_mode=query_mode,
            exclude_terms=exclude_terms,
            search_in=search_in,
            js=js,
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
