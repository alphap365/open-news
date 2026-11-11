"""CSV export with predictable columns and JSON-encoded nested values."""

import csv
import io
import json
import os
from typing import Any, Dict, List, Optional, Union

from ._shape import clean_article, normalize_input, write_output

_COLUMNS = [
    "cluster_id",
    "cluster_label",
    "cluster_size",
    "cluster_score",
    "cluster_first_seen",
    "cluster_last_seen",
    "title",
    "url",
    "description",
    "text",
    "publish_date",
    "category",
    "source",
    "sources",
    "authors",
    "keywords",
    "top_image",
    "images",
    "videos",
    "meta",
    "similar_articles",
]


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def to_csv(
    items: List[Dict],
    path: Optional[Union[str, "os.PathLike"]] = None,
    *,
    include_text: bool = True,
    include_internal: bool = False,
) -> str:
    """Serialize article or cluster records as CSV.

    Nested values (authors, sources, keywords, and similar articles) are
    JSON-encoded in their cells. Cluster records produce one row per story
    group, using its representative article and cluster metadata.
    """
    normalized, is_cluster = normalize_input(items)
    output = io.StringIO(newline="")
    columns = list(_COLUMNS)
    if include_internal:
        articles = [
            item.get("representative") or next(iter(item.get("articles") or [{}]), {})
            if is_cluster
            else item
            for item in normalized
        ]
        extra_columns = sorted(
            {
                key
                for item in [*normalized, *articles]
                for key in item
                if key.startswith("_")
            }
        )
        columns.extend(extra_columns)
    if not include_text:
        columns.remove("text")

    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for item in normalized:
        if is_cluster:
            article = item.get("representative") or next(
                iter(item.get("articles") or [{}]), {}
            )
            row = {
                "cluster_id": item.get("id"),
                "cluster_label": item.get("label"),
                "cluster_size": item.get("size"),
                "cluster_score": item.get("score"),
                "cluster_first_seen": item.get("first_seen"),
                "cluster_last_seen": item.get("last_seen"),
            }
            if include_internal:
                row.update({key: value for key, value in item.items() if key.startswith("_")})
        else:
            article = item
            row = {}
        row.update(clean_article(article, include_internal=include_internal))
        if not include_text:
            row.pop("text", None)
        writer.writerow({key: _csv_value(value) for key, value in row.items()})

    result = output.getvalue()
    if path:
        write_output(path, result)
    return result
