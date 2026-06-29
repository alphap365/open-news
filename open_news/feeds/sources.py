"""Retrieve article URLs and metadata from RSS feeds, Google News search,
or a domain-scoped Google search (news-fetch-style site search)."""

import logging
from typing import List, Dict, Optional
from urllib.parse import quote_plus, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from ..fetch.url_resolver import is_google_news_url, resolve_url

logger = logging.getLogger(__name__)


def from_rss(feed_url: str, limit: int = 10, resolve_google_urls: bool = True) -> List[Dict]:
    """
    Parse RSS feed and return list of articles (title, url, source, published,
    description). If resolve_google_urls is True (default), any entry whose
    link is a Google News URL gets resolved to the real article URL — this
    matters once Google News RSS feeds are merged into open-feeds category
    files alongside direct outlet feeds.
    """
    articles = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:limit]:
            link = entry.get("link", "")
            if not link:
                continue

            real_url = link
            if resolve_google_urls and is_google_news_url(link):
                real_url = resolve_url(link)

            description = entry.get("description", entry.get("summary", ""))
            if description:
                soup = BeautifulSoup(description, "html.parser")
                description = soup.get_text()

            articles.append({
                "title": entry.get("title", "No title"),
                "url": real_url,
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
            real_url = resolve_url(redirect_url)

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


def search_site(keyword: str, domain: str, limit: int = 10) -> List[Dict]:
    """
    Search Google for a keyword scoped to a single news domain
    (news-fetch-style GoogleSearchNewsURLExtractor equivalent), using
    Google News RSS search with a site: filter rather than scraping
    google.com/search HTML directly (more stable, no CAPTCHA risk).

    Args:
        keyword: Search terms.
        domain: Target domain, e.g. "timesofindia.indiatimes.com" or a
            full URL like "https://timesofindia.indiatimes.com/" (scheme
            and path are stripped automatically).
        limit: Maximum results.

    Returns:
        Same article dict shape as from_google_news().
    """
    netloc = urlparse(domain).netloc or domain
    netloc = netloc.replace("www.", "").strip("/")

    query = f"{keyword} site:{netloc}"
    results = from_google_news(query, limit=limit)

    # Defensive filter: Google News search occasionally returns near-domain
    # matches (subdomains, syndication mirrors) — keep only results whose
    # resolved URL actually lives on the requested domain.
    filtered = [
        art for art in results
        if netloc in urlparse(art["url"]).netloc.replace("www.", "")
    ]

    logger.info(f"search_site('{keyword}', domain={netloc}) returned {len(filtered)} articles")
    return filtered