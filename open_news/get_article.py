"""Fetch full article text and metadata using FastArticleExtractor + HTTP."""

import logging
from typing import Dict, Optional

import httpx
from .article_extractor import extract_article

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def get_article(url: str, timeout: int = DEFAULT_TIMEOUT) -> Dict:
    """
    Fetch and extract full article content, metadata, images, and videos.

    Args:
        url: Article URL.
        timeout: Request timeout in seconds.

    Returns:
        dict with keys:
            url, title, text, authors, publish_date, top_image, images, videos,
            source (domain), meta (raw extracted metadata).
    """
    logger.info(f"Fetching article: {url}")
    try:
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error(f"HTTP request failed for {url}: {e}")
        return {
            "url": url,
            "title": "",
            "text": "",
            "authors": [],
            "publish_date": None,
            "top_image": None,
            "images": [],
            "videos": [],
            "source": "",
            "meta": {},
        }

    # Extract using FastArticleExtractor
    extracted = extract_article(html, url=url)

    # Add source domain
    from urllib.parse import urlparse
    parsed = urlparse(url)
    source = parsed.netloc.replace("www.", "")

    return {
        "url": url,
        "title": extracted.get("title", ""),
        "text": extracted.get("text", ""),
        "authors": extracted.get("authors", []),
        "publish_date": extracted.get("publish_date"),
        "top_image": extracted.get("top_image"),
        "images": extracted.get("images", []),
        "videos": extracted.get("videos", []),
        "source": source,
        "meta": extracted.get("meta", {}),
    }


# Legacy alias (backward compatibility)
fetch_article = get_article