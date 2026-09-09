#!/usr/bin/env python3
"""Command-line interface for open-news."""

import argparse
import json
import sys
from typing import Any, Dict, List

from .api import fetch, search, get_article, discover_and_get


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Open-News: Fetch and extract news articles.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- fetch command ---
    fetch_p = subparsers.add_parser("fetch", help="Fetch live category/location news.")
    fetch_p.add_argument("--category", default="general", choices=["general", "business", "tech", "sports", "health", "science", "entertainment"])
    fetch_p.add_argument("--location", help="Country code, e.g. us, in")
    fetch_p.add_argument("--limit", type=int, default=5)
    fetch_p.add_argument("--language", help="ISO 639-1 language code, e.g. en")
    fetch_p.add_argument("--full-content", action="store_true")
    fetch_p.add_argument("--sort", default="date", choices=["date", "relevance", "popularity"])

    # --- search command ---
    search_p = subparsers.add_parser("search", help="Search news by keyword.")
    search_p.add_argument("query", help="Search terms")
    search_p.add_argument("--mode", default="any", choices=["any", "all", "exact_phrase"])
    search_p.add_argument("--exclude", help="Comma-separated terms to exclude")
    search_p.add_argument("--limit", type=int, default=5)
    search_p.add_argument("--language", help="ISO 639-1 language code")
    search_p.add_argument("--full-content", action="store_true")
    search_p.add_argument("--sort", default="date", choices=["date", "relevance", "popularity"])

    # --- extract command ---
    extract_p = subparsers.add_parser("extract", help="Extract a single article from a URL.")
    extract_p.add_argument("url", help="Article URL")
    extract_p.add_argument("--js", action="store_true", help="Use JS rendering")
    extract_p.add_argument("--timeout", type=int, default=15)

    # --- discover command ---
    discover_p = subparsers.add_parser("discover", help="Discover articles from a website homepage.")
    discover_p.add_argument("url", help="Website URL (homepage or section)")
    discover_p.add_argument("--limit", type=int, default=10)
    discover_p.add_argument("--max-pages", type=int, default=20)
    discover_p.add_argument("--js", action="store_true", help="Use JS crawling")
    discover_p.add_argument("--no-rss", action="store_true", help="Skip RSS discovery and crawl directly")

    args = parser.parse_args()

    try:
        if args.command == "fetch":
            results = fetch(
                category=args.category,
                location=args.location,
                max_results=args.limit,
                language=args.language,
                full_content=args.full_content,
                sort_by=args.sort,
            )
            _print_json(results)

        elif args.command == "search":
            exclude = args.exclude.split(",") if args.exclude else None
            results = search(
                query=args.query,
                query_mode=args.mode,
                exclude_terms=exclude,
                max_results=args.limit,
                language=args.language,
                full_content=args.full_content,
                sort_by=args.sort,
            )
            _print_json(results)

        elif args.command == "extract":
            article = get_article(args.url, timeout=args.timeout, js=args.js)
            _print_json(article)

        elif args.command == "discover":
            articles = discover_and_get(
                args.url,
                limit=args.limit,
                max_pages=args.max_pages,
                js=args.js,
                prefer_rss=not args.no_rss,
            )
            _print_json(articles)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()