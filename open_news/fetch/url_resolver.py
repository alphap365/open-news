"""URL resolution and classification.

Two roles:

  1. Resolve Google News redirect URLs to their real destination.
  2. Classify URLs that are not articles (homepages, listing pages) and
     flag wire-service / aggregator sources. Used by every feed engine
     to drop junk before it reaches the pipeline.
"""

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

try:
    from googlenewsdecoder import new_decoderv1
except ImportError:
    new_decoderv1 = None

logger = logging.getLogger(__name__)

_ARTICLE_QUERY_KEYS = ("p", "page_id", "article", "story", "newsid", "nid", "aid")
# ----------------------------------------------------------------------
# Google News redirect resolution
# ----------------------------------------------------------------------

GOOGLE_NEWS_DOMAINS = {"news.google.com"}


def is_google_news_url(url: str) -> bool:
    if not url:
        return False
    try:
        return urlparse(url).netloc.lower() in GOOGLE_NEWS_DOMAINS
    except Exception:
        return False


def resolve_url(url: str) -> str:
    """Decode a Google News redirect. Returns url unchanged otherwise.
    Never raises."""
    if not is_google_news_url(url):
        return url
    if not new_decoderv1:
        logger.debug("googlenewsdecoder not installed, using raw URL")
        return url
    try:
        result = new_decoderv1(url)
        decoded = result.get("decoded_url") if result else None
        return decoded or url
    except Exception as e:
        logger.debug("Decoder error for %s: %s", url, e)
        return url


def clean_url(url: str) -> str:
    """Resolve Google News redirects if present. Callers that also care
    about hub pages should check is_hub_url() on the result."""
    if not url:
        return url
    if is_google_news_url(url):
        return resolve_url(url)
    return url


# ----------------------------------------------------------------------
# Aggregator / wire-service detection
# ----------------------------------------------------------------------

AGGREGATOR_SOURCE_NAMES = {
    "google news", "ap news", "associated press", "reuters",
    "yahoo news", "msn", "msn news", "flipboard",
    "news break", "newsbreak", "smartnews",
}

AGGREGATOR_DOMAINS = {
    "news.google.com": "Google News",
    "apnews.com": "AP News",
    "reuters.com": "Reuters",
    "news.yahoo.com": "Yahoo News",
    "msn.com": "MSN",
    "flipboard.com": "Flipboard",
    "newsbreak.com": "NewsBreak",
    "smartnews.com": "SmartNews",
}


def _netloc(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_aggregator_source(source: Optional[str]) -> bool:
    """True if `source` names a wire service / aggregator."""
    if not source:
        return False
    return source.strip().lower() in AGGREGATOR_SOURCE_NAMES


def aggregator_domain_name(url: str) -> Optional[str]:
    """Return the canonical display name for a known aggregator domain,
    or None. For engines that only have a bare netloc to work with."""
    return AGGREGATOR_DOMAINS.get(_netloc(url))


# ----------------------------------------------------------------------
# Hub / listing page detection
# ----------------------------------------------------------------------

# Two kinds of non-article URLs:
#   1. Bare-domain homepages (any path == "" or "/").
#   2. Domain-specific listing patterns. Extend as new offenders appear.
_HUB_PATH_PATTERNS = {
    "apnews.com": (r"^/hub/", r"^/tag/"),
    "news.google.com": (r"^/topics/", r"^/rss/?$"),
    "reuters.com": (r"^/topic/", r"^/section/"),
    "news.yahoo.com": (r"^/topic/", r"^/rss/?$"),
    "flipboard.com": (r"^/topic/",),
    "msn.com": (r"^/en-us/news/other/?$", r"^/en-us/news/?$"),
    "abplive.com": (r"^/live", r"^/live-tv", r"^/tv"),
    "zeenews.india.com": (r"^/live", r"^/live-tv", r"^/tv"),
}

_COMPILED_HUB_PATTERNS = {
    d: [re.compile(p) for p in pats] for d, pats in _HUB_PATH_PATTERNS.items()
}


def is_hub_url(url: str) -> bool:
    """True if `url` is a listing / hub / homepage rather than a single
    article. Engines should drop these at fetch time."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    path = parsed.path or "/"
    if path in ("", "/"):
        # WordPress-style plain permalinks (/?p=123) are articles, not homepages.
        if any(k in parse_qs(parsed.query) for k in _ARTICLE_QUERY_KEYS):
            return False
        return True
    
    patterns = _COMPILED_HUB_PATTERNS.get(_netloc(url))
    if not patterns:
        return False
    return any(p.match(path) for p in patterns)
