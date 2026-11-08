import logging
from typing import Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..fetch.url_resolver import is_aggregator_source, is_google_news_url, resolve_url

logger = logging.getLogger(__name__)

# Query params that don't affect article identity — stripped before comparison
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
    "ref",
    "ref_src",
    "ito",
    "smid",
}


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

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.endswith(":80") and parsed.scheme.lower() == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and parsed.scheme.lower() == "https":
        netloc = netloc[:-4]
    path = parsed.path.rstrip("/") or "/"

    kept_params = [
        (k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept_params))

    normalized = urlunparse(("", netloc, path, "", query, ""))
    return normalized.lstrip("/")


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


def _source_names(article: Dict) -> List[str]:
    names = []
    meta = article.get("meta")
    site_name = meta.get("site_name") if isinstance(meta, dict) else None
    for value in (
        article.get("source"),
        site_name,
        article.get("sources", []),
    ):
        candidates = value if isinstance(value, (list, tuple, set)) else [value]
        names.extend(
            name.strip()
            for name in candidates
            if isinstance(name, str) and name.strip()
        )
    return list(dict.fromkeys(names))


def _article_priority(article: Dict) -> tuple:
    text = article.get("text") or article.get("description") or ""
    populated_fields = sum(
        value not in (None, "", [], {}) for value in article.values()
    )
    return (not _is_aggregator(article), len(text), populated_fields)


def _merge_same_url(existing: Dict, incoming: Dict) -> Dict:
    primary, secondary = (
        (incoming, existing)
        if _article_priority(incoming) > _article_priority(existing)
        else (existing, incoming)
    )
    merged = dict(secondary)
    for key, value in primary.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    sources = list(dict.fromkeys(_source_names(existing) + _source_names(incoming)))
    if sources:
        merged["sources"] = sources
    return merged


def dedupe_articles(
    articles: List[Dict],
    url_key: str = "url",
) -> List[Dict]:
    """Merge records for the same normalized URL without dropping similar stories.

    The preferred non-aggregator/fullest record supplies the article fields;
    source names from every matching record are retained in ``sources``.
    Articles without URLs are kept because they cannot be safely identified.
    """
    articles_by_url: Dict[str, int] = {}
    merged_articles: List[Dict] = []

    for art in articles:
        item = dict(art)
        url = item.get(url_key, "")
        if not url:
            merged_articles.append(item)
            continue

        if is_google_news_url(url):
            url = resolve_url(url)
            item[url_key] = url

        key = normalize_url(url)
        if key not in articles_by_url:
            articles_by_url[key] = len(merged_articles)
            merged_articles.append(item)
            continue

        index = articles_by_url[key]
        merged_articles[index] = _merge_same_url(merged_articles[index], item)

    logger.info(
        "Merged exact-URL duplicates: %d records -> %d articles",
        len(articles),
        len(merged_articles),
    )
    return merged_articles
