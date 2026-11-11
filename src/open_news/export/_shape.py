"""Shared helpers for structured export formats."""

import logging
import os
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def normalize_input(items: List[Dict]) -> Tuple[List[Dict], bool]:
    """Return (items, is_cluster). Cluster shape = dict with both an
    `articles` list and an int `size`."""
    if not items:
        return [], False
    first = items[0]
    is_cluster = (
        isinstance(first, dict)
        and isinstance(first.get("articles"), list)
        and isinstance(first.get("size"), int)
    )
    return list(items), is_cluster


def write_output(path, content: str) -> None:
    p = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(p))
    os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as output:
        output.write(content)
    logger.info("Wrote %d chars to %s", len(content), p)


def clean_article(article: Dict, include_internal: bool = False) -> Dict:
    if include_internal:
        return dict(article)
    return {key: value for key, value in article.items() if not key.startswith("_")}
