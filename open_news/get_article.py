"""Fetch full article text and metadata using newspaper4k, trafilatura, or BeautifulSoup fallback."""

import json
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

try:
    from newspaper import Article
except ImportError:
    Article = None
try:
    import trafilatura
    import trafilatura.settings
except ImportError:
    trafilatura = None

from bs4 import BeautifulSoup
import httpx

logger = logging.getLogger(__name__)

# Minimum character threshold to consider extraction successful
_MIN_TEXT_LENGTH = 200


def _extract_with_newspaper(url: str) -> Tuple[str, Dict]:
    """Return (text, metadata). Metadata dict may contain title, publish_date, source."""
    if not Article:
        return "", {}
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text or ""

        # FIX (Bug 3): publish_date may already be a string in some newspaper4k versions
        pub_date = article.publish_date
        if isinstance(pub_date, datetime):
            pub_date = pub_date.isoformat()
        elif not isinstance(pub_date, str):
            pub_date = ""

        meta = {
            "title": article.title or "",
            "publish_date": pub_date,
            "source": article.source_url or "",
        }
        return text, meta
    except Exception as e:
        logger.debug(f"newspaper failed for {url}: {e}")
        return "", {}


def _extract_with_trafilatura(url: str) -> Tuple[str, Dict]:
    """Return (text, metadata) using trafilatura with metadata extraction enabled."""
    if not trafilatura:
        return "", {}
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            # FIX (Bug 1): use include_metadata so we get title/date without a second HTTP call
            result = trafilatura.extract(
                downloaded,
                include_metadata=True,
                output_format="json",
                with_metadata=True,
            )
            if result:
                try:
                    data = json.loads(result)
                    text = data.get("text") or data.get("raw_text") or ""
                    meta = {
                        "title": data.get("title", ""),
                        "publish_date": data.get("date", ""),
                        "source": data.get("sitename", ""),
                    }
                    return text, meta
                except (json.JSONDecodeError, TypeError):
                    # Fallback: extract returned a plain string (older trafilatura)
                    text = trafilatura.extract(downloaded) or ""
                    return text, {}
    except Exception as e:
        logger.debug(f"trafilatura failed for {url}: {e}")
    return "", {}


def _extract_with_bs4(url: str) -> Tuple[str, Dict]:
    """Fallback: extract text and try to guess title from HTML."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        with httpx.Client(follow_redirects=True, timeout=15) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)

            title = ""
            if soup.title:
                title = soup.title.get_text(strip=True)
            meta = {"title": title, "publish_date": "", "source": ""}
            return text, meta
    except Exception as e:
        logger.debug(f"bs4 fallback failed for {url}: {e}")
        return "", {}


def fetch_article(url: str) -> Dict:
    """
    Fetch full article content and metadata.
    Returns dict with keys: url, title, text, publish_date, source.
    All values are strings; 'text' is empty string on complete failure.
    """
    logger.info(f"Fetching article: {url}")

    # Try newspaper4k first (best metadata)
    text, meta = _extract_with_newspaper(url)
    if text and len(text) > _MIN_TEXT_LENGTH:
        logger.debug("newspaper4k success")
        return {
            "url": url,
            "title": meta.get("title", ""),
            "text": text,
            "publish_date": meta.get("publish_date", ""),
            "source": meta.get("source", ""),
        }

    # FIX (Bug 1): trafilatura now returns metadata directly — no second HTTP call needed
    text, meta = _extract_with_trafilatura(url)
    if text and len(text) > _MIN_TEXT_LENGTH:
        logger.debug("trafilatura success")
        return {
            "url": url,
            "title": meta.get("title", ""),
            "text": text,
            "publish_date": meta.get("publish_date", ""),
            "source": meta.get("source", ""),
        }

    # Final fallback
    text, bs4_meta = _extract_with_bs4(url)
    if text and len(text) > _MIN_TEXT_LENGTH:
        logger.debug("bs4 fallback success")
        return {
            "url": url,
            "title": bs4_meta.get("title", ""),
            "text": text,
            "publish_date": "",
            "source": "",
        }

    logger.warning(f"All extraction methods failed for {url}")
    return {"url": url, "title": "", "text": "", "publish_date": "", "source": ""}
