import logging
from typing import Dict, List, Optional

from ..fetch.url_resolver import is_hub_url
from .language_guard import filter_by_language
from .token_filter import filter_articles
from .domain_filter import filter_by_domain
from .dedupe import dedupe_articles
from .ranker import sort_articles

logger = logging.getLogger(__name__)


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
    dedupe: bool = True,
    dedupe_fuzzy: bool = True,
    js: bool = False,
) -> List[Dict]:
    before = len(articles)

    # search_in=["body"] can only be judged after the text is downloaded.
    needs_body = bool(search_in and "body" in search_in and (query or exclude_terms))

    articles = filter_by_language(articles, language)
    articles = filter_by_domain(articles, whitelist=whitelist, blacklist=blacklist)
    if not needs_body:
        articles = filter_articles(
            articles, query=query, query_mode=query_mode,
            exclude_terms=exclude_terms, search_in=search_in,
        )

    if dedupe:
        articles = dedupe_articles(articles, fuzzy=dedupe_fuzzy)

    articles = sort_articles(articles, sort_by=sort_by)

    if needs_body:
        # Download a bounded pool (3x the goal), then filter on real text.
        pool = _enrich_full_content(articles[: max_results * 3], js=js)
        articles = filter_articles(
            pool, query=query, query_mode=query_mode,
            exclude_terms=exclude_terms, search_in=search_in,
        )

    # Slice BEFORE the final enrichment — no point crawling discarded articles.
    articles = articles[:max_results]

    if full_content:
        articles = _enrich_full_content(articles, js=js)

    logger.info(f"Pipeline: {before} raw -> {len(articles)} final")
    return articles


def _enrich_full_content(articles: List[Dict], js: bool = False) -> List[Dict]:
    from ..fetch.article import get_article

    enriched = []
    empty_count = 0
    for art in articles:
        if art.get("_full_content") is True:      # already fetched (body-filter pass)
            enriched.append(art)
            continue
        url = art.get("url", "")

        # Belt-and-suspenders: even if a hub/listing page slipped past the
        # feed engine (e.g. a caller assembled `articles` by hand rather
        # than via fetch()/search()), don't waste a crawl on something
        # that structurally cannot contain a single article body — and
        # say so explicitly rather than letting it look like a generic
        # extraction failure.
        if is_hub_url(url):
            art["_full_content"] = False
            art["_full_content_reason"] = "hub_or_listing_page"
            empty_count += 1
            enriched.append(art)
            continue

        try:
            full = get_article(url, js=js)
            if full.get("text"):
                # {**art, **full} would let any *empty* field in `full`
                # (e.g. extraction found no description on a paywalled or
                # JS-heavy page) silently clobber a perfectly good value
                # already in `art` (e.g. the search engine's snippet).
                # Only let `full`'s value win when it actually has one.
                merged = dict(art)
                for key, value in full.items():
                    if value not in (None, "", [], {}):
                        merged[key] = value
                merged["_full_content"] = True
                enriched.append(merged)
            else:
                art["_full_content"] = False
                art["_full_content_reason"] = "extraction_returned_no_text"
                empty_count += 1
                enriched.append(art)
        except Exception as e:
            logger.warning(f"full_content fetch failed for {url}: {e}")
            art["_full_content"] = False
            art["_full_content_reason"] = f"fetch_error: {e}"
            empty_count += 1
            enriched.append(art)

    if empty_count:
        logger.info(
            "full_content enrichment: %d/%d articles came back empty "
            "(see _full_content_reason on each)",
            empty_count, len(articles),
        )

    return enriched
