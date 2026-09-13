import logging
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import feedparser

from ..config import SearchConfig
from ..fetch.url_resolver import resolve_url

logger = logging.getLogger(__name__)

_TIME_LIMIT_TO_GNEWS = {"d": "1d", "w": "7d", "m": "30d"}


def _build_query(config: SearchConfig) -> str:
    query = config.query
    if config.query_mode == "exact_phrase":
        query = f'"{query}"'
    elif config.query_mode == "all":
        # Google News RSS treats space-separated bare terms as implicit AND
        # already; being explicit costs nothing and documents intent.
        query = " AND ".join(query.split())
    # "any" mode: leave as-is, engine's default OR-ish relevance matching applies

    if config.exclude_terms:
        query += " " + " ".join(f"-{t}" for t in config.exclude_terms)

    # Custom date range (v1.0.2) takes precedence over the coarse
    # time_limit window — Google News RSS supports `after:`/`before:`
    # search operators with plain YYYY-MM-DD dates.
    if config.start_date or config.end_date:
        if config.start_date:
            query += f" after:{config.start_date}"
        if config.end_date:
            query += f" before:{config.end_date}"
    else:
        when = _TIME_LIMIT_TO_GNEWS.get(config.time_limit)
        if when:
            query += f" when:{when}"

    return query


def search_raw(config: SearchConfig, country: Optional[str] = None, language: Optional[str] = None) -> List[Dict]:
    """
    Query Google News RSS. Returns list of dicts:
    {title, url, source, published, description} with `url` still
    potentially a Google News redirect — decoding happens in the pipeline
    via fetch/url_resolver.py's native base64 decoder, not here.

    Args:
        config: SearchConfig (query, filters, optional start_date/end_date).
        country: ISO 3166-1 alpha-2 region code, e.g. "US", "IN", "GB".
            Controls Google News' `gl`/`ceid` locale params. Defaults to
            "US" when not given — see docs/parameters-reference.md for the
            full list of codes Google News recognizes.
        language: ISO 639-1 language code, e.g. "en", "hi". Controls the
            `hl`/`ceid` locale params. Defaults to "en".
    """
    query = _build_query(config)
    encoded = quote_plus(query)
    gl = (country or "US").upper()
    hl = f"{(language or 'en').lower()}-{gl}"
    ceid = f"{gl}:{(language or 'en').lower()}"
    feed_url = f"https://news.google.com/rss/search?q={encoded}&hl={hl}&gl={gl}&ceid={ceid}"

    results = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[: config.max_results * 2]:  # over-fetch for pipeline filtering
            link = entry.get("link", "")
            if not link:
                continue

            source = entry.get("source", {}).get("title", "")
            if not source and " - " in entry.get("title", ""):
                source = entry["title"].split(" - ")[-1]
            if not source:
                domain = urlparse(link).netloc
                source = domain.replace("www.", "").split(".")[0].title()

            results.append({
                "title": entry.get("title", "No title"),
                "url": resolve_url(link),
                "source": source or "Google News",
                "published": entry.get("published", ""),
                "description": entry.get("summary", "")[:500],
            })
        logger.info(f"Google News search('{query}') returned {len(results)} raw results")
    except Exception as e:
        logger.error(f"Google News search error for '{query}': {e}")

    return results