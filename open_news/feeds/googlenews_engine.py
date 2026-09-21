"""Google News RSS engine.

Two public entry points, same canonical dict shape from both:

  * ``search_raw(config, country, language)`` — backs ``api.search()``.
  * ``fetch_raw(config)`` — backs ``api.fetch()`` (category / location).

Pure Python: feedparser for RSS, httpx + lxml for the opt-in fallback.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus, urlparse
from concurrent.futures import ThreadPoolExecutor

import feedparser
import httpx

try:
    import lxml.etree as _lxml_etree
except ImportError:
    _lxml_etree = None

from ..config import FetchConfig, SearchConfig
from ..fetch.url_resolver import resolve_url
from ..utils.httpx_compat import make_client

logger = logging.getLogger(__name__)


_TIME_LIMIT_TO_GNEWS = {"d": "1d", "w": "7d", "m": "30d"}

_GNEWS_TOPIC = {
    "business": "BUSINESS", "tech": "TECHNOLOGY", "sports": "SPORTS",
    "health": "HEALTH", "science": "SCIENCE", "entertainment": "ENTERTAINMENT",
}

_REGION_NAME = {
    "in": "India", "us": "US", "gb": "UK", "uk": "UK",
    "au": "Australia", "ca": "Canada", "nz": "New Zealand",
    "pk": "Pakistan", "bd": "Bangladesh", "lk": "Sri Lanka",
}

_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = 20.0
_TIER = "google"


def _pure_fallback_enabled() -> bool:
    return os.environ.get("OPEN_NEWS_GNEWS_PURE_FALLBACK") == "1"


def _locale_params(country: Optional[str], language: Optional[str]) -> str:
    gl = (country or "US").upper()
    lang = (language or "en").lower()
    hl = f"{lang}-{gl}"
    # FIX: URL-encode the colon so the query string is ceid=IN%3Ahi
    ceid = quote(f"{gl}:{lang}", safe="")
    return f"hl={hl}&gl={gl}&ceid={ceid}"


def _region_name(location: Optional[str]) -> str:
    if not location or location == "wt-wt":
        return ""
    return _REGION_NAME.get(location.lower().split("-")[0], location.upper())


# ----------------------------------------------------------------------
# Public: keyword search
# ----------------------------------------------------------------------

def search_raw(
    config: SearchConfig,
    country: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict]:
    query = _build_search_query(config)
    feed_url = (
        f"https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&{_locale_params(country, language)}"
    )
    entries = _fetch_entries(feed_url)
    results = _normalize_entries(entries[: config.max_results * 2])
    logger.info("Google News search(%r) returned %d raw results", query, len(results))
    return results


_QUERY_TOKEN_RE = re.compile(r'"[^"]+"|\S+')


def _quote_if_needed(term: str) -> str:
    term = term.strip().strip('"').replace('"', "")
    return f'"{term}"' if re.search(r"\s", term) else term


def _build_search_query(config: SearchConfig) -> str:
    terms = _QUERY_TOKEN_RE.findall(config.query)
    if config.query_mode == "exact_phrase":
        query = '"' + config.query.replace('"', "").strip() + '"'
    elif config.query_mode == "all" or len(terms) <= 1:
        query = " ".join(terms)                      # implicit AND
    else:  # "any": a bare space means AND to Google, so OR must be explicit
        query = "(" + " OR ".join(terms) + ")"

    if config.exclude_terms:
        query += " " + " ".join(
            f"-{_quote_if_needed(t)}" for t in config.exclude_terms if t and t.strip()
        )

    if config.start_date or config.end_date:
        if config.start_date:
            query += f" after:{config.start_date}"
        if config.end_date:
            # `before:` is exclusive; the CLI/docs promise an inclusive end date.
            end_date = config.end_date
            if isinstance(end_date, datetime):
                end = end_date.date()
            elif isinstance(end_date, date):
                end = end_date
            else:
                end = date.fromisoformat(end_date)
            end += timedelta(days=1)
            query += f" before:{end.isoformat()}"
    else:
        when = _TIME_LIMIT_TO_GNEWS.get(config.time_limit)
        if when:
            query += f" when:{when}"
    return query


# ----------------------------------------------------------------------
# Public: category / location feed
# ----------------------------------------------------------------------

def _locale_from_location(location: Optional[str]) -> str:
    """'in' -> India/en, 'in-hi' -> India/hi, None or 'wt-wt' -> US/en."""
    if not location or location == "wt-wt":
        return _locale_params(None, None)
    parts = location.lower().split("-")
    country = parts[0]
    lang = parts[1] if len(parts) > 1 else "en"
    return _locale_params(country, lang)


def fetch_raw(config: FetchConfig) -> List[Dict]:
    category = (config.category or "").lower().strip()
    location = (config.location or "").lower().strip()
    locale = _locale_from_location(location)
    topic = _GNEWS_TOPIC.get(category)
    has_location = bool(location) and location != "wt-wt"

    if topic and has_location:
        region = _region_name(location)
        query = f"{region} {category} news"
        feed_url = (
            f"https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&{locale}"
        )
    elif topic:
        feed_url = (
            f"https://news.google.com/rss/headlines/section/topic/{topic}?{locale}"
        )
    else:
        # General news, with or without a location. The locale carries the
        # country (gl=IN etc.), so no geo/ path is needed.
        feed_url = f"https://news.google.com/rss?{locale}"

    entries = _fetch_entries(feed_url)
    results = _normalize_entries(entries[: config.max_results * 2])
    logger.info("Google News category feed returned %d raw results", len(results))
    return results


# ----------------------------------------------------------------------
# Internal
# ----------------------------------------------------------------------

def _fetch_entries(feed_url: str) -> List[Any]:
    try:
        feed = feedparser.parse(feed_url)
        entries = list(feed.entries)
    except Exception as e:
        logger.error("Google News feedparser failed: %s", e)
        entries = []

    if not entries and _pure_fallback_enabled():
        try:
            entries = _fetch_and_parse_pure(feed_url)
        except Exception as e:
            logger.error("Pure-Python Google News fetch failed: %r", e)
    return entries


def _normalize_entries(entries: List[Any]) -> List[Dict]:
    entries = [e for e in entries if e.get("link")]
    if not entries:
        return []

    # Decode redirects concurrently; pool.map preserves input order.
    with ThreadPoolExecutor(max_workers=4) as pool:
        urls = list(pool.map(lambda e: resolve_url(e["link"]), entries))

    results: List[Dict] = []
    for entry, real_url in zip(entries, urls):
        link = entry["link"]

        source = entry.get("source", {}).get("title", "")
        if not source and " - " in entry.get("title", ""):
            source = entry["title"].split(" - ")[-1]
        if not source:
            source = urlparse(link).netloc.replace("www.", "").split(".")[0].title()

        results.append({
            "title": entry.get("title", "No title"),
            "url": real_url,
            "source": source or "Google News",
            "published": entry.get("published", ""),
            "description": entry.get("summary", "")[:500],
            "_tier": _TIER,
        })
    return results


def _fetch_and_parse_pure(feed_url: str) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    with make_client(proxy=None, timeout=_TIMEOUT, follow_redirects=True, headers=headers) as c:
        resp = c.get(feed_url)
        resp.raise_for_status()
        return _parse_rss(resp.text, max_items=200)


def _parse_rss(xml_text: str, *, max_items: int) -> List[Dict[str, Any]]:
    if not xml_text:
        return []
    root = None
    if _lxml_etree is not None:
        try:
            parser = _lxml_etree.XMLParser(recover=True, resolve_entities=False)
            root = _lxml_etree.fromstring(xml_text.encode("utf-8"), parser=parser)
        except Exception:
            pass
    if root is None:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
        except Exception:
            return []

    out: List[Dict[str, Any]] = []
    for item in root.iter():
        tag = item.tag if isinstance(item.tag, str) else ""
        if not tag.endswith("item"):
            continue
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not title or not link:
            continue
        source_title = ""
        for child in item:
            t = child.tag if isinstance(child.tag, str) else ""
            if t.endswith("source"):
                source_title = (child.text or "").strip()
                break
        out.append({
            "title": title, "link": link,
            "published": _child_text(item, "pubDate"),
            "summary": _child_text(item, "description"),
            "source": {"title": source_title} if source_title else {},
        })
        if len(out) >= max_items:
            break
    return out


def _child_text(node: Any, tag_suffix: str) -> str:
    for child in node:
        t = child.tag if isinstance(child.tag, str) else ""
        if t.endswith(tag_suffix):
            return (child.text or "").strip()
    return ""