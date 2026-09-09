import logging
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    # Allow callers to pass either "cnn.com" or "https://cnn.com/"
    if "://" in domain:
        domain = urlparse(domain).netloc
    return domain.replace("www.", "").strip("/")


def _article_domain(article: Dict) -> str:
    url = article.get("url", "")
    return urlparse(url).netloc.lower().replace("www.", "")


def _domain_matches(article_domain: str, listed_domain: str) -> bool:
    return article_domain == listed_domain or article_domain.endswith(f".{listed_domain}")


def filter_by_domain(
    articles: List[Dict],
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
) -> List[Dict]:
    """Apply whitelist (keep only matches) and/or blacklist (drop matches).
    Whitelist takes precedence if both are given — an explicit allow-list
    is a stronger signal of intent than a deny-list."""
    if not whitelist and not blacklist:
        return articles

    kept = []
    if whitelist:
        allowed = {_normalize_domain(d) for d in whitelist}
        for art in articles:
            dom = _article_domain(art)
            if any(_domain_matches(dom, a) for a in allowed):
                kept.append(art)
        logger.info(f"Whitelist filter: {len(articles)} -> {len(kept)}")
        return kept

    blocked = {_normalize_domain(d) for d in blacklist}
    for art in articles:
        dom = _article_domain(art)
        if not any(_domain_matches(dom, b) for b in blocked):
            kept.append(art)
    logger.info(f"Blacklist filter: {len(articles)} -> {len(kept)}")
    return kept
