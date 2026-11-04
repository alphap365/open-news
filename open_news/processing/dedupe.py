import logging
import re
from difflib import SequenceMatcher
from typing import List, Dict, Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from ..utils.textutil import normalize_title as _normalize_title
from ..fetch.url_resolver import is_aggregator_source, is_google_news_url, resolve_url

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


def _find_similar(title: str, kept_titles: List[str], threshold: float) -> Optional[int]:
    """Index of the first kept title at least `threshold` similar, else None.
    The two cheap upper bounds skip most O(n) full comparisons."""
    for idx, existing in enumerate(kept_titles):
        if not existing:
            continue
        sm = SequenceMatcher(None, title, existing)
        if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
            continue
        if sm.ratio() >= threshold:
            return idx
    return None


def _is_aggregator(article: Dict) -> bool:
    """
    True if this article is wire/aggregator content rather than a
    direct-outlet result. Checks, in order:
      1. The engine already flagged it (``_aggregator_source``, set by
         duckduckgo_engine.py / googlenews_engine.py when the source
         name is a known wire service).
      2. The `source` field itself names a known aggregator — broader
         than the old hardcoded "google news" substring check, so AP
         wire, Reuters, Yahoo News, MSN, etc. are also recognized.
      3. Legacy fallback: literal "google news" substring, kept for any
         caller populating `source` with something not covered above.
    """
    if article.get("_aggregator_source"):
        return True
    source = article.get("source") or ""
    if is_aggregator_source(source):
        return True
    return "google news" in source.lower()


def dedupe_articles(
    articles: List[Dict],
    fuzzy: bool = False,
    url_key: str = "url",
    title_key: str = "title",
) -> List[Dict]:
    """... (docstring unchanged) ..."""
    seen: Dict[str, Dict] = {}
    order: List[str] = []

    for art in articles:
        url = art.get(url_key, "")
        if not url:
            continue

        # Resolve gnews redirects ONCE. normalize_url() would otherwise call
        # resolve_url() internally, and the explicit resolve below would call
        # it a second time — two network round-trips per URL.
        if is_google_news_url(url):
            url = resolve_url(url)
            art[url_key] = url

        key = normalize_url(url)

        if key not in seen:
            seen[key] = art
            order.append(key)
            continue

        existing = seen[key]
        if _is_aggregator(existing) and not _is_aggregator(art):
            seen[key] = art

    stage1 = [seen[k] for k in order]
    logger.info("Dedupe stage 1 (exact URL): %d -> %d", len(articles), len(stage1))

    if not fuzzy:
        return stage1

    if len(stage1) > FUZZY_MAX_ARTICLES:
        logger.warning(
            "Skipping fuzzy dedupe: %d articles exceeds FUZZY_MAX_ARTICLES=%d",
            len(stage1), FUZZY_MAX_ARTICLES,
        )
        return stage1

    kept: List[Dict] = []
    kept_titles: List[str] = []

    for art in stage1:
        title = _normalize_title(art.get(title_key, ""))
        art.setdefault("_cluster_size", 1)
        match = _find_similar(title, kept_titles, FUZZY_TITLE_THRESHOLD) if title else None
        if match is None:
            kept.append(art)
            kept_titles.append(title)
        else:
            kept[match]["_cluster_size"] += art["_cluster_size"]

    logger.info("Dedupe stage 2 (fuzzy title): %d -> %d", len(stage1), len(kept))
    return kept