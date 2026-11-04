import logging
from typing import Dict, List, Optional, Union, cast
import re

from lxml.html import HtmlElement, fromstring

from .strategies import (
    ALL_FIELDS,
    ExtractionStrategy,
    JsonLdStrategy,
    OpenGraphStrategy,
    HeuristicStrategy,
)
from .source_resolver import resolve_source

logger = logging.getLogger(__name__)

_XML_DECL_RE = re.compile(r"^\s*<\?xml[^>]*\?>", re.I)


def _parse_html(html: Union[str, bytes]):
    if isinstance(html, str):
        html = _XML_DECL_RE.sub("", html.lstrip("\ufeff"), count=1)
    return cast(HtmlElement, fromstring(html))


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
        doc = _parse_html(html)
        if url:
            doc.make_links_absolute(url)

        result: Dict = {}
        sources: Dict[str, str] = {}
        needed = set(ALL_FIELDS)
        json_ld_data: Optional[Dict] = None   # captured once during the loop

        for strategy in self.strategies:
            if not needed:
                break
            try:
                found = strategy.extract(doc, url, needed)
            except Exception as e:
                logger.warning("%s strategy failed: %s", strategy.name, e)
                continue

            # Capture the JSON-LD parse on first encounter so source
            # resolution doesn't have to re-parse the same script tags.
            if json_ld_data is None and isinstance(strategy, JsonLdStrategy):
                try:
                    json_ld_data = strategy._parse(doc)
                except Exception:
                    json_ld_data = None

            for field, value in found.items():
                if field not in needed:
                    continue
                if value in (None, "", [], {}):
                    continue
                result[field] = value
                sources[field] = strategy.name
                needed.discard(field)

        for field in ALL_FIELDS:
            result.setdefault(field, _default(field))

        # Aggregator-aware source resolution.
        source_info = {"source": "", "is_aggregator": False, "resolved": True}
        if url:
            try:
                source_info = resolve_source(
                    doc, url, result["site_name"], json_ld_data,
                )
            except Exception as e:
                logger.debug("source resolution failed for %s: %s", url, e)
                from urllib.parse import urlparse as _urlparse
                source_info = {
                    "source": _urlparse(url).netloc.replace("www.", ""),
                    "is_aggregator": False, "resolved": True,
                }

        # Guard against a custom strategy returning a non-datetime; the
        # built-ins always return datetime, but this keeps the public
        # contract resilient.
        pd = result["publish_date"]
        pd_iso = pd.isoformat() if hasattr(pd, "isoformat") else (pd or None)

        return {
            "title": result["title"] or "",
            "authors": result["authors"] or [],
            "publish_date": pd_iso,
            "category": result["category"] or "",
            "text": result["text"] or "",
            "top_image": result["top_image"],
            "images": result["images"] or [],
            "videos": result["videos"] or [],
            "source": source_info["source"],
            "description": result["description"] or "",
            "meta": {
                "canonical": result["canonical"] or (url or ""),
                "description": result["description"] or "",
                "site_name": result["site_name"] or "",
                "keywords": result["keywords"] or [],
                "language": result["language"] or "",
                "source_is_aggregator": source_info["is_aggregator"],
                "source_resolved": source_info["resolved"],
            },
            "_field_sources": sources,
        }


def extract_article(html: str, url: Optional[str] = None) -> Dict:
    return ArticleExtractor().extract(html, url)