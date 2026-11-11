import asyncio
import logging
from typing import Awaitable, Dict, Optional, Union
from urllib.parse import urlparse

import httpx

from ..core.extractor import extract_article
from ..utils.user_agents import get_user_agent

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15


async def _get_article_async(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    js: bool = False,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict:
    """Async article fetch + extraction.

    If `client` is supplied, it is reused (connection pooling across many
    URLs); otherwise a fresh AsyncClient is created and closed per call.
    """
    logger.info("Fetching article: %s (js=%s)", url, js)
    html = None

    if js:
        from ..core import renderer as js_renderer

        try:
            # Playwright's sync driver is not async-safe. Isolate it in a
            # worker thread; the async event loop keeps running for other
            # concurrent article fetch calls.
            html = await asyncio.to_thread(
                js_renderer.render_html,
                url,
                timeout=timeout,
                user_agent=get_user_agent(),
            )
        except RuntimeError as e:
            logger.warning("%s — falling back to plain HTTP fetch", e)
        except Exception as e:
            logger.error("JS render failed for %s: %s — falling back", url, e)

    if html is None:
        headers = {"User-Agent": get_user_agent()}
        own_client = client is None
        c = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
        )
        try:
            resp = await c.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error("HTTP request failed for %s: %s", url, e)
            return _empty_result(url)
        finally:
            if own_client:
                await c.aclose()

    try:
        extracted = extract_article(html, url=url)
    except Exception as e:
        logger.error("Extraction failed for %s: %s", url, e)
        extracted = {}

    source = extracted.get("source") or urlparse(url).netloc.replace("www.", "")

    return {
        "url": url,
        "title": extracted.get("title", ""),
        "text": extracted.get("text", ""),
        "authors": extracted.get("authors", []),
        "publish_date": extracted.get("publish_date"),
        "category": extracted.get("category", ""),
        "top_image": extracted.get("top_image"),
        "images": extracted.get("images", []),
        "videos": extracted.get("videos", []),
        "source": source,
        "description": extracted.get("description", ""),
        "meta": extracted.get("meta", {}),
    }


def get_article(
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    js: bool = False,
    async_: bool = False,
) -> Union[Dict, Awaitable[Dict]]:
    """Fetch an article synchronously or return a coroutine when async_ is True."""
    coroutine = _get_article_async(url, timeout=timeout, js=js)
    return coroutine if async_ else asyncio.run(coroutine)


def _empty_result(url: str) -> Dict:
    return {
        "url": url,
        "title": "",
        "text": "",
        "authors": [],
        "publish_date": None,
        "category": "",
        "top_image": None,
        "images": [],
        "videos": [],
        "source": "",
        "description": "",
        "meta": {},
    }


fetch_article = get_article
