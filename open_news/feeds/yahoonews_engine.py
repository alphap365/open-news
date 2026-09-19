"""Yahoo News engine.

Yahoo News is a Bing white-label: the results are Bing's index through
Yahoo's front-end, which is more permissive about clients than Bing's
own HTML endpoint. Result URLs are wrapped as
``.../RU=<urlencoded>/RK=.../RS=...`` and dates arrive as relative
strings ("2 hours ago"); both are normalized here.

Pure Python: httpx for transport, lxml for parsing.
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import unquote_plus, urlparse

try:
    from lxml import html as _lxml_html
except ImportError:
    _lxml_html = None

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
_SEARCH_URL = "https://news.search.yahoo.com/search"
_TIER = "yahoo"

_REL_DATE_RE = re.compile(
    r"\b(\d+)\s*(minute|hour|day|week|month|year)s?\b", re.IGNORECASE,
)


def _skip() -> bool:
    return os.environ.get("OPEN_NEWS_SKIP_YAHOO_NEWS") == "1"


def _query_for(config: FetchConfig) -> str:
    base = _CATEGORY_TO_QUERY.get(config.category, "news today")
    loc = (config.location or "").strip()
    if loc and loc != "wt-wt":
        region = _REGION_NAME.get(loc.lower().split("-")[0], loc.upper())
        return f"{region} {base}"
    return base


def fetch_raw(config: FetchConfig) -> List[Dict]:
    if _skip():
        logger.info("OPEN_NEWS_SKIP_YAHOO_NEWS set; skipping")
        return []
    if _lxml_html is None:
        logger.info("lxml not installed; Yahoo News tier unavailable")
        return []

    params = {"p": _query_for(config)}
    if config.time_limit in ("d", "w", "m", "y"):
        params["btf"] = config.time_limit

    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://news.search.yahoo.com/",
    }

    try:
        with make_client(
            proxy=None, timeout=_TIMEOUT, follow_redirects=True, headers=headers,
        ) as client:
            resp = client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
            html_text = resp.text
    except Exception as e:
        logger.warning("Yahoo News fetch failed: %s", e)
        return []

    results = _parse_yahoo_html(html_text, config.max_results * 2)
    logger.info("Yahoo News returned %d results", len(results))
    return results


def _parse_yahoo_html(html_text: str, limit: int) -> List[Dict]:
    if not html_text or _lxml_html is None:
        return []
    try:
        tree = _lxml_html.fromstring(html_text)
    except Exception as e:
        logger.debug("Yahoo News parse failed: %r", e)
        return []

    results: List[Dict] = []
    # FIX: the link lives inside <h4>, not as a direct child of <li>,
    # so the old `li[a]` predicate matched nothing.
    for node in tree.xpath("//div[@id='web']//li[.//h4/a]"):
        title_parts = node.xpath(".//h4//text()")
        title = " ".join(t.strip() for t in title_parts if t.strip())
        if not title:
            continue

        link_attrs = node.xpath(".//h4/a/@href")
        if not link_attrs:
            continue
        real_url = _finalize_url(_unwrap_yahoo_url(link_attrs[0]))
        if not real_url:
            continue

        body_parts = node.xpath(".//p//text()")
        body = " ".join(b.strip() for b in body_parts if b.strip())[:500]

        date_attrs = node.xpath(".//span[contains(@class, 'time')]//text()")
        published = _parse_relative_date(date_attrs[0] if date_attrs else "")

        source_attrs = node.xpath(".//span[contains(@class, 'source')]//text()")
        source = source_attrs[0].strip() if source_attrs else ""
        source = source.split(" ·  via Yahoo", 1)[0].strip()
        if not source:
            agg = aggregator_domain_name(real_url)
            source = agg or urlparse(real_url).netloc.replace("www.", "")

        entry = {
            "title": title, "url": real_url, "source": source,
            "published": published, "description": body, "_tier": _TIER,
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
        logger.debug("Yahoo dropped hub page: %s", real_url)
        return None
    return real_url


def _unwrap_yahoo_url(u: str) -> str:
    if "/RU=" not in u:
        return u
    try:
        return unquote_plus(u.split("/RU=", 1)[1].split("/RK=", 1)[0].split("?", 1)[0])
    except Exception:
        return u


def _parse_relative_date(value: str) -> str:
    if not value:
        return ""
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