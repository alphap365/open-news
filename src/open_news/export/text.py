"""Plain-text export formatted for retrieval and language-model context."""

import os
from typing import Dict, List, Optional, Union

from ._shape import clean_article, normalize_input, write_output


def _article_text(
    article: Dict,
    include_text: bool,
    max_text_chars: Optional[int],
) -> str:
    article = clean_article(article)
    lines = [f"Title: {article.get('title') or 'Untitled'}"]

    for label, keys in (
        ("URL", ("url",)),
        ("Published", ("publish_date", "published")),
        ("Source", ("source",)),
        ("Category", ("category",)),
    ):
        value = next((article.get(key) for key in keys if article.get(key)), None)
        if value:
            lines.append(f"{label}: {value}")

    sources = article.get("sources")
    if sources:
        value = ", ".join(map(str, sources)) if isinstance(sources, list) else sources
        lines.append(f"Sources: {value}")

    authors = article.get("authors")
    if authors:
        value = ", ".join(map(str, authors)) if isinstance(authors, list) else authors
        lines.append(f"Authors: {value}")

    keywords = article.get("keywords")
    if keywords:
        value = ", ".join(map(str, keywords)) if isinstance(keywords, list) else keywords
        lines.append(f"Keywords: {value}")

    description = article.get("description")
    if description:
        lines.append(f"Description: {description}")

    if include_text and article.get("text"):
        body = str(article["text"]).strip()
        if max_text_chars is not None:
            body = body[:max_text_chars]
        lines.extend(["Article text:", body])

    similar = article.get("similar_articles")
    if similar:
        lines.append("Related coverage:")
        for related in similar:
            details = [related.get("title") or "Untitled"]
            if related.get("source"):
                details.append(f"source: {related['source']}")
            if related.get("url"):
                details.append(f"url: {related['url']}")
            lines.append("- " + " | ".join(details))

    return "\n".join(lines)


def to_text(
    items: List[Dict],
    path: Optional[Union[str, "os.PathLike"]] = None,
    *,
    include_text: bool = True,
    max_text_chars: Optional[int] = None,
) -> str:
    """Render articles or clusters as labeled plain text for LLM context.

    Cluster records use the representative article and include cluster
    metadata. The serialized string is returned and optionally written to path.
    """
    if max_text_chars is not None and max_text_chars < 0:
        raise ValueError("max_text_chars must be non-negative or None")

    normalized, is_cluster = normalize_input(items)
    blocks = []
    for index, item in enumerate(normalized, 1):
        if is_cluster:
            representative = item.get("representative") or next(
                iter(item.get("articles") or [{}]), {}
            )
            header = [
                f"Story group {index}: {item.get('label') or representative.get('title') or 'Untitled'}",
                f"Cluster size: {item.get('size', len(item.get('articles') or []))}",
            ]
            if item.get("sources"):
                sources = item["sources"]
                value = ", ".join(map(str, sources)) if isinstance(sources, list) else sources
                header.append(f"Sources: {value}")
            if item.get("first_seen"):
                header.append(f"First seen: {item['first_seen']}")
            if item.get("last_seen"):
                header.append(f"Last seen: {item['last_seen']}")
            block = header + [
                _article_text(representative, include_text, max_text_chars)
            ]
            blocks.append("\n".join(block))
        else:
            blocks.append(
                f"Article {index}\n"
                + _article_text(item, include_text, max_text_chars)
            )

    result = "\n\n---\n\n".join(blocks)
    if path:
        write_output(path, result)
    return result
