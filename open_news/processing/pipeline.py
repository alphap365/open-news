import logging
from typing import Dict, List, Optional

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

    articles = filter_by_language(articles, language)
    articles = filter_articles(
        articles, query=query, query_mode=query_mode,
        exclude_terms=exclude_terms, search_in=search_in,
    )
    articles = filter_by_domain(articles, whitelist=whitelist, blacklist=blacklist)

    if dedupe:
        articles = dedupe_articles(articles, fuzzy=dedupe_fuzzy)

    articles = sort_articles(articles, sort_by=sort_by)

    # Slice BEFORE full_content enrichment — no point crawling articles
    # that will be discarded by the max_results cutoff anyway.
    articles = articles[:max_results]

    if full_content:
        articles = _enrich_full_content(articles, js=js)

    logger.info(f"Pipeline: {before} raw -> {len(articles)} final")
    return articles


def _enrich_full_content(articles: List[Dict], js: bool = False) -> List[Dict]:
    from ..fetch.article import get_article

    enriched = []
    for art in articles:
        url = art.get("url", "")
        if not url:
            art["_full_content"] = False
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
                enriched.append(art)
        except Exception as e:
            logger.warning(f"full_content fetch failed for {url}: {e}")
            art["_full_content"] = False
            enriched.append(art)

    return enriched