"""
Best-effort resolution of the *original publisher* for articles served
through a syndication aggregator (MSN, Yahoo News, etc.) rather than the
outlet's own domain.

This is explicitly best-effort, not guaranteed correct: aggregators change
their markup without notice, and there's no universal standard for "who
actually wrote this" on a syndicated page. What this module does instead
of silently guessing wrong:

  1. Maintains a known list of aggregator domains.
  2. On an aggregator page, checks a short list of meta tags / JSON-LD
     fields that *sometimes* carry the real publisher's name.
  3. If a plausible name is found (and it isn't just the aggregator's own
     name again), uses it and marks the result as resolved.
  4. If nothing is found, still reports the aggregator's name (better than
     an empty string) but flags `resolved=False` so callers/consumers know
     this is the distributor, not necessarily the original publisher.

Callers should treat `is_aggregator=True, resolved=False` as "source is a
best guess" rather than ground truth.
"""

from typing import Dict, Optional
from urllib.parse import urlparse

from lxml.html import HtmlElement

# Known syndication/aggregation platforms that host other outlets' stories
# under their own domain. Not exhaustive -- add to this as new cases show up.
AGGREGATOR_DOMAINS = {
    "msn.com",
    "news.yahoo.com",
    "yahoo.com",
    "news.google.com",
    "flipboard.com",
    "apple.news",
    "smartnews.com",
    "news.yandex.com",
    "newsbreak.com",
}

# Meta tag names that occasionally carry the original publisher on an
# aggregator-hosted page. Checked in this priority order.
_PUBLISHER_META_NAMES = [
    "article:publisher",
    "parsely-source",
    "analyticsattributes.arc_provider",
    "provider",
    "syndication-source",
    "original-source",
]

# JSON-LD keys that sometimes name the original publisher separately from
# whatever `publisher` the aggregator stamps on every page it serves.
_JSON_LD_PROVIDER_KEYS = ("provider", "sourceOrganization", "copyrightHolder")


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def is_aggregator_domain(url: str) -> bool:
    dom = _domain(url)
    return any(dom == a or dom.endswith(f".{a}") for a in AGGREGATOR_DOMAINS)


def _meta_content(doc: HtmlElement, name: str) -> Optional[str]:
    vals = doc.xpath(f'//meta[@name="{name}"]/@content | //meta[@property="{name}"]/@content')
    return vals[0].strip() if vals and vals[0].strip() else None


def resolve_source(doc: HtmlElement, url: str, site_name: Optional[str], json_ld: Optional[Dict] = None) -> Dict:
    """
    Returns:
        {
          "source": str,            # best available name
          "is_aggregator": bool,    # url's domain is a known aggregator
          "resolved": bool,         # True if `source` is believed to be the
                                     # *original* publisher, not the aggregator
        }
    """
    dom = _domain(url)

    if not is_aggregator_domain(url):
        return {"source": site_name or dom, "is_aggregator": False, "resolved": True}

    aggregator_label = (site_name or dom).strip().lower()
    candidates = []

    if json_ld:
        for key in _JSON_LD_PROVIDER_KEYS:
            val = json_ld.get(key)
            name = val.get("name") if isinstance(val, dict) else val if isinstance(val, str) else None
            if name:
                candidates.append(name.strip())

    for meta_name in _PUBLISHER_META_NAMES:
        val = _meta_content(doc, meta_name)
        if val:
            candidates.append(val)

    for cand in candidates:
        if cand and cand.lower() != aggregator_label:
            return {"source": cand, "is_aggregator": True, "resolved": True}

    # Honest fallback: we know it's an aggregator, but couldn't find the
    # real publisher. Report the aggregator's name rather than nothing,
    # but flag it so downstream code/UI can show "(via MSN)" instead of
    # presenting it as if MSN wrote the story.
    return {"source": site_name or dom, "is_aggregator": True, "resolved": False}