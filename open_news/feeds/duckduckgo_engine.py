"""DuckDuckGo engine + news-fetch orchestrator.

This module is the entry point for ``open_news.api.fetch()``. It runs a
five-tier fallback chain, returning as soon as a tier yields results:

  1. ddgs (native primp)  — fast, has dates; skipped on Termux.
  2. Google News RSS      — pure Python, real ISO dates.
  3. Bing News            — HTML then RSS; pure Python.
  4. Yahoo News HTML      — pure Python, relative dates.
  5. DDG HTML scraper     — general web search, last resort.

Escape hatches (all default off):
    OPEN_NEWS_TRY_DDGS_ON_TERMUX=1   Try ddgs on Termux anyway.
    OPEN_NEWS_SKIP_DDGS=1            Skip tier 1.
    OPEN_NEWS_SKIP_GOOGLE_NEWS=1     Skip tier 2.
    OPEN_NEWS_SKIP_BING_NEWS=1       Skip tier 3 (read by bingnews_engine).
    OPEN_NEWS_SKIP_YAHOO_NEWS=1      Skip tier 4 (read by yahoonews_engine).
    OPEN_NEWS_SKIP_DDG_HTML=1        Skip tier 5.
    OPEN_NEWS_DDG_HTML_ENDPOINT=<url> Override DDG HTML endpoint.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Any, cast
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..config import FetchConfig
from ..fetch.url_resolver import (
    aggregator_domain_name, is_aggregator_source, is_hub_url, resolve_url,
)
from ..utils.user_agents import get_user_agent
from . import bingnews_engine, googlenews_engine, yahoonews_engine

try:
    from lxml.html import fromstring as _lxml_fromstring
except ImportError:
    _lxml_fromstring = None

logger = logging.getLogger(__name__)


_CATEGORY_TO_DDG_QUERY = {
    "general": "breaking news today",
    "business": "business news today",
    "tech": "technology news today",
    "sports": "sports news today",
    "health": "health news today",
    "science": "science news today",
    "entertainment": "entertainment news today",
}

_REGION_NAME = {
    "in": "India", "us": "US", "gb": "UK", "uk": "UK",
    "au": "Australia", "ca": "Canada", "nz": "New Zealand",
    "pk": "Pakistan", "bd": "Bangladesh", "lk": "Sri Lanka",
}

_DEFAULT_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_HTML_ENDPOINT = os.environ.get("OPEN_NEWS_DDG_HTML_ENDPOINT", _DEFAULT_HTML_ENDPOINT)

_RETRIES = 3
_TIMEOUT = 20.0
_MAX_RETRY_WAIT = 8.0
_TIER = "ddg_html"


# ----------------------------------------------------------------------
# Escape hatches
# ----------------------------------------------------------------------

def _is_termux() -> bool:
    return bool(os.environ.get("TERMUX_VERSION")) or os.path.isdir("/data/data/com.termux")


def _try_ddgs_on_termux() -> bool:
    return os.environ.get("OPEN_NEWS_TRY_DDGS_ON_TERMUX") == "1"


def _skip_ddgs() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_DDGS") == "1"


def _skip_google_news() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_GOOGLE_NEWS") == "1"


def _skip_ddg_html() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_DDG_HTML") == "1"


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def fetch_raw(config: FetchConfig) -> List[Dict]:
    """Category/location news via the five-tier chain."""
    # Tier 1 — ddgs
    if _skip_ddgs() or (_is_termux() and not _try_ddgs_on_termux()):
        logger.info("Tier 1 (ddgs) skipped: %s",
                    "env" if _skip_ddgs() else "Termux")
    else:
        results = _try_ddgs(config)
        if results:
            logger.info("Tier 1 (ddgs) returned %d results", len(results))
            return results
        logger.info("Tier 1 (ddgs) empty; trying Google News")

    # Tier 2 — Google News
    if not _skip_google_news():
        try:
            results = googlenews_engine.fetch_raw(config)
            if results:
                logger.info("Tier 2 (Google News) returned %d results", len(results))
                return results
            logger.info("Tier 2 (Google News) empty; trying Bing News")
        except Exception as e:
            logger.warning("Tier 2 (Google News) failed: %r", e)
    else:
        logger.info("Tier 2 (Google News) skipped: env")

    # Tier 3 — Bing News
    try:
        results = bingnews_engine.fetch_raw(config)
        if results:
            logger.info("Tier 3 (Bing News) returned %d results", len(results))
            return results
        logger.info("Tier 3 (Bing News) empty; trying Yahoo News")
    except Exception as e:
        logger.warning("Tier 3 (Bing News) failed: %r", e)

    # Tier 4 — Yahoo News
    try:
        results = yahoonews_engine.fetch_raw(config)
        if results:
            logger.info("Tier 4 (Yahoo News) returned %d results", len(results))
            return results
        logger.info("Tier 4 (Yahoo News) empty; trying DDG HTML")
    except Exception as e:
        logger.warning("Tier 4 (Yahoo News) failed: %r", e)

    # Tier 5 — DDG HTML
    if _skip_ddg_html():
        logger.info("Tier 5 (DDG HTML) skipped: env")
        return []
    results = _fetch_via_ddg_html(config)
    logger.info("Tier 5 (DDG HTML) returned %d results", len(results))
    return results


# ----------------------------------------------------------------------
# Tier 1: ddgs
# ----------------------------------------------------------------------

def _try_ddgs(config: FetchConfig) -> List[Dict]:
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.info("ddgs not installed")
            return []

    query = _ddg_query(config)
    region = _region_param(config.location)

    try:
        with DDGS() as ddgs:
            hits = ddgs.news(
                query=query, region=region,
                timelimit=config.time_limit,
                max_results=config.max_results * 2,
            )
    except Exception as e:
        logger.warning("ddgs fetch failed: %s", e)
        return []

    results: List[Dict] = []
    for hit in hits:
        real_url = _finalize_url(hit.get("url", ""))
        if not real_url:
            continue
        source = hit.get("source", "Unknown")
        entry: Dict[str, Any] = {
            "title": hit.get("title", "No title"),
            "url": real_url, "source": source,
            "published": hit.get("date", ""),
            "description": (hit.get("body") or "")[:500],
            "_tier": "ddgs",
        }
        if is_aggregator_source(source):
            entry["_aggregator_source"] = True
        results.append(entry)
    return results


# ----------------------------------------------------------------------
# Tier 5: DDG HTML
# ----------------------------------------------------------------------

def _fetch_via_ddg_html(config: FetchConfig) -> List[Dict]:
    if _lxml_fromstring is None:
        logger.info("lxml not installed; DDG HTML tier unavailable")
        return []

    query = _ddg_query(config)
    region = _region_param(config.location)
    df = config.time_limit

    headers = {
        "User-Agent": get_user_agent(),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
    }
    data = {
        "q": query, "kl": region, "df": df, "kp": "-1",
        "ia": "news", "iar": "news",
    }

    last_err: Optional[Exception] = None
    for attempt in range(_RETRIES):
        try:
            with httpx.Client(
                follow_redirects=True, timeout=_TIMEOUT, headers=headers,
            ) as client:
                resp = client.post(_HTML_ENDPOINT, data=data)

                if resp.status_code == 202:
                    wait = min(2.0 ** attempt, _MAX_RETRY_WAIT)
                    logger.warning("DDG HTML rate limit; retrying in %.1fs", wait)
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                parsed = _parse_ddg_html(resp.text, config.max_results * 2)
                logger.info("DDG HTML fetch(%r) returned %d results", query, len(parsed))
                return parsed

        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code == 202 and attempt < _RETRIES - 1:
                time.sleep(min(2.0 ** attempt, _MAX_RETRY_WAIT))
                continue
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
        except Exception as e:
            last_err = e
            logger.warning("DDG HTML attempt %d failed: %s", attempt + 1, e)
            time.sleep(0.5)

    logger.error("DDG HTML exhausted retries: %s", last_err)
    return []


def _parse_ddg_html(html_text: str, limit: int) -> List[Dict]:
    if not html_text or _lxml_fromstring is None:
        return []
    try:
        doc = _lxml_fromstring(html_text)
    except Exception as e:
        logger.warning("DDG HTML parse error: %s", e)
        return []

    results: List[Dict] = []
    result_nodes = cast(
        List[Any], doc.xpath("//div[contains(@class, 'result')]")
    )
    for node in result_nodes:
        title_a = node.xpath(".//a[contains(@class, 'result__a')]")
        if not title_a:
            continue
        title = title_a[0].text_content().strip()
        raw_url = _decode_uddg(title_a[0].get("href", ""))
        if not title or not raw_url:
            continue
        real_url = _finalize_url(raw_url)
        if not real_url:
            continue

        snippet_el = (
            node.xpath(".//a[contains(@class, 'result__snippet')]")
            or node.xpath(".//div[contains(@class, 'result__snippet')]")
            or node.xpath(".//span[contains(@class, 'result__snippet')]")
        )
        snippet = snippet_el[0].text_content().strip() if snippet_el else ""

        agg = aggregator_domain_name(real_url)
        source = agg or urlparse(real_url).netloc.replace("www.", "")

        entry = {
            "title": title, "url": real_url, "source": source,
            "published": "", "description": snippet[:500], "_tier": _TIER,
        }
        if agg or is_aggregator_source(source):
            entry["_aggregator_source"] = True
        results.append(entry)
        if len(results) >= limit:
            break
    return results


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------

def _region_param(location: Optional[str]) -> str:
    if not location or location == "wt-wt":
        return "wt-wt"
    return location if "-" in location else f"{location}-en"


def _ddg_query(config: FetchConfig) -> str:
    base = _CATEGORY_TO_DDG_QUERY.get(config.category, "news today")
    loc = (config.location or "").strip()
    if loc and loc != "wt-wt":
        region = _REGION_NAME.get(loc.lower().split("-")[0], loc.upper())
        return f"{region} {base}"
    return base


def _finalize_url(url: str) -> Optional[str]:
    if not url:
        return None
    real_url = resolve_url(url)
    if is_hub_url(real_url):
        logger.debug("Dropped hub/listing page: %s", real_url)
        return None
    return real_url


def _decode_uddg(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "uddg=" not in href:
        return href
    try:
        vals = parse_qs(urlparse(href).query).get("uddg")
        if vals:
            return unquote(vals[0])
    except Exception:
        pass
    return href