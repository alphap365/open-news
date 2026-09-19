"""Google News RSS engine for open-news.

Returns the same list-of-dicts shape as every other feed engine:

    {title, url, source, published, description}

``url`` may still be a Google News redirect when this function returns;
decoding happens lazily in the pipeline via
``fetch/url_resolver.resolve_url``. Callers who need a resolved URL
immediately can run the results through ``dedupe_articles`` or call
``resolve_url`` themselves.

Tiers
-----

1. ``feedparser.parse`` — the primary path. Fast, well-tested, and
   returns publish dates in ISO-8601 for free.
2. Pure-Python fallback (``_fallback.fetch_and_parse``) — httpx +
   stdlib/lxml XML parsing, used only when feedparser returns zero
   entries (a network hiccup, a malformed response, or an environment
   where feedparser's optional accelerators silently fail). Opt-in via
   ``OPEN_NEWS_GNEWS_PURE_FALLBACK=1`` to keep the default path
   byte-for-byte identical to the pre-split behaviour.

Package layout
--------------

  * ``_query``      — pure query-string builder (no I/O).
  * ``_fallback``   — httpx + XML fallback.
  * ``__init__``    — orchestrator and monkeypatch surface. Both
                      ``feedparser`` and ``resolve_url`` are bound here
                      and called from this module's globals so that
                      ``monkeypatch.setattr(googlenews_engine, ...)``
                      actually takes effect on ``search_raw``.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import feedparser

from ...config import SearchConfig
from ...fetch.url_resolver import resolve_url
from ._fallback import fetch_and_parse as _fetch_and_parse_pure
from ._query import _TIME_LIMIT_TO_GNEWS, _build_query  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)


def _pure_fallback_enabled() -> bool:
    return os.environ.get("OPEN_NEWS_GNEWS_PURE_FALLBACK") == "1"


def search_raw(
    config: SearchConfig,
    country: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict]:
    """
    Query Google News RSS. Returns list of dicts:
    {title, url, source, published, description} with `url` already
    passed through ``resolve_url`` (mirroring the pre-split behaviour).

    Args:
        config: SearchConfig (query, filters, optional start_date/end_date).
        country: ISO 3166-1 alpha-2 region code, e.g. "US", "IN", "GB".
            Controls Google News' `gl`/`ceid` locale params. Defaults to
            "US" when not given.
        language: ISO 639-1 language code, e.g. "en", "hi". Controls the
            `hl`/`ceid` locale params. Defaults to "en".
    """
    query = _build_query(config)
    encoded = quote_plus(query)
    gl = (country or "US").upper()
    hl = f"{(language or 'en').lower()}-{gl}"
    ceid = f"{gl}:{(language or 'en').lower()}"
    feed_url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded}&hl={hl}&gl={gl}&ceid={ceid}"
    )

    entries: List[Any] = []
    try:
        feed = feedparser.parse(feed_url)
        entries = list(feed.entries)
    except Exception as e:
        logger.error("Google News search error for %r: %s", query, e)

    if not entries and _pure_fallback_enabled():
        logger.info(
            "feedparser returned no entries for %r; trying pure-Python fallback",
            query,
        )
        try:
            entries = _fetch_and_parse_pure(feed_url)
        except Exception as e:  # noqa: BLE001
            logger.error("Pure-Python Google News fallback failed: %r", e)

    results = _normalize_entries(entries[: config.max_results * 2])
    logger.info("Google News search(%r) returned %d raw results", query, len(results))
    return results


def _normalize_entries(entries: List[Any]) -> List[Dict]:
    """Turn feedparser entries (or fallback-produced equivalents) into
    the engine's canonical dict shape, resolving Google News redirects.

    Lives in ``__init__`` on purpose: it calls the module-level
    ``resolve_url`` name, which is the same one tests monkeypatch via
    ``monkeypatch.setattr(googlenews_engine, 'resolve_url', ...)``.
    """
    results: List[Dict] = []
    for entry in entries:
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
    return results