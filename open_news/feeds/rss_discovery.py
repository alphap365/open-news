import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..utils.user_agents import get_user_agent

logger = logging.getLogger(__name__)


def discover_rss_feed(website_url: str, timeout: int = 10) -> Optional[str]:
    """Find RSS/Atom feed URL from a website using BeautifulSoup."""
    try:
        headers = {"User-Agent": get_user_agent()}
        resp = httpx.get(website_url, timeout=timeout, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("link", type=["application/rss+xml", "application/atom+xml"]):
            href = link.get("href")
            if href:
                return urljoin(website_url, href)

        feed_keywords = ("/feed", "/rss", "/atom", ".rss", ".atom", "feed.xml", "rss.xml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            path = urlparse(href).path.lower()
            if any(kw in path for kw in feed_keywords):
                return urljoin(website_url, href)
        return None
    except Exception as e:
        logger.debug(f"RSS discovery failed for {website_url}: {e}")
        return None
