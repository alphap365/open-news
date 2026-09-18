"""DuckDuckGo news engine for open-news.

Returns the same list-of-dicts shape regardless of which backend produced
the results:

    {title, url, source, published, description}

so downstream code (pipeline.py, api.py, config.py) stays unchanged.

Backend selection (three tiers, tried in order)
-------------------------------------------------

1. ``ddgs`` — the native DuckDuckGo search client. Best quality: has
   publish dates, source names, structured results. Used when available
   and when the process will survive the call (see Termux caveat below).

2. ``duckpy`` — a small, pure-Python DuckDuckGo client built on ``httpx``.
   No compiled extensions, no Rust runtime, so it is safe on Termux where
   ``ddgs`` is not. Has no publish date and no region/time filtering, but
   is meaningfully more robust than hand-parsing HTML and is tried before
   falling all the way back to the manual scraper.

3. ``httpx``-based DuckDuckGo HTML scraper — pure Python, no dependency
   beyond ``httpx`` + ``lxml``. Last resort: used when both ``ddgs`` and
   ``duckpy`` are unavailable, raise, or return nothing.

Termux caveat
-------------

On Termux/Android, ``ddgs`` v7+ pulls in ``primp``, a Rust-based HTTP
client that calls ``ndk-context`` at runtime. Termux never initializes
that context, so the first network call panics with
``android context was not initialized`` and the Rust runtime raises
``SIGABRT``. This **terminates the process** — it cannot be caught by
``try/except``. To avoid dying before any fallback can run, this module
detects Termux at call time and skips the ``ddgs`` attempt entirely.

``duckpy`` has no such issue (it's httpx all the way down), so it is
attempted on every platform, including Termux, and is the primary
Termux path rather than a last resort there.

Escape hatches (environment variables)
---------------------------------------

    OPEN_NEWS_TRY_DDGS_ON_TERMUX=1
        Try ``ddgs`` even on Termux. Useful if a future release drops
        ``primp``, or for testing on a device where the panic doesn't
        reproduce. If it panics, the process still dies — that's your
        signal to unset the variable.

    OPEN_NEWS_SKIP_DUCKPY=1
        Skip the ``duckpy`` tier entirely and go straight from ``ddgs``
        (or its Termux skip) to the manual HTML scraper. Useful for
        testing the scraper fallback in isolation.

    OPEN_NEWS_FORCE_DDG_FALLBACK=1
        Force the manual httpx/lxml scraper on every platform, skipping
        both ``ddgs`` and ``duckpy`` entirely. Useful for testing the
        last-resort path without uninstalling anything.

    OPEN_NEWS_DDG_HTML_ENDPOINT=<url>
        Override the DuckDuckGo HTML endpoint (default:
        ``https://html.duckduckgo.com/html/``). Useful if the default
        gets blocked or if you want to point at a mirror.
"""

import logging
import os
import time
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from lxml.html import fromstring

from ..config import FetchConfig
from ..utils.user_agents import USER_AGENTS, get_user_agent

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


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def fetch_raw(config: FetchConfig) -> List[Dict]:
    """
    Query DuckDuckGo for a category or location feed.

    Tries, in order: ddgs -> duckpy -> manual HTML scraper. Returns as
    soon as a tier yields results. Returns list of dicts:
    {title, url, source, published, description} — same shape
    regardless of which tier actually ran.
    """
    if _force_fallback():
        logger.info("OPEN_NEWS_FORCE_DDG_FALLBACK set; using manual HTML scraper")
        return _fetch_via_ddg_html(config)

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
        logger.info("duckpy returned no results; falling back to HTML scraper")
    else:
        logger.info("OPEN_NEWS_SKIP_DUCKPY set; going straight to HTML scraper")

    return _fetch_via_ddg_html(config)


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
            return []

    keywords = _CATEGORY_TO_DDG_QUERY.get(config.category, "news")
    region = _region_param(config.location)

    results: List[Dict] = []
    try:
        with DDGS() as ddgs:
            hits = ddgs.news(
                query=keywords,
                region=region,
                timelimit=config.time_limit,
                max_results=config.max_results * 2,  # over-fetch; pipeline filters
            )
            for hit in hits:
                results.append({
                    "title": hit.get("title", "No title"),
                    "url": hit.get("url", ""),
                    "source": hit.get("source", "Unknown"),
                    "published": hit.get("date", ""),
                    "description": (hit.get("body") or "")[:500],
                })
        logger.info(
            "ddgs fetch(%r) returned %d raw results", keywords, len(results)
        )
    except Exception as e:
        # Ordinary Python exceptions (ImportError, network errors) are
        # catchable here. SIGABRT is not — hence the pre-check in fetch_raw.
        logger.error("ddgs fetch error for %r: %s", keywords, e)
        return []

    return [r for r in results if r["url"]]


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
    try:
        # Hand duckpy the whole UA pool rather than one pre-picked string —
        # it randomizes per .search() call internally, same spirit as
        # get_user_agent() being called fresh for each HTML-scraper request.
        client = Client(default_user_agents=USER_AGENTS)
        hits = client.search(keywords)
        for hit in hits[:limit]:
            url = getattr(hit, "url", "") or ""
            title = getattr(hit, "title", "") or "No title"
            description = getattr(hit, "description", "") or ""
            if not url:
                continue
            results.append({
                "title": title,
                "url": url,
                "source": urlparse(url).netloc.replace("www.", ""),
                "published": "",  # duckpy has no date field
                "description": description[:500],
            })
        logger.info(
            "duckpy fetch(%r) returned %d raw results", keywords, len(results)
        )
    except Exception as e:
        # duckpy is pure Python/httpx — ordinary exceptions only, no
        # Termux SIGABRT risk, so a plain try/except is sufficient here.
        logger.error("duckpy fetch error for %r: %s", keywords, e)
        return []

    return results


# ----------------------------------------------------------------------
# Backend 3: DuckDuckGo HTML scraper (pure Python, no dates)
# ----------------------------------------------------------------------

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
        "kp": "-1",  # moderate safe search
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
                    time.sleep(wait)
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
                time.sleep(wait)
                continue
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            last_err = e
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
            time.sleep(0.5)

    logger.error("DDG HTML scraper exhausted retries: %s", last_err)
    return []


def _parse_ddg_html(html: str, limit: int) -> List[Dict]:
    """
    Extract result dicts from a DDG HTML search response.

    DDG wraps each result in a div whose class contains "result"; the
    title and snippet anchors carry stable class names (result__a,
    result__snippet). Both have been stable for years, but DDG does
    occasionally shuffle the surrounding markup — the class-based
    selectors are chosen to survive the most common variations.
    """
    try:
        doc = fromstring(html)
    except Exception as e:
        logger.warning("DDG HTML parse error: %s", e)
        return []

    results: List[Dict] = []

    for node in doc.xpath("//div[contains(@class, 'result')]"):
        title_a = node.xpath(".//a[contains(@class, 'result__a')]")
        if not title_a:
            continue

        title = title_a[0].text_content().strip()
        href = title_a[0].get("href", "")
        url = _decode_uddg(href)

        if not title or not url:
            continue

        snippet_el = (
            node.xpath(".//a[contains(@class, 'result__snippet')]")
            or node.xpath(".//div[contains(@class, 'result__snippet')]")
            or node.xpath(".//span[contains(@class, 'result__snippet')]")
        )
        snippet = snippet_el[0].text_content().strip() if snippet_el else ""

        source = urlparse(url).netloc.replace("www.", "")

        results.append({
            "title": title,
            "url": url,
            "source": source,
            "published": "",  # DDG HTML has no date; ranker handles missing
            "description": snippet[:500],
        })

        if len(results) >= limit:
            break

    return results


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _region_param(location: Optional[str]) -> str:
    """DDG expects region codes like 'us-en', 'in-en', or 'wt-wt'.
    Config gives us something like 'us' or 'wt-wt'. Normalize."""
    if not location or location == "wt-wt":
        return "wt-wt"
    return location if "-" in location else f"{location}-en"


def _decode_uddg(href: str) -> str:
    """
    DuckDuckGo wraps result URLs in a redirect of the form
    ``//duckduckgo.com/l/?uddg=<urlencoded>&rut=...``. Extract the real
    destination from the uddg parameter. Returns href unchanged if it's
    already a direct URL or the parameter is missing.
    """
    if not href:
        return ""

    # Normalize protocol-relative URLs first, so urlparse can handle them.
    if href.startswith("//"):
        href = "https:" + href

    if "uddg=" not in href:
        return href

    try:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        vals = qs.get("uddg")
        if vals:
            return unquote(vals[0])
    except Exception:
        pass

    return href