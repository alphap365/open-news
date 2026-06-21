"""Fetch full article text and metadata using FastArticleExtractor + HTTP."""

import logging
from typing import Dict, Optional

import httpx
from .article_extractor import extract_article
from .user_agents import get_user_agent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15

def get_article(url: str, timeout: int = DEFAULT_TIMEOUT, js: bool = False) -> Dict:
    """
    Fetch and extract full article content, metadata, images, and videos.

    Args:
        url: Article URL.
        timeout: Request timeout in seconds.
        js: If True, render the page with a headless browser (requires
            `pip install open-news-api[js]`). Use for JS-heavy sites where
            httpx's raw HTML misses the real article body.
    """
    logger.info(f"Fetching article: {url} (js={js})")
    html = None

    if js:
        from . import js_renderer
        try:
            html = js_renderer.render_html(url, timeout=timeout, user_agent=get_user_agent())
        except RuntimeError as e:
            logger.warning(f"{e} — falling back to plain HTTP fetch")
        except Exception as e:
            logger.error(f"JS render failed for {url}: {e} — falling back to plain HTTP fetch")

    if html is None:
        try:
            headers = {"User-Agent": get_user_agent()}
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            logger.error(f"HTTP request failed for {url}: {e}")
            return _empty_result(url)

    try:
        extracted = extract_article(html, url=url)
    except Exception as e:
        logger.error(f"Extraction failed for {url}: {e}")
        extracted = {}

    from urllib.parse import urlparse
    source = urlparse(url).netloc.replace("www.", "")

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


def _empty_result(url: str) -> Dict:
    return {
        "url": url, "title": "", "text": "", "authors": [], "publish_date": None,
        "top_image": None, "images": [], "videos": [], "source": "", "meta": {},
    }


# Legacy alias (backward compatibility)
fetch_article = get_article