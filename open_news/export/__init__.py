"""Structured exports for article / cluster lists.

    from open_news.export import to_markdown, to_json

    to_markdown(articles, path="news.md")
    to_json(clusters, path="news.json")

Both return the serialized string AND write to `path` when given.
Cluster-shaped input (list of dicts with `articles` + `size`) is
auto-detected and rendered per-cluster."""
from .markdown import to_markdown
from .json import to_json

__all__ = ["to_markdown", "to_json"]