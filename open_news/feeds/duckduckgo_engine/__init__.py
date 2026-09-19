"""DuckDuckGo news engine for open-news.

Returns the same list-of-dicts shape regardless of which backend produced
the results:

    {title, url, source, published, description}

Backend selection (three tiers, tried in order):

1. ``ddgs`` — the native DuckDuckGo client (primp-based). Best quality:
   publish dates, source names, structured results.
2. ``duckpy`` — a small, pure-Python DuckDuckGo client built on httpx.
   No compiled extensions, Termux-safe, tried before the manual scraper.
3. Manual pure-Python fallback chain — DDG HTML scraper, then Bing News
   RSS. No primp, no Rust: safe on Termux/Android.

The public module name is preserved so that
``from open_news.feeds import duckduckgo_engine`` and
``from open_news.feeds.duckduckgo_engine import fetch_raw`` both keep
working after the split into this package.

Package layout
--------------

  * ``_parsing``       — pure URL / HTML helpers (no I/O, no side effects).
  * ``_fallback_news`` — the pure-Python "recreated DDGS.news"
                         (DDG HTML + Bing RSS), used as the final tier.
  * ``__init__``       — orchestrator, escape hatches, and every name
                         the original module exposed. Anything that
                         tests monkeypatch lives here so that rebinding
                         via the package attribute actually takes effect
                         on ``fetch_raw``.
"""

import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from ...config import FetchConfig
from ...fetch.url_resolver import (
    aggregator_domain_name,
    is_aggregator_source,
    is_hub_url,
    resolve_url,
)
from ...utils.user_agents import USER_AGENTS, get_user_agent

# Re-exports: keep the old single-file API intact.
from ._parsing import (
    _decode_uddg,
    _finalize_url,
    _parse_ddg_html,
    _region_param,
)
from ._fallback_news import (
    search_news_pure as _search_news_pure,
    fetch_bing_rss as _fetch_bing_rss_impl,
)

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

_CATEGORY_TO_DDG_QUERY = {
    "general": "news",
    "business": "business",
    "tech": "technology",
    "sports": "sports",
    "health": "health",
    "science": "science",
    "entertainment": "entertainment",
}

_DEFAULT_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_HTML_ENDPOINT = os.environ.get("OPEN_NEWS_DDG_HTML_ENDPOINT", _DEFAULT_HTML_ENDPOINT)

_RETRIES = 3
_TIMEOUT = 20.0
_MAX_RETRY_WAIT = 8.0


# ----------------------------------------------------------------------
# Escape hatches
# ----------------------------------------------------------------------

def _is_termux() -> bool:
    """Detect Termux at call time (not import time), so tests can
    monkeypatch this function directly instead of racing module import."""
    return bool(os.environ.get("TERMUX_VERSION")) or os.path.isdir(
        "/data/data/com.termux"
    )


def _try_ddgs_on_termux() -> bool:
    return os.environ.get("OPEN_NEWS_TRY_DDGS_ON_TERMUX") == "1"


def _skip_duckpy() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_DUCKPY") == "1"


def _force_fallback() -> bool:
    return os.environ.get("OPEN_NEWS_FORCE_DDG_FALLBACK") == "1"


def _use_pure_ddgs_fallback() -> bool:
    """When the native ``ddgs`` import fails, also try the pure-Python
    recreation instead of returning an empty list immediately.

    Off by default so a native-import failure does not silently start
    scraping the DDG HTML endpoint from a caller that expected the
    network-free "return []" contract of the old module. Turn on with
    ``OPEN_NEWS_DDGS_PURE_FALLBACK=1`` once you've decided you want it.
    """
    return os.environ.get("OPEN_NEWS_DDGS_PURE_FALLBACK") == "1"


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def fetch_raw(config: FetchConfig) -> List[Dict]:
    """
    Query DuckDuckGo for a category or location feed.

    Tries, in order: ddgs -> duckpy -> fallback chain (DDG HTML, Bing RSS).
    Returns as soon as a tier yields results. Returns list of dicts:
    {title, url, source, published, description} — same shape regardless
    of which tier actually ran.
    """
    if _force_fallback():
        logger.info("OPEN_NEWS_FORCE_DDG_FALLBACK set; using fallback chain")
        return _fetch_via_fallback_chain(config)

    skip_ddgs = _is_termux() and not _try_ddgs_on_termux()
    if skip_ddgs:
        logger.info(
            "ddgs skipped on Termux (set OPEN_NEWS_TRY_DDGS_ON_TERMUX=1 to override); "
            "trying duckpy next"
        )
    else:
        results = _try_ddgs(config)
        if results:
            return results
        logger.info("ddgs returned no results; trying duckpy next")

    if not _skip_duckpy():
        results = _try_duckpy(config)
        if results:
            return results
        logger.info("duckpy returned no results; falling back to fallback chain")
    else:
        logger.info("OPEN_NEWS_SKIP_DUCKPY set; going straight to fallback chain")

    return _fetch_via_fallback_chain(config)


# ----------------------------------------------------------------------
# Backend 1: ddgs (native, has publish dates)
# ----------------------------------------------------------------------

def _try_ddgs(config: FetchConfig) -> List[Dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # deprecated fallback name
        except ImportError:
            logger.info("ddgs / duckduckgo_search not installed")
            if _use_pure_ddgs_fallback():
                logger.info(
                    "OPEN_NEWS_DDGS_PURE_FALLBACK set; using pure-Python recreated DDGS.news"
                )
                return _try_ddgs_pure(config)
            return []

    keywords = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = _region_param(config.location)

    results: List[Dict] = []
    dropped_hubs = 0
    try:
        with DDGS() as ddgs:
            hits = ddgs.news(
                query=keywords,
                region=region,
                timelimit=config.time_limit,
                max_results=config.max_results * 2,  # over-fetch; pipeline filters
            )
            for hit in hits:
                real_url = _finalize_url(hit.get("url", ""))
                if not real_url:
                    dropped_hubs += 1
                    continue
                source = hit.get("source", "Unknown")
                entry = {
                    "title": hit.get("title", "No title"),
                    "url": real_url,
                    "source": source,
                    "published": hit.get("date", ""),
                    "description": (hit.get("body") or "")[:500],
                }
                if is_aggregator_source(source):
                    entry["_aggregator_source"] = True
                results.append(entry)
        logger.info(
            "ddgs fetch(%r) returned %d usable results (%d hub/listing pages dropped)",
            keywords, len(results), dropped_hubs,
        )
    except Exception as e:
        logger.error("ddgs fetch error for %r: %s", keywords, e)
        return []

    return results


def _try_ddgs_pure(config: FetchConfig) -> List[Dict]:
    """Pure-Python re-creation of ``DDGS.news`` — DDG HTML first, then
    Bing News RSS. No primp, no Rust. Only reached when the native
    package isn't importable *and* ``OPEN_NEWS_DDGS_PURE_FALLBACK=1``."""
    keywords = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = _region_param(config.location)
    raw = _search_news_pure(
        query=keywords,
        region=region,
        safesearch="moderate",
        timelimit=config.time_limit,
        max_results=config.max_results * 2,
        page=1,
        proxy=None,
        timeout=_TIMEOUT,
    )
    return _normalize_pure_news(raw)


# ----------------------------------------------------------------------
# Backend 2: duckpy (pure-Python/httpx, no dates, Termux-safe)
# ----------------------------------------------------------------------

def _try_duckpy(config: FetchConfig) -> List[Dict]:
    try:
        from duckpy import Client
    except ImportError:
        logger.info("duckpy not installed")
        return []

    keywords = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    limit = config.max_results * 2

    results: List[Dict] = []
    dropped_hubs = 0
    try:
        client = Client(default_user_agents=USER_AGENTS)
        hits = client.search(keywords)
        for hit in hits[:limit]:
            raw_url = getattr(hit, "url", "") or ""
            title = getattr(hit, "title", "") or "No title"
            description = getattr(hit, "description", "") or ""
            real_url = _finalize_url(raw_url)
            if not real_url:
                dropped_hubs += 1
                continue
            agg_name = aggregator_domain_name(real_url)
            source = agg_name or urlparse(real_url).netloc.replace("www.", "")
            entry = {
                "title": title,
                "url": real_url,
                "source": source,
                "published": "",
                "description": description[:500],
            }
            if agg_name or is_aggregator_source(source):
                entry["_aggregator_source"] = True
            results.append(entry)
        logger.info(
            "duckpy fetch(%r) returned %d usable results (%d hub/listing pages dropped)",
            keywords, len(results), dropped_hubs,
        )
    except Exception as e:
        logger.error("duckpy fetch error for %r: %s", keywords, e)
        return []

    return results


# ----------------------------------------------------------------------
# Backend 3: fallback chain — DDG HTML, then Bing RSS
# ----------------------------------------------------------------------

def _fetch_via_fallback_chain(config: FetchConfig) -> List[Dict]:
    """Ordered fallback: DDG HTML scraper first, Bing News RSS second.

    ``_fetch_via_ddg_html`` keeps its name and signature from the old
    single-file module so any existing test that monkeypatches it
    continues to intercept the first tier of this chain.
    """
    results = _fetch_via_ddg_html(config)
    if results:
        return results
    logger.info("DDG HTML tier returned no results; trying Bing News RSS")
    return _fetch_via_bing_rss(config)


def _fetch_via_ddg_html(config: FetchConfig) -> List[Dict]:
    query = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = _region_param(config.location)
    df = config.time_limit  # 'd' | 'w' | 'm' — DDG's df param accepts the same

    headers = {
        "User-Agent": get_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
    }
    data = {
        "q": query,
        "kl": region,
        "df": df,
        "kp": "-1",
    }

    last_err: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            with httpx.Client(
                follow_redirects=True, timeout=_TIMEOUT, headers=headers
            ) as client:
                resp = client.post(_HTML_ENDPOINT, data=data)

                if resp.status_code == 202:
                    wait = min(2.0 ** attempt, _MAX_RETRY_WAIT)
                    logger.warning(
                        "DDG HTML rate limit (202); retrying in %.1fs", wait
                    )
                    _sleep(wait)
                    continue

                resp.raise_for_status()
                parsed = _parse_ddg_html(resp.text, config.max_results * 2)
                logger.info(
                    "DDG HTML fetch(%r) returned %d raw results",
                    query, len(parsed),
                )
                return parsed

        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code == 202 and attempt < _RETRIES - 1:
                wait = min(2.0 ** attempt, _MAX_RETRY_WAIT)
                _sleep(wait)
                continue
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            last_err = e
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
            _sleep(0.5)

    logger.error("DDG HTML scraper exhausted retries: %s", last_err)
    return []


def _fetch_via_bing_rss(config: FetchConfig) -> List[Dict]:
    """Thin wrapper around the pure-Python Bing News RSS scraper living
    in ``_fallback_news``. Adapter keeps this tier mockable at the
    package level without touching ``_fallback_news`` internals."""
    query = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = _region_param(config.location)
    raw = _fetch_bing_rss_impl(
        query=query,
        region=region,
        timelimit=config.time_limit,
        max_results=config.max_results * 2,
        page=1,
        proxy=None,
        timeout=_TIMEOUT,
    )
    return _normalize_pure_news(raw)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------

def _normalize_pure_news(raw: List[Dict]) -> List[Dict]:
    """Convert ``_fallback_news``'s richer records into the engine's
    canonical shape, applying the same hub-drop / aggregator-flag logic
    as the native tiers."""
    out: List[Dict] = []
    for item in raw:
        real_url = _finalize_url(item.get("url", ""))
        if not real_url:
            continue
        source = item.get("source") or urlparse(real_url).netloc.replace("www.", "")
        entry = {
            "title": item.get("title", "No title"),
            "url": real_url,
            "source": source,
            # _fallback_news returns RFC822-derived ISO dates when it has
            # them; the engine's schema names the field ``published``.
            "published": item.get("date", "") or "",
            "description": (item.get("body") or "")[:500],
        }
        if is_aggregator_source(source):
            entry["_aggregator_source"] = True
        out.append(entry)
    return out


def _sleep(seconds: float) -> None:
    """Indirection so tests can patch sleeping without importing time."""
    import time
    time.sleep(seconds)