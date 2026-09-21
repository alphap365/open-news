"""Markdown export — clean, TOC'd, download-friendly."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from ._shape import normalize_input

logger = logging.getLogger(__name__)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-") or "section"


def _fmt_dt(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _article_block(
    article: Dict, index: Optional[int], *,
    heading_level: int = 3,
    include_text: bool = True,
    include_summary: bool = True,
    include_metadata: bool = True,
    max_text_chars: Optional[int] = None,
) -> str:
    title = article.get("title") or "Untitled"
    prefix = f"{index}. " if index is not None else ""
    lines: List[str] = [f"{'#' * heading_level} {prefix}{title}", ""]

    if include_metadata:
        bits = []
        source = article.get("source") or article.get("meta", {}).get("site_name")
        if source:
            bits.append(f"**Source:** {source}")
        date = article.get("publish_date") or article.get("published")
        if date:
            bits.append(f"**Published:** {_fmt_dt(date) or date}")
        authors = article.get("authors") or []
        if authors:
            bits.append(f"**Authors:** {', '.join(str(a) for a in authors)}")
        if bits:
            lines.append(" — ".join(bits))
            lines.append("")

    if include_summary:
        desc = article.get("description") or article.get("meta", {}).get("description")
        if desc and desc.strip():
            lines.extend([f"> {desc.strip()}", ""])

    if include_text:
        text = (article.get("text") or "").strip()
        if text:
            if max_text_chars and len(text) > max_text_chars:
                text = text[:max_text_chars].rstrip() + " […]"
            lines.extend([text, ""])

    url = article.get("url") or ""
    if url:
        lines.extend([f"[Read original]({url})", ""])

    return "\n".join(lines)


def _cluster_block(
    cluster: Dict, index: int, *,
    heading_level: int = 2,
    include_text: bool = True,
    include_summary: bool = True,
    include_metadata: bool = True,
    max_text_chars: Optional[int] = None,
    include_all_members: bool = False,
) -> str:
    label = cluster.get("label") or f"Cluster {index}"
    size = cluster.get("size") or len(cluster.get("articles") or [])
    lines: List[str] = [f"{'#' * heading_level} {index}. {label}", ""]
    lines.extend([f"_Cluster of {size} article(s)._", ""])

    sources = cluster.get("sources") or []
    if sources:
        lines.extend([f"**Sources:** {', '.join(sources)}", ""])

    span = []
    if cluster.get("first_seen"):
        span.append(f"first {_fmt_dt(cluster['first_seen']) or cluster['first_seen']}")
    if cluster.get("last_seen"):
        span.append(f"latest {_fmt_dt(cluster['last_seen']) or cluster['last_seen']}")
    if span:
        lines.extend(["_Timeline: " + ", ".join(span) + "_", ""])

    rep = cluster.get("representative") or (cluster.get("articles") or [{}])[0]
    lines.append(_article_block(
        rep, None, heading_level=heading_level + 1,
        include_text=include_text, include_summary=include_summary,
        include_metadata=include_metadata, max_text_chars=max_text_chars,
    ))

    if include_all_members and size > 1:
        lines.extend([f"{'#' * (heading_level + 1)} Other reports", ""])
        for m in cluster.get("articles", [])[1:]:
            title = m.get("title") or "Untitled"
            url = m.get("url") or ""
            src = m.get("source") or ""
            suffix = f" — _{src}_" if src else ""
            lines.append(f"- [{title}]({url}){suffix}" if url else f"- {title}{suffix}")
        lines.append("")

    lines.extend(["---", ""])
    return "\n".join(lines)


def _write(path, content: str) -> None:
    p = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(p))
    os.makedirs(parent, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Wrote %d chars to %s", len(content), p)


def to_markdown(
    items: List[Dict],
    path: Optional[Union[str, "os.PathLike"]] = None,
    *,
    title: Optional[str] = None,
    include_text: bool = True,
    include_summary: bool = True,
    include_metadata: bool = True,
    include_toc: bool = True,
    max_text_chars: Optional[int] = 4000,
    include_all_members: bool = False,
    generated_at: Optional[datetime] = None,
) -> str:
    """Render articles (or clusters) as clean Markdown. Always returns the
    string; writes to `path` (parent dirs created) when given."""
    items, is_cluster = normalize_input(items)
    doc_title = title or ("News Clusters" if is_cluster else "News Export")
    now = generated_at or datetime.now(timezone.utc)

    out: List[str] = [
        f"# {doc_title}",
        "",
        f"_Generated: {now.strftime('%Y-%m-%d %H:%M UTC')} — "
        f"{len(items)} {'cluster(s)' if is_cluster else 'article(s)'}_",
        "",
    ]

    if not items:
        out.append("_No items._")
        md = "\n".join(out)
    else:
        if include_toc and len(items) > 1:
            out.extend(["## Table of Contents", ""])
            for i, item in enumerate(items, 1):
                label = item.get("label") if is_cluster else item.get("title")
                label = label or f"Item {i}"
                out.append(f"{i}. [{label}](#{_slug(f'{i}. {label}')})")
            out.extend(["", "---", ""])

        for i, item in enumerate(items, 1):
            if is_cluster:
                out.append(_cluster_block(
                    item, i,
                    include_text=include_text, include_summary=include_summary,
                    include_metadata=include_metadata, max_text_chars=max_text_chars,
                    include_all_members=include_all_members,
                ))
            else:
                out.append(_article_block(
                    item, i, heading_level=2,
                    include_text=include_text, include_summary=include_summary,
                    include_metadata=include_metadata, max_text_chars=max_text_chars,
                ))
                out.extend(["---", ""])
        md = "\n".join(out).rstrip() + "\n"

    if path:
        _write(path, md)
    return md