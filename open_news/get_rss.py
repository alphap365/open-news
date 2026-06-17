"""RSS feed handling: remote feed lists (from open-feeds repo), discovery, caching."""

import os
import json
import time
import logging
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REMOTE_BASE = "https://raw.githubusercontent.com/alphap365/open-feeds/main/feeds"
CACHE_DIR = os.path.expanduser("~/.open_news/feeds_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 24 * 3600


def _cache_path(category: str, country: Optional[str] = None) -> str:
    if country:
        return os.path.join(CACHE_DIR, f"country_{country}.json")
    return os.path.join(CACHE_DIR, f"{category}.json")


def get_feed_list(category: str = "news", country: Optional[str] = None, use_cache: bool = True) -> Dict:
    """
    Fetch feed JSON from open-feeds repository.

    Args:
        category: 'news', 'business', 'politics', etc.
        country: If given, fetches country-specific feeds (e.g., 'india').
        use_cache: Use cached copy if fresh.

    Returns:
        Dict with keys: feeds, max_articles_per_feed, etc.
    """
    cache_path = _cache_path(category, country)

    if use_cache and os.path.exists(cache_path):
        try:
            with open(cache_path) as f:
                data = json.load(f)
            if time.time() - data.get('_cached_at', 0) < CACHE_TTL:
                logger.debug(f"Using cached feed list for {category}/{country}")
                return data
        except Exception as e:
            logger.warning(f"Cache read error: {e}")

    if country:
        url = f"{REMOTE_BASE}/country/{country}.json"
    else:
        url = f"{REMOTE_BASE}/{category}.json"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        data['_cached_at'] = time.time()
        with open(cache_path, 'w') as f:
            json.dump(data, f)
        logger.info(f"Fetched fresh feed list from {url}")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                logger.warning(f"Using stale cache for {category}/{country}")
                return json.load(f)
        return {"feeds": [], "max_articles_per_feed": 8}


def discover_rss_feed(website_url: str) -> Optional[str]:
    """Find RSS/Atom feed URL from a website using BeautifulSoup."""
    try:
        headers = {"User-Agent": "open-news/1.0"}
        resp = requests.get(website_url, timeout=10, headers=headers)
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
        logger.debug(f"Discovery failed for {website_url}: {e}")
        return None