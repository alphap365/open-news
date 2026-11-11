"""Schema.org JSON-LD export for news articles and story groups."""

import json
import os
from typing import Any, Dict, List, Optional, Union

from ._shape import clean_article, normalize_input, write_output


def _news_article(article: Dict) -> Dict[str, Any]:
    article = clean_article(article)
    result: Dict[str, Any] = {"@type": "NewsArticle"}

    fields = {
        "headline": "title",
        "url": "url",
        "description": "description",
        "articleBody": "text",
        "datePublished": "publish_date",
        "dateModified": "date_modified",
    }
    for schema_key, article_key in fields.items():
        value = article.get(article_key)
        if schema_key == "datePublished":
            value = value or article.get("published")
        elif schema_key == "dateModified":
            value = value or article.get("modified")
        if value:
            result[schema_key] = value.isoformat() if hasattr(value, "isoformat") else value

    authors = article.get("authors")
    if authors:
        if isinstance(authors, str):
            authors = [authors]
        result["author"] = [
            {
                "@type": "Person",
                "name": author.get("name") if isinstance(author, dict) else author,
            }
            for author in authors
            if author
        ]

    meta = article.get("meta")
    publisher = article.get("source") or (
        meta.get("site_name") if isinstance(meta, dict) else None
    )
    if publisher:
        result["publisher"] = {"@type": "Organization", "name": publisher}

    images = article.get("images") or []
    if isinstance(images, str):
        images = [images]
    top_image = article.get("top_image")
    if top_image and top_image not in images:
        images = [top_image, *images]
    if images:
        result["image"] = images

    keywords = article.get("keywords")
    if keywords:
        result["keywords"] = keywords
    return result


def to_jsonld(
    items: List[Dict],
    path: Optional[Union[str, "os.PathLike"]] = None,
    *,
    indent: Optional[int] = 2,
) -> str:
    """Serialize article or cluster records as Schema.org JSON-LD ItemList.

    Each item is represented by a ``NewsArticle``. For clusters, the
    representative is used and cluster summary metadata is retained as
    ``additionalProperty`` values. The JSON string is returned and optionally
    written to path.
    """
    normalized, is_cluster = normalize_input(items)
    elements = []
    for index, item in enumerate(normalized, 1):
        if is_cluster:
            representative = item.get("representative") or next(
                iter(item.get("articles") or [{}]), {}
            )
            article = _news_article(representative)
            properties = [
                {
                    "@type": "PropertyValue",
                    "name": "clusterSize",
                    "value": item.get("size", 0),
                }
            ]
            if item.get("label"):
                properties.append(
                    {
                        "@type": "PropertyValue",
                        "name": "clusterLabel",
                        "value": item["label"],
                    }
                )
            if item.get("sources"):
                properties.append(
                    {
                        "@type": "PropertyValue",
                        "name": "sources",
                        "value": item["sources"],
                    }
                )
            article["additionalProperty"] = properties
        else:
            article = _news_article(item)
        elements.append({"@type": "ListItem", "position": index, "item": article})

    payload = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "numberOfItems": len(elements),
        "itemListElement": elements,
    }
    result = json.dumps(payload, indent=indent, ensure_ascii=False, default=str)
    if path:
        write_output(path, result)
    return result
