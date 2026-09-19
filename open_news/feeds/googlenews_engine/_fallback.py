"""Pure-Python RSS fetch + parse fallback.

Used by :func:`search_raw` when ``feedparser.parse()`` comes back with
no entries — either because it silently swallowed a network hiccup,
choked on a slightly malformed XML response, or because the caller is
on a platform where feedparser's optional accelerators misbehave.

Returns entries in the *feedparser entry* shape (``title``, ``link``,
``published``, ``summary``, ``source={'title': ...}``) so the caller's
existing :func:`_normalize_entries` can consume them unchanged.

No primp, no Rust: ``httpx`` for transport, stdlib ``xml.etree`` for
parsing. ``lxml`` is used when available purely as a faster parser.
"""

import logging
import re
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

try:
    from lxml import etree as lxml_etree
except ImportError:  # pragma: no cover
    lxml_etree = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


_DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<[^>]+>")


def fetch_and_parse(
    feed_url: str,
    *,
    timeout: float = 20.0,
    proxy: Optional[str] = None,
    max_items: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch ``feed_url`` and return a list of feedparser-shaped entries.

    Never raises on ordinary network / parse failures — returns ``[]``
    so the caller can decide what to do.
    """
    if httpx is None:
        logger.info("httpx not installed; pure-Python Google News fallback unavailable")
        return []

    try:
        with httpx.Client(
            proxy=proxy if proxy else None,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            resp = client.get(feed_url)
            resp.raise_for_status()
            xml_text = resp.text
    except Exception as ex:  # noqa: BLE001
        logger.info("Pure-Python Google News fetch failed: %r", ex)
        return []

    return _parse_rss(xml_text, max_items=max_items)


def _parse_rss(xml_text: str, *, max_items: int) -> List[Dict[str, Any]]:
    if not xml_text:
        return []

    root = None
    if lxml_etree is not None:
        try:
            parser = lxml_etree.XMLParser(recover=True, resolve_entities=False)
            root = lxml_etree.fromstring(xml_text.encode("utf-8"), parser=parser)
        except Exception as ex:  # noqa: BLE001
            logger.debug("Google News lxml parse failed: %r", ex)

    if root is None:
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)
        except Exception as ex:  # noqa: BLE001
            logger.debug("Google News ET parse failed: %r", ex)
            return []

    entries: List[Dict[str, Any]] = []
    for item in root.iter():
        tag = item.tag if isinstance(item.tag, str) else ""
        if not tag.endswith("item"):
            continue

        title = _child_text(item, "title")
        link = _child_text(item, "link")
        pub_date = _child_text(item, "pubDate")
        description = _child_text(item, "description")
        source_title = ""
        for child in item:
            child_tag = child.tag if isinstance(child.tag, str) else ""
            if child_tag.endswith("source"):
                source_title = (child.text or "").strip()
                break

        if not title or not link:
            continue

        entries.append({
            "title": title,
            "link": link,
            "published": _rfc822_to_iso(pub_date),
            # feedparser maps <description> → entry.summary; keep the same
            # name so _normalize_entries doesn't need a branch.
            "summary": _strip_html(description),
            # feedparser exposes the source as a dict-like object with a
            # `title` key; a plain dict matches that shape.
            "source": {"title": source_title} if source_title else {},
        })
        if len(entries) >= max_items:
            break

    return entries


def _child_text(node: Any, tag_suffix: str) -> str:
    for child in node:
        tag = child.tag if isinstance(child.tag, str) else ""
        if tag.endswith(tag_suffix):
            return (child.text or "").strip()
    return ""


def _rfc822_to_iso(value: str) -> str:
    """Normalize a pubDate to ISO-8601 UTC so it matches feedparser's
    ``entry.published`` format. Falls back to the raw string on failure."""
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


def _strip_html(text: str) -> str:
    if not text:
        return ""
    import html as _html
    return _html.unescape(_TAG_RE.sub("", text)).strip()