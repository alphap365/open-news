"""Google News URL detection and resolution to real article URLs."""

import logging
from typing import Optional
from urllib.parse import urlparse

try:
    from googlenewsdecoder import new_decoderv1
except ImportError:
    new_decoderv1 = None

logger = logging.getLogger(__name__)

GOOGLE_NEWS_DOMAINS = {"news.google.com"}


def is_google_news_url(url: str) -> bool:
    """Check whether a URL points at Google News (redirect or RSS link)."""
    if not url:
        return False
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return netloc in GOOGLE_NEWS_DOMAINS


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
        return decoded or url
    except Exception as e:
        logger.debug(f"Decoder error for {url}: {e}")
        return url