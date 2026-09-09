import logging
from typing import Dict, List, Optional

from lxml.html import fromstring

from .strategies import (
    ALL_FIELDS,
    ExtractionStrategy,
    JsonLdStrategy,
    OpenGraphStrategy,
    HeuristicStrategy,
)

logger = logging.getLogger(__name__)

DEFAULT_STRATEGIES: List[ExtractionStrategy] = [
    JsonLdStrategy(),
    OpenGraphStrategy(),
    HeuristicStrategy(),
]

_LIST_FIELDS = {"authors", "images", "videos", "keywords"}


def _default(field: str):
    return [] if field in _LIST_FIELDS else None


class ArticleExtractor:
    """Coordinator that runs strategies in order, filling only missing fields."""

    def __init__(self, strategies: Optional[List[ExtractionStrategy]] = None):
        self.strategies = strategies or DEFAULT_STRATEGIES

    def extract(self, html: str, url: Optional[str] = None) -> Dict:
        doc = fromstring(html)
        if url:
            doc.make_links_absolute(url)

        result: Dict = {}
        sources: Dict[str, str] = {}          # which strategy supplied each field, for debugging/QA
        needed = set(ALL_FIELDS)

        for strategy in self.strategies:
            if not needed:
                break
            try:
                found = strategy.extract(doc, url, needed)
            except Exception as e:
                logger.warning(f"{strategy.name} strategy failed: {e}")
                continue
            for field, value in found.items():
                if field not in needed:
                    continue  # strategy returned something we already have; ignore
                if value in (None, "", [], {}):
                    continue
                result[field] = value
                sources[field] = strategy.name
                needed.discard(field)

        for field in ALL_FIELDS:
            result.setdefault(field, _default(field))

        return {
            "title": result["title"] or "",
            "authors": result["authors"] or [],
            "publish_date": result["publish_date"].isoformat() if result["publish_date"] else None,
            "category": result["category"] or "",
            "text": result["text"] or "",
            "top_image": result["top_image"],
            "images": result["images"] or [],
            "videos": result["videos"] or [],
            "meta": {
                "canonical": result["canonical"] or (url or ""),
                "description": result["description"] or "",
                "site_name": result["site_name"] or "",
                "keywords": result["keywords"] or [],
                "language": result["language"] or "",
            },
            "_field_sources": sources,   # which strategy filled each field (QA/debugging aid)
        }


def extract_article(html: str, url: Optional[str] = None) -> Dict:
    """Convenience function, drop-in replacement for the old API."""
    return ArticleExtractor().extract(html, url)
