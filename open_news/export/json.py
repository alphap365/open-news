"""JSON export — schema-versioned, internal keys stripped."""
from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from ._shape import normalize_input

logger = logging.getLogger(__name__)
SCHEMA_VERSION = "1.0"

_INTERNAL_KEYS = {
    "_tier", "_aggregator_source", "_field_sources",
    "_full_content", "_full_content_reason", "_cluster_size",
}


def _sanitize(item: Dict, drop_internal: bool) -> Dict:
    return ({k: v for k, v in item.items() if k not in _INTERNAL_KEYS}
            if drop_internal else dict(item))


def _default_serializer(o: Any):
    if isinstance(o, datetime):
        return o.isoformat()
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    return str(o)


def _write(path, content: str) -> None:
    p = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(p))
    os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Wrote %d chars to %s", len(content), p)


def to_json(
    items: List[Dict],
    path: Optional[Union[str, "os.PathLike"]] = None,
    *,
    indent: Optional[int] = 2,
    envelope: bool = True,
    include_internal: bool = False,
    ensure_ascii: bool = False,
    generated_at: Optional[datetime] = None,
    extra_meta: Optional[Dict] = None,
) -> str:
    """Serialize articles (or clusters) to clean JSON.

    envelope=True (default) wraps in {schema_version, generated_at, count,
    kind, articles|clusters}. Set envelope=False for a bare list.
    include_internal=False strips `_tier`, `_field_sources`, etc.
    Always returns the string; writes to `path` when given."""
    items, is_cluster = normalize_input(items)
    cleaned = [_sanitize(it, drop_internal=not include_internal) for it in items]

    if envelope:
        now = generated_at or datetime.now(timezone.utc)
        payload: Any = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": now.isoformat(),
            "count": len(cleaned),
            "kind": "clusters" if is_cluster else "articles",
            ("clusters" if is_cluster else "articles"): cleaned,
        }
        if extra_meta:
            payload.update(extra_meta)
    else:
        payload = cleaned

    text = json.dumps(payload, indent=indent, default=_default_serializer,
                       ensure_ascii=ensure_ascii)
    if path:
        _write(path, text)
    return text