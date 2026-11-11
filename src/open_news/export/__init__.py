"""Structured exports for article / cluster lists.

    from open_news.export import to_csv, to_json, to_jsonld, to_markdown, to_text

    to_markdown(articles, path="news.md")
    to_json(clusters, path="news.json")
    to_jsonld(articles, path="news.jsonld")
    to_csv(articles, path="news.csv")
    to_text(articles, path="news.txt")

Both return the serialized string AND write to `path` when given.
Cluster-shaped input (list of dicts with `articles` + `size`) is
auto-detected and rendered per-cluster."""

from .csv import to_csv
from .json import to_json
from .jsonld import to_jsonld
from .markdown import to_markdown
from .text import to_text

__all__ = ["to_markdown", "to_json", "to_jsonld", "to_csv", "to_text"]
