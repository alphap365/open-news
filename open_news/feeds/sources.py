"""Retrieve article URLs and metadata from RSS feeds or Google News search."""

import logging
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urlparse

import feedparser
from bs4 import BeautifulSoup

try:
    from googlenewsdecoder import new_decoderv1
except ImportError:
    new_decoderv1 = None

logger = logging.getLogger(__name__)


def _decode_google_url(url: str) -> Optional[str]:
    if not new_decoderv1:
        logger.debug("googlenewsdecoder not installed, using raw URL")
        return url
    try:
        result = new_decoderv1(url)
        return result.get("decoded_url") if result else None
    except Exception as e:
        logger.debug(f"Decoder error: {e}")
        return None


def from_rss(feed_url: str, limit: int = 10) -> List[Dict]:
    """Parse RSS feed and return list of articles (title, url, source, published, description)."""
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:limit]:
            link = entry.get("link", "")
            if not link:
                continue
            description = entry.get("description", entry.get("summary", ""))
            if description:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text()
            articles.append({
                "title": entry.get("title", "No title"),
                "url": link,
                "source": feed.feed.get("title", "Unknown RSS"),
                "published": entry.get("published", entry.get("pubDate", "")),
                "description": description[:500],
            })
        logger.info(f"Fetched {len(articles)} from RSS {feed_url}")
    except Exception as e:
        logger.error(f"RSS error {feed_url}: {e}")
    return articles


def from_google_news(query: str, limit: int = 10) -> List[Dict]:
    """Search Google News, decode redirects, return articles."""
    encoded = quote_plus(query)
    search_url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    articles = []
    try:
        feed = feedparser.parse(search_url)
        for entry in feed.entries[:limit]:
            redirect_url = entry.get("link", "")
            if not redirect_url:
                continue
            real_url = _decode_google_url(redirect_url) or redirect_url

            source = entry.get("source", {}).get("title", "")
            if not source and " - " in entry.get("title", ""):
                source = entry["title"].split(" - ")[-1]
            if not source and real_url:
                domain = urlparse(real_url).netloc
                source = domain.replace("www.", "").split(".")[0].title()

            description = entry.get("description", entry.get("summary", ""))
            if description:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text()

            articles.append({
                "title": entry.get("title", "No title"),
                "url": real_url,
                "source": source or "Google News",
                "published": entry.get("published", ""),
                "description": description[:500],
            })
        logger.info(f"Google News '{query}' returned {len(articles)} articles")
    except Exception as e:
        logger.error(f"Google News error: {e}")
    return articles