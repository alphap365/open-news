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
import re

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

# Last-resort in-body attribution phrases ("This story originally appeared
# on Reuters.", "— via Bloomberg"). Low precision by nature (free text, no
# structure to lean on) so this only runs after every structured signal
# (canonical/AMP link, og:url, JSON-LD, meta tags) has come up empty.
_IN_TEXT_ATTRIBUTION_RE = re.compile(
    r"(?:originally (?:appeared|published|ran)(?:\s+on| in| by)?|"
    r"first (?:appeared|published)(?:\s+on| in| by)?|"
    r"this (?:story|article|post) (?:appeared|was published)(?:\s+on| in| by)?|"
    r"—\s*via|—\s*courtesy of)\s+"
    r"([A-Z][A-Za-z0-9&.,'’\- ]{1,40}?)(?:[.,\n]|$)"
)
# Guard against capturing junk like "the" or a sentence fragment as a name.
_GENERIC_TOKENS = {"the", "this", "a", "an", "and", "read", "more", "here"}


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def is_aggregator_domain(url: str) -> bool:
    dom = _domain(url)
    return any(dom == a or dom.endswith(f".{a}") for a in AGGREGATOR_DOMAINS)


def _meta_content(doc: HtmlElement, name: str) -> Optional[str]:
    vals = doc.xpath(f'//meta[@name="{name}"]/@content | //meta[@property="{name}"]/@content')
    return vals[0].strip() if vals and vals[0].strip() else None


def _link_href(doc: HtmlElement, rel: str) -> Optional[str]:
    vals = doc.xpath(f'//link[@rel="{rel}"]/@href')
    return vals[0].strip() if vals and vals[0].strip() else None


def _domain_to_name(domain: str) -> str:
    """Best-effort human-readable name from a bare domain, e.g.
    'reuters.com' -> 'Reuters'. Used only when a URL-based signal (canonical/
    AMP/og:url) points off-domain but doesn't carry an explicit publisher
    name the way JSON-LD/meta tags sometimes do."""
    return domain.split(".")[0].replace("-", " ").title()


def _off_domain_candidate(url_or_domain: Optional[str], own_domain: str) -> Optional[str]:
    """Given a candidate URL (or bare domain) pulled from canonical/AMP/
    og:url tags, return its domain IF it's meaningfully different from the
    aggregator's own domain and isn't itself another known aggregator
    (which would just swap one aggregator label for another, not resolve
    to the actual original publisher)."""
    if not url_or_domain:
        return None
    candidate_domain = _domain(url_or_domain) if "://" in url_or_domain else url_or_domain.lower().replace("www.", "")
    if not candidate_domain or candidate_domain == own_domain:
        return None
    if is_aggregator_domain(f"https://{candidate_domain}"):
        return None
    return candidate_domain


def _in_text_attribution(doc: HtmlElement) -> Optional[str]:
    """Last-resort scan of the rendered text for phrases like 'This story
    originally appeared on Reuters.' Deliberately runs after every
    structured signal has failed — free text has no schema to lean on, so
    false positives are more likely here than anywhere else in the chain."""
    text = doc.text_content()
    if not text:
        return None
    # Only scan the first ~4000 chars: attribution lines are almost always
    # near the top (byline) or bottom (footer credit) of syndicated pages,
    # and scanning the whole article risks matching incidental prose.
    match = _IN_TEXT_ATTRIBUTION_RE.search(text[:4000]) or _IN_TEXT_ATTRIBUTION_RE.search(text[-2000:])
    if not match:
        return None
    name = match.group(1).strip().strip(".,'’-")
    if not name or name.lower() in _GENERIC_TOKENS or len(name) > 40:
        return None
    return name


def resolve_source(doc: HtmlElement, url: str, site_name: Optional[str], json_ld: Optional[Dict] = None) -> Dict:
    """
    Returns:
        {
          "source": str,            # best available name
          "is_aggregator": bool,    # url's domain is a known aggregator
          "resolved": bool,         # True if `source` is believed to be the
                                     # *original* publisher, not the aggregator
        }

    Resolution runs in priority order — stops at the first candidate that
    isn't just the aggregator's own name again:

      1. Canonical / AMP link (`<link rel="canonical"|"amphtml">`) pointing
         off-domain. A URL is unambiguous (no name-matching needed) and
         this is often exactly what it's for on syndicated pages.
      2. `og:url` pointing off-domain — same idea, weaker signal (more
         often just points back at the aggregator itself).
      3. JSON-LD `provider`/`sourceOrganization`/`copyrightHolder`.
      4. Publisher-ish meta tags (`article:publisher`, `parsely-source`, ...).
      5. In-body attribution text ("originally appeared on X") — last
         resort, free text, lowest precision.
    """
    dom = _domain(url)

    if not is_aggregator_domain(url):
        return {"source": site_name or dom, "is_aggregator": False, "resolved": True}

    aggregator_label = (site_name or dom).strip().lower()

    # 1 & 2: URL-based signals first — a resolved domain is more trustworthy
    # than a resolved *name*, since there's no ambiguity about whether it's
    # "the aggregator's name again" (we compare domains, not fuzzy strings).
    for rel in ("canonical", "amphtml"):
        off_domain = _off_domain_candidate(_link_href(doc, rel), dom)
        if off_domain:
            return {"source": _domain_to_name(off_domain), "is_aggregator": True, "resolved": True}

    off_domain = _off_domain_candidate(_meta_content(doc, "og:url"), dom)
    if off_domain:
        return {"source": _domain_to_name(off_domain), "is_aggregator": True, "resolved": True}

    # 3 & 4: existing name-based signals (JSON-LD, meta tags)
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

    # 5: in-text attribution, last resort
    text_cand = _in_text_attribution(doc)
    if text_cand and text_cand.lower() != aggregator_label:
        return {"source": text_cand, "is_aggregator": True, "resolved": True}

    # Honest fallback: we know it's an aggregator, but couldn't find the
    # real publisher. Report the aggregator's name rather than nothing,
    # but flag it so downstream code/UI can show "(via MSN)" instead of
    # presenting it as if MSN wrote the story.
    return {"source": site_name or dom, "is_aggregator": True, "resolved": False}