"""Pure-Python re-creation of ``ddgs.news`` — no primp, no Rust.

Used by :mod:`open_news.feeds.duckduckgo_engine` when the native primp
backend and ``duckpy`` are both unavailable, and by anything that wants
a Termux-safe news scraper.

Backends, tried in order
------------------------

1. DuckDuckGo HTML endpoint (``html.duckduckgo.com/html/``). Stable
   markup; no dates in the results.
2. Bing News RSS (``bing.com/news/search?format=RSS``). Clean XML with
   ``pubDate`` and a per-item source element.

Both scrapers are pure Python: ``httpx`` for transport, ``lxml`` for
HTML/XML parsing when present, stdlib ``xml.etree`` otherwise.
"""

import html as _html
import logging
import re
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from lxml import html as lxml_html
except ImportError:  # pragma: no cover
    lxml_html = None  # type: ignore[assignment]

try:
    from lxml import etree as lxml_etree
except ImportError:  # pragma: no cover
    lxml_etree = None  # type: ignore[assignment]


# Reuse the engine's pure helpers so URL decoding and region handling
# behave identically regardless of tier.
from ._parsing import _decode_uddg, _region_param

logger = logging.getLogger(__name__)


_DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
_BING_RSS_ENDPOINT = "https://www.bing.com/news/search"

_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------

def search_news_pure(
    query: str,
    region: str = "us-en",
    safesearch: str = "moderate",
    timelimit: Optional[str] = None,
    max_results: int = 10,
    page: int = 1,
    proxy: Optional[str] = None,
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    """Pure-Python news search. DDG HTML first, Bing RSS second.

    Never raises on ordinary network/parse errors — returns ``[]`` so
    the caller can decide what to do.
    """
    if httpx is None:
        logger.warning("httpx is not installed; pure-Python news search unavailable")
        return []
    if not query:
        return []

    errors: List[str] = []
    results: List[Dict[str, Any]] = []

    try:
        results = _search_via_ddg_html(
            query=query, region=region, safesearch=safesearch,
            timelimit=timelimit, max_results=max_results, page=page,
            proxy=proxy, timeout=timeout,
        )
    except Exception as ex:  # noqa: BLE001
        errors.append(f"ddg-html: {ex!r}")
        logger.info("Pure news: DDG HTML failed: %r", ex)

    if not results:
        try:
            results = fetch_bing_rss(
                query=query, region=region, timelimit=timelimit,
                max_results=max_results, page=page,
                proxy=proxy, timeout=timeout,
            )
        except Exception as ex:  # noqa: BLE001
            errors.append(f"bing-rss: {ex!r}")
            logger.info("Pure news: Bing RSS failed: %r", ex)

    if not results and errors:
        logger.warning("Pure news search exhausted all fallbacks: %s", "; ".join(errors))

    return results[:max_results] if max_results else results


# ----------------------------------------------------------------------
# DDG HTML backend (returned records carry ``date=""`` — DDG has none)
# ----------------------------------------------------------------------

def _ddg_df(timelimit: Optional[str]) -> Optional[str]:
    return timelimit if timelimit in ("d", "w", "m", "y") else None


def _search_via_ddg_html(
    query: str,
    region: str,
    safesearch: str,
    timelimit: Optional[str],
    max_results: int,
    page: int,
    proxy: Optional[str],
    timeout: float,
) -> List[Dict[str, Any]]:
    if lxml_html is None:
        raise RuntimeError("lxml is required for the DDG HTML backend")

    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://duckduckgo.com/",
    }
    data: Dict[str, str] = {
        "q": query,
        "kl": _region_param(region),
        "kp": "-1" if safesearch == "off" else "1",
    }
    df = _ddg_df(timelimit)
    if df:
        data["df"] = df
    if page > 1:
        data["s"] = str((page - 1) * 30)

    with httpx.Client(
        proxy=proxy if proxy else None,
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        resp = client.post(_DDG_HTML_ENDPOINT, data=data)
        resp.raise_for_status()
        return _parse_ddg_html_rich(resp.text, max_results)


def _parse_ddg_html_rich(html_text: str, limit: int) -> List[Dict[str, Any]]:
    """Like ``_parsing._parse_ddg_html`` but returns the richer
    ``{date, title, body, url, image, source}`` schema used by the
    recreated DDGS.news surface."""
    if not html_text or lxml_html is None:
        return []
    try:
        doc = lxml_html.fromstring(html_text)
    except Exception as ex:  # noqa: BLE001
        logger.debug("DDG HTML parse error: %r", ex)
        return []

    results: List[Dict[str, Any]] = []
    for node in doc.xpath("//div[contains(@class, 'result')]"):
        title_a = node.xpath(".//a[contains(@class, 'result__a')]")
        if not title_a:
            continue
        title = title_a[0].text_content().strip()
        href = title_a[0].get("href", "")
        if not title or not href:
            continue
        real_url = _decode_uddg(href)
        if not real_url:
            continue

        snippet_el = (
            node.xpath(".//a[contains(@class, 'result__snippet')]")
            or node.xpath(".//div[contains(@class, 'result__snippet')]")
            or node.xpath(".//span[contains(@class, 'result__snippet')]")
        )
        snippet = snippet_el[0].text_content().strip() if snippet_el else ""

        netloc = urlparse(real_url).netloc.replace("www.", "")
        results.append({
            "date": _guess_date(snippet),
            "title": title,
            "body": snippet[:500],
            "url": real_url,
            "image": "",
            "source": netloc,
        })
        if len(results) >= limit:
            break
    return results


# ----------------------------------------------------------------------
# Bing News RSS backend
# ----------------------------------------------------------------------

def _bing_market(region: Optional[str]) -> str:
    if not region or region == "wt-wt":
        return "en-US"
    if "-" not in region:
        return f"en-{region.upper()}"
    lang, country = region.split("-", 1)
    return f"{lang}-{country.upper()}"


def _bing_qft(timelimit: Optional[str]) -> Optional[str]:
    return {
        "d": 'interval="4"',
        "w": 'interval="7"',
        "m": 'interval="9"',
        "y": 'interval="9"',
    }.get(timelimit or "")


def fetch_bing_rss(
    query: str,
    region: str = "us-en",
    timelimit: Optional[str] = None,
    max_results: int = 10,
    page: int = 1,
    proxy: Optional[str] = None,
    timeout: float = 20.0,
) -> List[Dict[str, Any]]:
    """Bing News RSS tier — public so it can be reached by name from
    ``__init__._fetch_via_bing_rss`` without importing a private helper."""
    if httpx is None:
        return []
    headers = {
        "User-Agent": _DEFAULT_UA,
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    params: Dict[str, str] = {
        "q": query,
        "format": "RSS",
        "mkt": _bing_market(region),
    }
    qft = _bing_qft(timelimit)
    if qft:
        params["qft"] = qft
    if page > 1:
        params["first"] = str((page - 1) * 10 + 1)

    with httpx.Client(
        proxy=proxy if proxy else None,
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        resp = client.get(_BING_RSS_ENDPOINT, params=params)
        resp.raise_for_status()
        return _parse_bing_rss(resp.text, max_results)


def _parse_bing_rss(xml_text: str, limit: int) -> List[Dict[str, Any]]:
    if not xml_text:
        return []

    root = None
    if lxml_etree is not None:
        try:
            parser = lxml_etree.XMLParser(recover=True, resolve_entities=False)
            root = lxml_etree.fromstring(xml_text.encode("utf-8"), parser=parser)
        except Exception as ex:  # noqa: BLE001
            logger.debug("Bing RSS lxml parse failed: %r", ex)

    if root is None:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
        except Exception as ex:  # noqa: BLE001
            logger.debug("Bing RSS ET parse failed: %r", ex)
            return []

    results: List[Dict[str, Any]] = []
    for item in root.iter():
        tag = item.tag if isinstance(item.tag, str) else ""
        if not tag.endswith("item"):
            continue

        title = _child_text(item, "title")
        link = _child_text(item, "link")
        description = _child_text(item, "description")
        pub_date = _child_text(item, "pubDate")
        source = (
            _child_text(item, "Source")
            or urlparse(link).netloc.replace("www.", "")
        )
        if not title or not link:
            continue

        results.append({
            "date": _rfc822_to_iso(pub_date),
            "title": title,
            "body": _strip_html(description)[:500],
            "url": link,
            "image": "",
            "source": source,
        })
        if len(results) >= limit:
            break
    return results


def _child_text(node: Any, tag_suffix: str) -> str:
    for child in node:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag.endswith(tag_suffix):
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
    except Exception:  # noqa: BLE001
        return value


# ----------------------------------------------------------------------
# Misc helpers
# ----------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_DATE_HINT_RE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"(?:\s+\d{4})?|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)


def _strip_html(text: str) -> str:
    if not text:
        return ""
    return _html.unescape(_TAG_RE.sub("", text)).strip()


def _guess_date(text: str) -> str:
    if not text:
        return ""
    m = _DATE_HINT_RE.search(text)
    return m.group(1).strip() if m else ""