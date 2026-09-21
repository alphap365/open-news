"""Bing News engine — HTML first, RSS second.

Both tiers are pure Python: httpx for transport, lxml for parsing. The
HTML tier needs the ``_EDGE_CD``/``_EDGE_S`` cookies a real Bing session
sets and returns article-level results with relative dates. The RSS tier
is slower but always available and carries ISO-8601 dates.
"""

import html as _html
import logging
import os
import re
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

try:
    import lxml.etree as _lxml_etree
    import lxml.html as _lxml_html
except ImportError:
    _lxml_etree = None
    _lxml_html = None

_lxml_etree = _lxml_etree if _lxml_etree is not None else None
_lxml_html = _lxml_html if _lxml_html is not None else None

from ..config import FetchConfig
from ..fetch.url_resolver import (
    aggregator_domain_name, is_aggregator_source, is_hub_url, resolve_url,
)
from ..utils.httpx_compat import make_client

logger = logging.getLogger(__name__)


_CATEGORY_TO_QUERY = {
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

_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = 20.0
_HTML_ENDPOINT = "https://www.bing.com/news/infinitescrollajax"
_RSS_ENDPOINT = "https://www.bing.com/news/search"
_TIER = "bing"

_REL_DATE_RE = re.compile(
    r"\b(\d+)\s*(minute|hour|day|week|month|year)s?\b", re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _skip() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_BING_NEWS") == "1"


def _query_for(config: FetchConfig) -> str:
    base = _CATEGORY_TO_QUERY.get(config.category, "news today")
    loc = (config.location or "").strip()
    if loc and loc != "wt-wt":
        region = _REGION_NAME.get(loc.lower().split("-")[0], loc.upper())
        return f"{region} {base}"
    return base


def _country_lang(location: Optional[str]) -> tuple[str, str]:
    """Parse '<country>' or '<country>-<lang>' (e.g. 'in', 'in-en').

    Returns (country, lang), both lowercase. Falls back to ('us', 'en')
    for None / 'wt-wt'.
    """
    if not location or location == "wt-wt":
        return "us", "en"
    if "-" in location:
        country, lang = location.split("-", 1)
        return country.lower(), lang.lower()
    return location.lower(), "en"


def _qft(timelimit: Optional[str]) -> Optional[str]:
    return {
        "d": 'interval="7"', "w": 'interval="8"',
        "m": 'interval="9"', "y": 'interval="9"',
    }.get(timelimit or "")


# ----------------------------------------------------------------------
# Public
# ----------------------------------------------------------------------

def fetch_raw(config: FetchConfig) -> List[Dict]:
    if _skip():
        logger.info("OPEN_NEWS_SKIP_BING_NEWS set; skipping")
        return []

    results = _fetch_via_html(config)
    if results:
        return results
    logger.info("Bing News HTML empty; trying Bing News RSS")
    return _fetch_via_rss(config)


def _fetch_via_html(config: FetchConfig) -> List[Dict]:
    if _lxml_html is None:
        return []

    country, lang = _country_lang(config.location)
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{lang}-{country.upper()},{lang};q=0.9",
        "Referer": "https://www.bing.com/news",
    }
    cookies = {
        "_EDGE_CD": f"m={lang}-{country}&u={lang}-{country}",
        "_EDGE_S": f"mkt={lang}-{country}&ui={lang}-{country}",
    }
    params: Dict[str, str] = {
        "q": _query_for(config),
        "InfiniteScroll": "1", "first": "1", "SFX": "1",
        "cc": country, "setlang": lang,
    }
    qft = _qft(config.time_limit)
    if qft:
        params["qft"] = qft

    try:
        with make_client(
            proxy=None, timeout=_TIMEOUT, follow_redirects=True, headers=headers,
        ) as client:
            resp = client.get(_HTML_ENDPOINT, params=params, cookies=cookies)
            resp.raise_for_status()
            html_text = resp.text
    except Exception as e:
        logger.warning("Bing News HTML fetch failed: %s", e)
        return []

    return _parse_html_results(html_text, config.max_results * 2)


def _parse_html_results(html_text: str, limit: int) -> List[Dict]:
    if not html_text or _lxml_html is None:
        return []
    try:
        tree = _lxml_html.fromstring(html_text)
    except Exception as e:
        logger.debug("Bing HTML parse failed: %r", e)
        return []

    results: List[Dict] = []
    nodes = cast(List[Any], tree.xpath("//div[contains(@class, 'newsitem')]") )
    for node in nodes:
        title = node.get("data-title", "").strip()
        raw_url = node.get("url", "").strip()
        source = node.get("data-author", "").strip()
        if not title or not raw_url:
            continue

        real_url = _finalize_url(raw_url)
        if not real_url:
            continue

        date_attrs = node.xpath(".//span[@aria-label]//@aria-label")
        body_parts = node.xpath(".//div[@class='snippet']//text()")
        body = " ".join(p.strip() for p in body_parts if p.strip())[:500]

        if not source:
            agg = aggregator_domain_name(real_url)
            source = agg or urlparse(real_url).netloc.replace("www.", "")

        entry: Dict[str, Any] = {
            "title": title, "url": real_url, "source": source,
            "published": _parse_relative_date(date_attrs[0] if date_attrs else ""),
            "description": body, "_tier": _TIER,
        }
        if is_aggregator_source(source):
            entry["_aggregator_source"] = True
        results.append(entry)
        if len(results) >= limit:
            break
    return results


def _parse_relative_date(value: str) -> str:
    if not value:
        return ""
    from datetime import datetime, timedelta, timezone
    m = _REL_DATE_RE.search(value)
    if not m:
        return value
    n = int(m.group(1))
    unit = m.group(2).lower()
    delta = {
        "minute": timedelta(minutes=n), "hour": timedelta(hours=n),
        "day": timedelta(days=n), "week": timedelta(weeks=n),
        "month": timedelta(days=30 * n), "year": timedelta(days=365 * n),
    }[unit]
    return (datetime.now(timezone.utc) - delta).replace(microsecond=0).isoformat()


def _fetch_via_rss(config: FetchConfig) -> List[Dict]:
    country, lang = _country_lang(config.location)
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    }
    params: Dict[str, str] = {
        "q": _query_for(config), "format": "RSS",
        "mkt": f"{lang}-{country.upper()}",
    }
    qft = _qft(config.time_limit)
    if qft:
        params["qft"] = qft

    try:
        with make_client(
            proxy=None, timeout=_TIMEOUT, follow_redirects=True, headers=headers,
        ) as client:
            resp = client.get(_RSS_ENDPOINT, params=params)
            resp.raise_for_status()
            xml_text = resp.text
    except Exception as e:
        logger.warning("Bing News RSS fetch failed: %s", e)
        return []

    return _parse_rss_results(xml_text, config.max_results * 2)


def _parse_rss_results(xml_text: str, limit: int) -> List[Dict]:
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

    results: List[Dict] = []
    for item in root.iter():
        tag = item.tag if isinstance(item.tag, str) else ""
        if not tag.endswith("item"):
            continue
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not title or not link:
            continue
        real_url = _finalize_url(link)
        if not real_url:
            continue

        pub = _child_text(item, "pubDate")
        desc = _child_text(item, "description")
        source = _child_text(item, "Source") or urlparse(real_url).netloc.replace("www.", "")

        entry: Dict[str, Any] = {
            "title": title, "url": real_url, "source": source,
            "published": _rfc822_to_iso(pub),
            "description": _strip_html(desc)[:500], "_tier": _TIER,
        }
        if is_aggregator_source(source):
            entry["_aggregator_source"] = True
        results.append(entry)
        if len(results) >= limit:
            break
    return results


def _finalize_url(url: str) -> Optional[str]:
    if not url:
        return None
    real_url = resolve_url(url)
    if is_hub_url(real_url):
        logger.debug("Bing dropped hub page: %s", real_url)
        return None
    return real_url


def _child_text(node: Any, tag_suffix: str) -> str:
    for child in node:
        t = child.tag if isinstance(child.tag, str) else ""
        if t.endswith(tag_suffix):
            return (child.text or "").strip()
    return ""


def _rfc822_to_iso(value: str) -> str:
    if not value:
        return ""
    try:
        from datetime import timezone
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def _strip_html(text: str) -> str:
    return _html.unescape(_TAG_RE.sub("", text)).strip() if text else ""