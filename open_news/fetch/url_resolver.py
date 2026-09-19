import logging
import re
from typing import Optional
from urllib.parse import urlparse

try:
    from googlenewsdecoder import new_decoderv1
except ImportError:
    new_decoderv1 = None

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Google News redirect links: these are always wrapper URLs. The real
# article URL is base64-ish encoded inside the path and must be decoded
# via googlenewsdecoder before the link is usable at all.
# ----------------------------------------------------------------------
GOOGLE_NEWS_DOMAINS = {"news.google.com"}

# ----------------------------------------------------------------------
# Aggregator / wire-service names whose *source name* should never be
# trusted as "the publisher" even when the URL itself is a normal,
# resolvable link (unlike Google News, these are not redirects — the
# page really does live at that URL, it's just wire copy or a listing
# page rather than a standalone article).
# ----------------------------------------------------------------------
AGGREGATOR_SOURCE_NAMES = {
    "google news",
    "ap news",
    "associated press",
    "reuters",
    "yahoo news",
    "msn",
    "msn news",
    "flipboard",
    "news break",
    "newsbreak",
    "smartnews",
}

# ----------------------------------------------------------------------
# Same set of wire services, keyed by domain instead of display name.
# Needed because not every backend supplies a human-readable `source` —
# duckpy and the HTML scraper only give us a bare netloc (e.g.
# "apnews.com"), which will never match AGGREGATOR_SOURCE_NAMES above.
# ----------------------------------------------------------------------
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

# ----------------------------------------------------------------------
# Hub / topic / tag / index pages: these list many articles rather than
# containing one, so full-content extraction on them will always come
# back empty (or return nav/summary noise). Detected by domain + a
# path-prefix that is a known "this is a listing, not an article"
# pattern for that domain. Extend this table as new aggregators/patterns
# turn up in the wild — it is intentionally conservative (only known
# patterns are flagged) rather than trying to guess from path shape
# alone, which produces false positives on legitimate deep-linked
# articles that happen to live under a short path.
# ----------------------------------------------------------------------
_HUB_PATH_PATTERNS = {
    "apnews.com": (r"^/hub/", r"^/tag/", r"^/$"),
    "news.google.com": (r"^/topics/", r"^/rss/?$", r"^/$"),
    "reuters.com": (r"^/topic/", r"^/section/"),
    "news.yahoo.com": (r"^/topic/", r"^/rss/?$"),
    "flipboard.com": (r"^/topic/",),
    "msn.com": (r"^/en-us/news/other/?$", r"^/en-us/news/?$"),
}
_COMPILED_HUB_PATTERNS = {
    domain: [re.compile(p) for p in patterns]
    for domain, patterns in _HUB_PATH_PATTERNS.items()
}


def _netloc(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_google_news_url(url: str) -> bool:
    """Check whether a URL points at Google News (redirect or RSS link)."""
    return _netloc(url) in GOOGLE_NEWS_DOMAINS


def is_hub_url(url: str) -> bool:
    """
    True if this URL is a known listing/hub/topic page rather than a
    single article — e.g. apnews.com/hub/technology, reuters.com/topic/...
    These will never yield usable article text; callers should drop them
    at fetch time rather than let full-content enrichment silently fail
    on them downstream.
    """
    if not url:
        return False
    domain = _netloc(url)
    patterns = _COMPILED_HUB_PATTERNS.get(domain)
    if not patterns:
        return False
    try:
        path = urlparse(url).path or "/"
    except Exception:
        return False
    return any(p.match(path) for p in patterns)


def is_aggregator_source(source: Optional[str]) -> bool:
    """True if `source` names a wire service / news aggregator rather
    than an original publisher. Used to deprioritize (not necessarily
    drop) results whose byline is generic wire copy."""
    if not source:
        return False
    return source.strip().lower() in AGGREGATOR_SOURCE_NAMES


def aggregator_domain_name(url: str) -> Optional[str]:
    """
    Domain-based counterpart to is_aggregator_source(), for backends
    (duckpy, the HTML scraper) that only give us a bare netloc rather
    than a human-readable source name. Returns the canonical display
    name (e.g. "AP News" for apnews.com) if the URL's domain is a known
    wire/aggregator domain, else None.
    """
    domain = _netloc(url)
    return AGGREGATOR_DOMAINS.get(domain)


def resolve_url(url: str) -> str:
    """
    If url is a Google News link, decode it to the real underlying article
    URL. Otherwise return url unchanged. Falls back to the raw URL if
    decoding isn't possible or fails — never raises.
    """
    if not is_google_news_url(url):
        return url

    if not new_decoderv1:
        logger.debug("googlenewsdecoder not installed, using raw URL")
        return url

    try:
        result = new_decoderv1(url)
        decoded = result.get("decoded_url") if result else None
        if not decoded:
            logger.debug("googlenewsdecoder returned no decoded_url for %s", url)
            return url
        return decoded
    except Exception as e:
        logger.debug("Decoder error for %s: %s", url, e)
        return url


def clean_url(url: str) -> str:
    """
    One-stop helper for feed engines: resolve Google News redirects if
    present. Callers that also care about hub pages should check
    is_hub_url() on the *result* of this function (a Google News redirect
    can itself decode to a hub page).
    """
    if not url:
        return url
    if is_google_news_url(url):
        return resolve_url(url)
    return url
