"""Shared input normalization for both exporters."""
from typing import Dict, List, Tuple


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