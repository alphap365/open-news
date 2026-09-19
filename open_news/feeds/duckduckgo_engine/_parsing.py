"""Pure URL / HTML helpers for the DuckDuckGo engine.

Nothing here makes a network call or reads global state; these functions
are safe to import and call from any tier.
"""

import logging
from typing import Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from lxml.html import fromstring

from ...fetch.url_resolver import (
    aggregator_domain_name,
    is_aggregator_source,
    is_hub_url,
    resolve_url,
)

logger = logging.getLogger(__name__)


def _region_param(location: Optional[str]) -> str:
    """DDG expects region codes like 'us-en', 'in-en', or 'wt-wt'.
    Config gives us something like 'us' or 'wt-wt'. Normalize."""
    if not location or location == "wt-wt":
        return "wt-wt"
    return location if "-" in location else f"{location}-en"


def _decode_uddg(href: str) -> str:
    """Decode DDG's ``//duckduckgo.com/l/?uddg=<urlencoded>&rut=...``
    wrapper. Returns href unchanged if it isn't wrapped."""
    if not href:
        return ""

    if href.startswith("//"):
        href = "https:" + href

    if "uddg=" not in href:
        return href

    try:
        parsed = urlparse(href)
        vals = parse_qs(parsed.query).get("uddg")
        if vals:
            return unquote(vals[0])
    except Exception:
        pass

    return href


def _finalize_url(url: str) -> Optional[str]:
    """Shared post-processing for a raw hit URL from any tier: resolve
    Google News redirects, then reject the result entirely if what we
    end up with is a known hub/listing page. Returns None to drop."""
    if not url:
        return None
    real_url = resolve_url(url)
    if is_hub_url(real_url):
        logger.debug("Dropping hub/listing page (not an article): %s", real_url)
        return None
    return real_url


def _parse_ddg_html(html: str, limit: int) -> List[Dict]:
    """Extract engine-schema result dicts from a DDG HTML response.

    DDG wraps each result in a div whose class contains "result"; the
    title and snippet anchors carry stable class names (result__a,
    result__snippet)."""
    try:
        doc = fromstring(html)
    except Exception as e:
        logger.warning("DDG HTML parse error: %s", e)
        return []

    results: List[Dict] = []
    dropped_hubs = 0

    for node in doc.xpath("//div[contains(@class, 'result')]"):
        title_a = node.xpath(".//a[contains(@class, 'result__a')]")
        if not title_a:
            continue

        title = title_a[0].text_content().strip()
        href = title_a[0].get("href", "")
        raw_url = _decode_uddg(href)

        if not title or not raw_url:
            continue

        real_url = _finalize_url(raw_url)
        if not real_url:
            dropped_hubs += 1
            continue

        snippet_el = (
            node.xpath(".//a[contains(@class, 'result__snippet')]")
            or node.xpath(".//div[contains(@class, 'result__snippet')]")
            or node.xpath(".//span[contains(@class, 'result__snippet')]")
        )
        snippet = snippet_el[0].text_content().strip() if snippet_el else ""

        agg_name = aggregator_domain_name(real_url)
        source = agg_name or urlparse(real_url).netloc.replace("www.", "")

        entry = {
            "title": title,
            "url": real_url,
            "source": source,
            "published": "",
            "description": snippet[:500],
        }
        if agg_name or is_aggregator_source(source):
            entry["_aggregator_source"] = True
        results.append(entry)

        if len(results) >= limit:
            break

    if dropped_hubs:
        logger.info("DDG HTML: dropped %d hub/listing pages", dropped_hubs)

    return results