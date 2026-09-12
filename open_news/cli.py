#!/usr/bin/env python3
"""Command-line interface for open-news.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional  # noqa: F401 (Any used by config loader)

from .api import fetch, search, get_article, discover_and_get, search_site
from .processing.batch import batch_summarize, search_and_summarize

__all__ = ["main"]


# ----------------------------------------------------------------------
# User preferences, written by install.sh's wizard mode (or hand-edited).
# Only used to set argparse *defaults* — any flag the person actually
# passes on the command line still wins.
# ----------------------------------------------------------------------

_CONFIG_PATH = os.path.expanduser("~/.config/open-news/config.json")


def _load_user_config() -> Dict[str, Any]:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


_CONFIG = _load_user_config()


# ----------------------------------------------------------------------
# Minimal color helper — no dependency, disables itself when not useful.
# ----------------------------------------------------------------------

class _Color:
    def __init__(self) -> None:
        self.enabled = (
            sys.stdout.isatty()
            and os.environ.get("NO_COLOR") is None
            and os.environ.get("TERM") != "dumb"
        )
        if self.enabled and os.name == "nt":
            try:
                import colorama  # optional, only used if already installed
                colorama.init()
            except ImportError:
                # ANSI works natively on Windows 10+ terminals anyway;
                # if it doesn't render cleanly, NO_COLOR=1 is the escape hatch.
                pass

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, t): return self._wrap("1", t)
    def dim(self, t): return self._wrap("2", t)
    def cyan(self, t): return self._wrap("36", t)
    def green(self, t): return self._wrap("32", t)
    def yellow(self, t): return self._wrap("33", t)
    def red(self, t): return self._wrap("31", t)


C = _Color()


# ----------------------------------------------------------------------
# Output rendering
# ----------------------------------------------------------------------

def _save(data: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)
    print(C.dim(f"Saved to {path}"), file=sys.stderr)


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _print_articles_pretty(articles: List[Dict]) -> None:
    if not articles:
        print(C.yellow("No articles found."))
        return
    for i, a in enumerate(articles, 1):
        title = a.get("title") or "Untitled"
        source = a.get("source") or a.get("meta", {}).get("site_name") or ""
        date = a.get("published") or a.get("publish_date") or ""
        url = a.get("url") or ""
        print(f"{C.bold(f'[{i}]')} {C.cyan(title)}")
        meta_bits = [b for b in (source, date) if b]
        if meta_bits:
            print(f"    {C.dim(' | '.join(meta_bits))}")
        print(f"    {url}")
    print(C.dim(f"\n{len(articles)} article(s)."))


def _print_article_pretty(article: Dict) -> None:
    title = article.get("title") or "Untitled"
    print(C.bold(C.cyan(title)))
    print(C.dim("-" * min(70, max(20, len(title)))))
    source = article.get("source") or ""
    date = article.get("publish_date") or ""
    if source or date:
        print(C.dim(f"{source}  {date}".strip()))
    authors = article.get("authors") or []
    if authors:
        print(f"By: {', '.join(authors)}")
    print(f"URL: {article.get('url', '')}")
    text = (article.get("text") or "").strip()
    if text:
        print()
        print(text[:2000])
        if len(text) > 2000:
            print(C.dim("\n[truncated — full text in JSON/--save output]"))
    else:
        print(C.yellow("\nNo article text extracted from this URL."))


def _print_summaries_pretty(results: List[Dict]) -> None:
    ok = [r for r in results if r.get("status") == "success"]
    failed = [r for r in results if r.get("status") != "success"]
    for r in ok:
        print(C.bold(C.cyan(r.get("title") or r.get("url", "Untitled"))))
        print(f"  {r.get('summary', '')}")
        print(C.dim(f"  {r.get('url', '')}"))
        print()
    if failed:
        print(C.red(f"{len(failed)} failed:"))
        for r in failed:
            print(f"  {r.get('url', '')} — {r.get('error', 'unknown error')}")
    print(C.dim(f"{len(ok)}/{len(results)} succeeded."))


def _emit(data: Any, args: argparse.Namespace, kind: str) -> None:
    """Route output to JSON / pretty / --save per the shared output flags."""
    if getattr(args, "save", None):
        _save(data, args.save)
    if args.format == "json":
        _print_json(data)
        return
    if kind == "articles":
        _print_articles_pretty(data)
    elif kind == "article":
        _print_article_pretty(data)
    elif kind == "summaries":
        _print_summaries_pretty(data)
    else:
        _print_json(data)


def _csv_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [v.strip() for v in value.split(",") if v.strip()]


# ----------------------------------------------------------------------
# Shared argument groups
# ----------------------------------------------------------------------

def _add_output_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--format", choices=["pretty", "json"], default=_CONFIG.get("format", "pretty"),
                    help="Output style (default: pretty, or your configured default). Use json for scripting/piping.")
    p.add_argument("--save", metavar="FILE", help="Also write the full JSON result to FILE.")


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--whitelist", metavar="DOMAINS", help="Comma-separated domains to keep, e.g. bbc.com,reuters.com")
    p.add_argument("--blacklist", metavar="DOMAINS", help="Comma-separated domains to drop.")
    p.add_argument("--dedupe", dest="dedupe", action="store_true", default=True, help="Dedupe results (default: on).")
    p.add_argument("--no-dedupe", dest="dedupe", action="store_false", help="Disable deduplication.")


def _add_fetch_content_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--full-content", action="store_true", help="Crawl+extract full text for each result.")
    p.add_argument("--js", action="store_true", help="Use headless-browser rendering for --full-content/extract.")


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="open-news",
        description="Fetch, search, and extract news articles from the command line.",
        epilog=(
            "Examples:\n"
            "  open-news fetch --category tech --limit 5\n"
            "  open-news search \"artificial intelligence\" --mode all --exclude sports\n"
            "  open-news extract https://example.com/article --save article.json\n"
            "  open-news discover https://www.bbc.com --limit 10\n"
            "  open-news search-site \"climate policy\" reuters.com\n"
            "  open-news summarize https://example.com/a https://example.com/b\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="store_true", help="Print the installed open-news version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    # Defaults from ~/.config/open-news/config.json, if present (see
    # _load_user_config above). Explicit CLI flags always override these.
    cfg_category = _CONFIG.get("category", "general")
    cfg_language = _CONFIG.get("language")
    cfg_sort = _CONFIG.get("sort_by", "date")
    cfg_format = _CONFIG.get("format", "pretty")

    # --- fetch ---
    fetch_p = subparsers.add_parser("fetch", help="Fetch live category/location news.")
    fetch_p.add_argument("--category", default=cfg_category,
                          choices=["general", "business", "tech", "sports", "health", "science", "entertainment"])
    fetch_p.add_argument("--location", help="Country/region code, e.g. us, in.")
    fetch_p.add_argument("--limit", type=int, default=10)
    fetch_p.add_argument("--language", default=cfg_language, help="ISO 639-1 language code, e.g. en.")
    fetch_p.add_argument("--sort", default=cfg_sort, choices=["date", "relevance", "popularity"])
    fetch_p.add_argument("--time-limit", default="d", choices=["d", "w", "m"], help="Recency window (day/week/month).")
    _add_fetch_content_args(fetch_p)
    _add_filter_args(fetch_p)
    _add_output_args(fetch_p)

    # --- search ---
    search_p = subparsers.add_parser("search", help="Search news by keyword (Google News).")
    search_p.add_argument("query", help="Search terms.")
    search_p.add_argument("--mode", default="any", choices=["any", "all", "exact_phrase"])
    search_p.add_argument("--exclude", metavar="TERMS", help="Comma-separated terms to exclude.")
    search_p.add_argument("--limit", type=int, default=10)
    search_p.add_argument("--language", default=cfg_language, help="ISO 639-1 language code.")
    # NOTE: search only supports date/relevance ranking (no popularity
    # clustering pass) — this mirrors config.VALID_SORT_SEARCH exactly so
    # an invalid combination is rejected here, at the CLI layer, with a
    # clear argparse error instead of a ValueError from deep in the stack.
    search_p.add_argument("--sort", default=cfg_sort if cfg_sort in ("date", "relevance") else "date",
                           choices=["date", "relevance"])
    search_p.add_argument("--time-limit", default="d", choices=["d", "w", "m"])
    _add_fetch_content_args(search_p)
    _add_filter_args(search_p)
    _add_output_args(search_p)

    # --- extract ---
    extract_p = subparsers.add_parser("extract", help="Extract a single article from a URL.")
    extract_p.add_argument("url", help="Article URL.")
    extract_p.add_argument("--js", action="store_true", help="Use headless-browser rendering.")
    extract_p.add_argument("--timeout", type=int, default=15)
    _add_output_args(extract_p)

    # --- discover ---
    discover_p = subparsers.add_parser("discover", help="Discover articles from a website (RSS or crawl).")
    discover_p.add_argument("url", help="Website URL (homepage or section page).")
    discover_p.add_argument("--limit", type=int, default=10)
    discover_p.add_argument("--max-pages", type=int, default=None, help="Crawl page budget (default: auto).")
    discover_p.add_argument("--max-depth", type=int, default=None, help="Crawl link-hop depth (default: auto).")
    discover_p.add_argument("--js", action="store_true", help="Use headless-browser crawling.")
    discover_p.add_argument("--no-rss", action="store_true", help="Skip RSS discovery and crawl directly.")
    discover_p.add_argument("--full-content", action="store_true", help="Enrich RSS-path results with full text.")
    discover_p.add_argument("--no-dedupe", dest="dedupe", action="store_false", default=True)
    _add_output_args(discover_p)

    # --- search-site ---
    site_p = subparsers.add_parser("search-site", help="Search a single news domain.")
    site_p.add_argument("keyword", help="Search terms.")
    site_p.add_argument("domain", help="Domain to search within, e.g. reuters.com.")
    site_p.add_argument("--limit", type=int, default=10)
    site_p.add_argument("--mode", default="any", choices=["any", "all", "exact_phrase"])
    site_p.add_argument("--language", help="ISO 639-1 language code.")
    _add_fetch_content_args(site_p)
    _add_output_args(site_p)

    # --- summarize ---
    summarize_p = subparsers.add_parser(
        "summarize", help="Summarize one or more article URLs, or a topic search."
    )
    summarize_p.add_argument("urls", nargs="*", help="Article URLs to summarize.")
    summarize_p.add_argument("--query", help="Instead of URLs, search this topic and summarize the results.")
    summarize_p.add_argument("--limit", type=int, default=10, help="Result limit when using --query.")
    summarize_p.add_argument("--sentences", type=int, default=3, help="Sentences per summary.")
    summarize_p.add_argument("--workers", type=int, default=5, help="Concurrent fetch/extract threads.")
    summarize_p.add_argument("--js", action="store_true")
    _add_output_args(summarize_p)

    return parser


# ----------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------

def _run(args: argparse.Namespace) -> None:
    if args.command == "fetch":
        results = fetch(
            category=args.category, location=args.location, max_results=args.limit,
            language=args.language, sort_by=args.sort, time_limit=args.time_limit,
            full_content=args.full_content, js=args.js,
            whitelist=_csv_list(args.whitelist), blacklist=_csv_list(args.blacklist),
            dedupe=args.dedupe,
        )
        _emit(results, args, "articles")

    elif args.command == "search":
        results = search(
            query=args.query, query_mode=args.mode, exclude_terms=_csv_list(args.exclude),
            max_results=args.limit, language=args.language, sort_by=args.sort,
            time_limit=args.time_limit, full_content=args.full_content, js=args.js,
            whitelist=_csv_list(args.whitelist), blacklist=_csv_list(args.blacklist),
            dedupe=args.dedupe,
        )
        _emit(results, args, "articles")

    elif args.command == "extract":
        article = get_article(args.url, timeout=args.timeout, js=args.js)
        _emit(article, args, "article")

    elif args.command == "discover":
        articles = discover_and_get(
            args.url, limit=args.limit, max_pages=args.max_pages, max_depth=args.max_depth,
            js=args.js, prefer_rss=not args.no_rss, full_content=args.full_content,
            dedupe=args.dedupe,
        )
        _emit(articles, args, "articles")

    elif args.command == "search-site":
        articles = search_site(
            args.keyword, args.domain, limit=args.limit, query_mode=args.mode,
            language=args.language, full_content=args.full_content, js=args.js,
        )
        _emit(articles, args, "articles")

    elif args.command == "summarize":
        if args.query:
            results = search_and_summarize(
                args.query, limit=args.limit, sentence_count=args.sentences,
                max_workers=args.workers, js=args.js,
            )
        elif args.urls:
            results = batch_summarize(
                args.urls, sentence_count=args.sentences, max_workers=args.workers, js=args.js,
            )
        else:
            raise SystemExit("summarize: provide one or more URLs, or --query TOPIC")
        _emit(results, args, "summaries")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        from . import __version__
        print(f"open-news {__version__}")
        return

    if not args.command:
        parser.print_help()
        return

    try:
        _run(args)
    except KeyboardInterrupt:
        print(C.dim("\nCancelled."), file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(C.red(f"Error: {e}"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()