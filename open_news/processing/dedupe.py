"""Article deduplication: exact URL normalization + optional fuzzy title match."""

import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from ..fetch.url_resolver import is_google_news_url, resolve_url

logger = logging.getLogger(__name__)

# Query params that don't affect article identity — stripped before comparison
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "ref", "ref_src", "ito", "smid",
}

FUZZY_TITLE_THRESHOLD = 0.85
FUZZY_MAX_ARTICLES = 300  # guard against O(n^2) blowup on large batches


def normalize_url(url: str) -> str:
    """
    Resolve Google News redirects, then strip scheme/www/trailing-slash/
    tracking params so equivalent URLs collapse to the same key.
    """
    if not url:
        return url

    if is_google_news_url(url):
        url = resolve_url(url)

    try:
        parsed = urlparse(url)
    except Exception:
        return url

    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")

    kept_params = [
        (k, v) for k, v in parse_qsl(parsed.query)
        if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept_params))

    normalized = urlunparse(("", netloc, path, "", query, ""))
    return normalized.lstrip("/")


def _normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def _is_aggregator(article: Dict) -> bool:
    """Heuristic: source is Google News, or the original url was a gnews link."""
    source = (article.get("source") or "").lower()
    return "google news" in source


def dedupe_articles(
    articles: List[Dict],
    fuzzy: bool = False,
    url_key: str = "url",
    title_key: str = "title",
) -> List[Dict]:
    """
    Remove duplicate articles.

    Stage 1 (always): normalize URLs (resolve gnews redirects, strip
    scheme/www/trailing-slash/tracking params) and dedupe on exact match.
    When both a direct-outlet entry and a Google-News-aggregator entry
    resolve to the same URL, the direct-outlet entry is kept (better
    metadata, no aggregator passthrough).

    Stage 2 (opt-in via fuzzy=True): collapse near-duplicate titles across
    different URLs (same story, different outlets). O(n^2) on article
    count — skipped automatically above FUZZY_MAX_ARTICLES with a warning.

    Args:
        articles: List of article dicts.
        fuzzy: Enable stage 2 fuzzy title dedupe.
        url_key: Dict key holding the article URL.
        title_key: Dict key holding the article title.

    Returns:
        Deduplicated list, original order preserved (first-seen wins).
    """
    seen: Dict[str, Dict] = {}
    order: List[str] = []

    for art in articles:
        url = art.get(url_key, "")
        if not url:
            continue
        key = normalize_url(url)

        if key not in seen:
            seen[key] = art
            order.append(key)
            continue

        # Collision: prefer the non-aggregator entry
        existing = seen[key]
        if _is_aggregator(existing) and not _is_aggregator(art):
            seen[key] = art

    stage1 = [seen[k] for k in order]
    logger.info(f"Dedupe stage 1 (exact URL): {len(articles)} -> {len(stage1)}")

    if not fuzzy:
        return stage1

    if len(stage1) > FUZZY_MAX_ARTICLES:
        logger.warning(
            f"Skipping fuzzy dedupe: {len(stage1)} articles exceeds "
            f"FUZZY_MAX_ARTICLES={FUZZY_MAX_ARTICLES}"
        )
        return stage1

    kept: List[Dict] = []
    kept_titles: List[str] = []

    for art in stage1:
        title = _normalize_title(art.get(title_key, ""))
        if not title:
            kept.append(art)
            kept_titles.append(title)
            continue

        is_dup = False
        for existing_title in kept_titles:
            if not existing_title:
                continue
            ratio = SequenceMatcher(None, title, existing_title).ratio()
            if ratio >= FUZZY_TITLE_THRESHOLD:
                is_dup = True
                break

        if not is_dup:
            kept.append(art)
            kept_titles.append(title)

    logger.info(f"Dedupe stage 2 (fuzzy title): {len(stage1)} -> {len(kept)}")
    return kept