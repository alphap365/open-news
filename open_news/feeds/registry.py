"""Feed registry: auto-discovery via index.json, caching, force-refresh."""

import os
import json
import time
import logging
from typing import Dict, Optional, List
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

REMOTE_BASE = "https://raw.githubusercontent.com/alphap365/open-feeds/main/"
INDEX_URL = urljoin(REMOTE_BASE, "index.json")
CACHE_DIR = os.path.expanduser("~/.open_news/feeds_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_TTL = 24 * 3600

# Local supplemental feeds merged into remote results (safety net if the
# remote repo hasn't picked up a feed yet). Empty by default; populate via
# feeds/local_feeds.json if/when needed.
LOCAL_SUPPLEMENTAL_FEEDS: Dict[str, List[Dict]] = {}


def _cache_path(name: str) -> str:
    safe = name.replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}.json")


def _read_cache(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if time.time() - data.get("_cached_at", 0) < CACHE_TTL:
            return data
    except Exception as e:
        logger.warning(f"Cache read error for {path}: {e}")
    return None


def _write_cache(path: str, data: Dict) -> None:
    try:
        data = {**data, "_cached_at": time.time()}
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"Cache write error for {path}: {e}")


def _fetch_json(url: str, cache_key: str, use_cache: bool = True) -> Optional[Dict]:
    cache_path = _cache_path(cache_key)

    if use_cache:
        cached = _read_cache(cache_path)
        if cached is not None:
            logger.debug(f"Using cached {cache_key}")
            return cached

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _write_cache(cache_path, data)
        logger.info(f"Fetched fresh {cache_key} from {url}")
        return data
    except Exception as e:
        logger.error(f"Failed to fetch {url}: {e}")
        stale = _read_cache_ignore_ttl(cache_path)
        if stale is not None:
            logger.warning(f"Using stale cache for {cache_key}")
            return stale
        return None


def _read_cache_ignore_ttl(path: str) -> Optional[Dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def get_index(use_cache: bool = True) -> Dict:
    """Fetch the open-feeds registry index (category/country -> file path)."""
    data = _fetch_json(INDEX_URL, "_registry_index", use_cache=use_cache)
    return data or {"schema_version": 2, "registry": []}


def list_categories(use_cache: bool = True) -> List[str]:
    idx = get_index(use_cache=use_cache)
    return [e["key"] for e in idx.get("registry", []) if e.get("kind") == "category"]


def list_countries(use_cache: bool = True) -> List[str]:
    idx = get_index(use_cache=use_cache)
    return [e["key"] for e in idx.get("registry", []) if e.get("kind") == "country"]


def _resolve_path(key: str, kind: str, use_cache: bool = True) -> Optional[str]:
    idx = get_index(use_cache=use_cache)
    for entry in idx.get("registry", []):
        if entry.get("key") == key and entry.get("kind") == kind:
            return entry.get("path")
    return None


def _merge_local_supplemental(key: str, feed_data: Dict) -> Dict:
    extra = LOCAL_SUPPLEMENTAL_FEEDS.get(key)
    if not extra:
        return feed_data
    existing_urls = {f.get("url") for f in feed_data.get("feeds", [])}
    merged = list(feed_data.get("feeds", []))
    for feed in extra:
        if feed.get("url") not in existing_urls:
            merged.append(feed)
            existing_urls.add(feed.get("url"))
    feed_data = {**feed_data, "feeds": merged}
    return feed_data


def get_feed_list(
    category: str = "news",
    country: Optional[str] = None,
    use_cache: bool = True,
) -> Dict:
    """
    Resolve a category or country to its feed file via the registry index,
    fetch it (cached), and return the feed dict.

    Backward compatible with v1 flat {name, url} feed entries — missing
    'type'/'active' fields default to 'rss'/True downstream in sources.py.
    """
    key = country or category
    kind = "country" if country else "category"

    path = _resolve_path(key, kind, use_cache=use_cache)
    if not path:
        logger.warning(f"No registry entry for {kind}={key}")
        return {"feeds": [], "max_articles_per_feed": 8}

    url = urljoin(REMOTE_BASE, path)
    data = _fetch_json(url, f"{kind}_{key}", use_cache=use_cache)
    if not data:
        return {"feeds": [], "max_articles_per_feed": 8}

    # filter inactive feeds (v2 schema); v1 feeds with no 'active' key pass through
    feeds = [f for f in data.get("feeds", []) if f.get("active", True)]
    data = {**data, "feeds": feeds}

    data = _merge_local_supplemental(key, data)
    return data


def force_refresh_feed_list(category: str = "news", country: Optional[str] = None) -> Dict:
    """Convenience wrapper: always bypass cache and overwrite it with fresh data."""
    return get_feed_list(category=category, country=country, use_cache=False)


def clear_feed_cache(category: Optional[str] = None, country: Optional[str] = None) -> None:
    """
    Clear cached feed data.
    - Both None: wipe entire cache dir (including the index cache).
    - category or country given: clear just that file's cache.
    """
    if category is None and country is None:
        for fname in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
            except OSError:
                pass
        logger.info("Cleared entire feed cache")
        return

    key = country or category
    kind = "country" if country else "category"
    path = _cache_path(f"{kind}_{key}")
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Cleared cache for {kind}={key}")


def discover_rss_feed(website_url: str) -> Optional[str]:
    """Find RSS/Atom feed URL from a website using BeautifulSoup. (unchanged from get_rss.py)"""
    from bs4 import BeautifulSoup
    from urllib.parse import urlparse

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