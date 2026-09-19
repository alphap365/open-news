#!/usr/bin/env python3
"""Numbered terminal interface for open-news.
"""

import json
import os
import sys
import webbrowser
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from open_news.api import discover_and_get, fetch, get_article, search, search_site, stream_search
from open_news.processing.batch import batch_summarize, search_and_summarize


class _Color:
    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
        if self.enabled and os.name == "nt":
            try:
                import colorama
                colorama.init()
            except ImportError:
                pass

    def _wrap(self, code, t): return f"\033[{code}m{t}\033[0m" if self.enabled else t
    def bold(self, t): return self._wrap("1", t)
    def dim(self, t): return self._wrap("2", t)
    def cyan(self, t): return self._wrap("36", t)
    def green(self, t): return self._wrap("32", t)
    def yellow(self, t): return self._wrap("33", t)
    def red(self, t): return self._wrap("31", t)


C = _Color()

CATEGORIES = ("general", "business", "tech", "sports", "health", "science", "entertainment")
SORTS = ("date", "relevance", "popularity")


def _article_source(article: Dict[str, Any]) -> str:
    """Best-effort source label. Articles from the crawler path don't carry
    a top-level `source` field, so fall back to the URL's domain rather
    than showing a bare 'Unknown' for every discovered article."""
    src = article.get("source") or article.get("meta", {}).get("site_name")
    if src:
        return src
    url = article.get("url") or ""
    domain = urlparse(url).netloc.replace("www.", "")
    return domain or "Unknown source"


class Settings:
    """User-adjustable defaults, held for the session."""

    def __init__(self) -> None:
        self.language: Optional[str] = None
        self.sort_by: str = "date"
        self.full_content: bool = False
        self.js: bool = False
        self.default_limit: int = 10
        self.whitelist: Optional[List[str]] = None
        self.blacklist: Optional[List[str]] = None
        self.country: Optional[str] = None  # v1.0.2: ISO 3166-1 alpha-2, search() only

    def summary_line(self) -> str:
        wl = ",".join(self.whitelist) if self.whitelist else "none"
        bl = ",".join(self.blacklist) if self.blacklist else "none"
        return (
            f"language={self.language or 'any'}  country={self.country or 'default'}  sort={self.sort_by}  "
            f"full_content={'on' if self.full_content else 'off'}  "
            f"js={'on' if self.js else 'off'}  default_limit={self.default_limit}  "
            f"whitelist={wl}  blacklist={bl}"
        )


class OpenNewsTUI:
    """Input-driven terminal interface for the public open-news API."""

    def __init__(self) -> None:
        self.articles: List[Dict[str, Any]] = []
        self.settings = Settings()

    def run(self) -> None:
        self._print_header()
        while True:
            self._print_menu()
            try:
                choice = input("Choose an option: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                return

            actions = {
                "0": None,
                "1": self._fetch_news,
                "2": self._search_news,
                "3": self._discover_news,
                "4": self._search_site,
                "5": self._extract_article,
                "6": self._summarize,
                "7": self._view_articles,
                "8": self._settings_menu,
                "9": self.articles.clear,
                "10": self._watch_news,
            }
            if choice == "0":
                print("Goodbye.")
                return
            action = actions.get(choice)
            if action is None:
                print(C.yellow("\nPlease choose a valid option number."))
                continue
            if choice == "9":
                action()
                print(C.dim("\nArticle list cleared."))
            else:
                action()

    def _print_header(self) -> None:
        print("\n" + "=" * 64)
        print(C.bold("OPEN-NEWS | fetch, search, discover, understand"))
        print("=" * 64)

    def _print_menu(self) -> None:
        print("\n" + C.cyan("[1]") + " Fetch category news")
        print(C.cyan("[2]") + " Search by keyword")
        print(C.cyan("[3]") + " Discover a website")
        print(C.cyan("[4]") + " Search one domain")
        print(C.cyan("[5]") + " Extract one article")
        print(C.cyan("[6]") + " Summarize URL(s) or a topic")
        print(C.cyan("[7]") + " View loaded articles")
        print(C.cyan("[8]") + " Settings")
        print(C.cyan("[9]") + " Clear loaded articles")
        print(C.cyan("[10]") + " Live refresh (category or keyword search)")
        print(C.cyan("[0]") + " Exit")
        if self.articles:
            print(C.dim(f"Loaded articles: {len(self.articles)}"))
        print(C.dim(self.settings.summary_line()))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _fetch_news(self) -> None:
        category = self._prompt_category()
        if category is None:
            return
        location = self._prompt_location()
        limit = self._prompt_limit()
        try:
            results = fetch(
                category=category, location=location, max_results=limit,
                language=self.settings.language, sort_by=self.settings.sort_by,
                full_content=self.settings.full_content, js=self.settings.js,
                whitelist=self.settings.whitelist, blacklist=self.settings.blacklist,
            )
            label = f"Fetched {category} news ({location})" if location else f"Fetched {category} news"
            self._replace_articles(results, label)
        except Exception as error:
            self._show_error(error)

    def _search_news(self) -> None:
        query = input("Search query (blank to cancel): ").strip()
        if not query:
            return
        mode = input("Match mode [any/all/exact_phrase] (blank = any): ").strip().lower() or "any"
        if mode not in ("any", "all", "exact_phrase"):
            print(C.yellow(f"Unknown mode {mode!r}, using 'any'."))
            mode = "any"
        exclude_raw = input("Exclude terms, comma-separated (blank = none): ").strip()
        exclude_terms = [t.strip() for t in exclude_raw.split(",") if t.strip()] or None
        start_date, end_date = self._prompt_date_range()
        limit = self._prompt_limit()
        # search() only supports date/relevance ranking (no popularity
        # clustering); silently fall back rather than raising deep in the stack.
        sort_by = self.settings.sort_by if self.settings.sort_by != "popularity" else "date"
        try:
            results = search(
                query, query_mode=mode, exclude_terms=exclude_terms, max_results=limit,
                language=self.settings.language, sort_by=sort_by,
                start_date=start_date, end_date=end_date, country=self.settings.country,
                full_content=self.settings.full_content, js=self.settings.js,
                whitelist=self.settings.whitelist, blacklist=self.settings.blacklist,
            )
            self._replace_articles(results, f"Search results for {query!r}")
        except Exception as error:
            self._show_error(error)

    @staticmethod
    def _prompt_date_range() -> "tuple[Optional[str], Optional[str]]":
        """Optional custom date range (v1.0.2) — 'YYYY-MM-DD', either side
        may be left blank for an open-ended range. Overrides the recency
        window (time_limit) when either is given."""
        raw = input("Custom date range? Start date YYYY-MM-DD (blank = skip): ").strip()
        if not raw:
            return None, None
        end = input("End date YYYY-MM-DD (blank = open-ended): ").strip()
        return raw or None, end or None

    def _discover_news(self) -> None:
        url = input("Website URL (blank to cancel): ").strip()
        if not url:
            return
        limit = self._prompt_limit()
        try:
            results = discover_and_get(
                url, limit=limit, js=self.settings.js, full_content=self.settings.full_content,
            )
            self._replace_articles(results, f"Discovered articles from {url}")
        except Exception as error:
            self._show_error(error)

    def _search_site(self) -> None:
        keyword = input("Search keyword (blank to cancel): ").strip()
        if not keyword:
            return
        domain = input("Domain, e.g. reuters.com (blank to cancel): ").strip()
        if not domain:
            return
        limit = self._prompt_limit()
        try:
            results = search_site(
                keyword, domain, limit=limit, language=self.settings.language,
                full_content=self.settings.full_content, js=self.settings.js,
            )
            self._replace_articles(results, f"{keyword!r} on {domain}")
        except Exception as error:
            self._show_error(error)

    def _summarize(self) -> None:
        print("\n[a] Summarize a topic search   [b] Summarize specific URL(s)")
        mode = input("Choose (blank to cancel): ").strip().lower()
        if mode not in ("a", "b"):
            return
        try:
            if mode == "a":
                query = input("Topic (blank to cancel): ").strip()
                if not query:
                    return
                limit = self._prompt_limit()
                results = search_and_summarize(query, limit=limit, js=self.settings.js)
            else:
                raw = input("URLs, comma-separated (blank to cancel): ").strip()
                if not raw:
                    return
                urls = [u.strip() for u in raw.split(",") if u.strip()]
                results = batch_summarize(urls, js=self.settings.js)
        except Exception as error:
            self._show_error(error)
            return

        print()
        ok = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") != "success"]
        for r in ok:
            print(C.bold(C.cyan(r.get("title") or r.get("url", "Untitled"))))
            print(f"  {r.get('summary', '')}")
            print(C.dim(f"  {r.get('url', '')}\n"))
        if failed:
            print(C.red(f"{len(failed)} failed:"))
            for r in failed:
                print(f"  {r.get('url', '')} — {r.get('error', 'unknown error')}")
        print(C.dim(f"{len(ok)}/{len(results)} succeeded."))

    def _watch_news(self) -> None:
        print("\n[a] Live category/location fetch   [b] Live keyword search")
        mode = input("Choose (blank to cancel): ").strip().lower()
        if mode not in ("a", "b"):
            return
        if mode == "a":
            self._watch_fetch()
        else:
            self._watch_search()

    def _watch_fetch(self) -> None:
        category = self._prompt_category()
        if category is None:
            return
        location = self._prompt_location()
        limit = self._prompt_limit()
        interval = self._prompt_refresh_interval()
        subject = location or category
        print(f"\nWatching {subject} news every {interval} seconds.")
        print("Press Ctrl+C to stop live refresh and return to the menu.")
        try:
            stream = fetch(
                category=category, location=location, max_results=limit,
                refresh_interval=interval, language=self.settings.language,
            )
            for new_articles in stream:
                if not new_articles:
                    continue
                self.articles.extend(new_articles)
                stamp = datetime.now().strftime("%H:%M:%S")
                self._clear_screen()
                self._print_header()
                print(f"Watching {subject} news every {interval} seconds.")
                print(f"Last refresh: {stamp} | {len(new_articles)} new article(s)")
                self._print_article_list(self.articles)
        except KeyboardInterrupt:
            print("\nLive refresh stopped.")
        except Exception as error:
            self._show_error(error)

    def _watch_search(self) -> None:
        """Live keyword search (v1.0.2) via stream_search() — the search()
        equivalent of _watch_fetch(), closing the previous TUI gap where
        menu 10 only covered category/location fetch."""
        query = input("Search query (blank to cancel): ").strip()
        if not query:
            return
        limit = self._prompt_limit()
        interval = self._prompt_refresh_interval()
        sort_by = self.settings.sort_by if self.settings.sort_by != "popularity" else "date"
        print(f"\nWatching search {query!r} every {interval} seconds.")
        print("Press Ctrl+C to stop live refresh and return to the menu.")
        try:
            stream = stream_search(
                query, refresh_interval=interval, max_results=limit,
                language=self.settings.language, country=self.settings.country,
                sort_by=sort_by, whitelist=self.settings.whitelist,
                blacklist=self.settings.blacklist, js=self.settings.js,
            )
            for new_articles in stream:
                if not new_articles:
                    continue
                self.articles.extend(new_articles)
                stamp = datetime.now().strftime("%H:%M:%S")
                self._clear_screen()
                self._print_header()
                print(f"Watching search {query!r} every {interval} seconds.")
                print(f"Last refresh: {stamp} | {len(new_articles)} new article(s)")
                self._print_article_list(self.articles)
        except KeyboardInterrupt:
            print("\nLive refresh stopped.")
        except Exception as error:
            self._show_error(error)

    def _extract_article(self) -> None:
        url = input("Article URL (blank to cancel): ").strip()
        if not url:
            return
        try:
            article = get_article(url, js=self.settings.js)
            if not article.get("text"):
                print(C.yellow("\nNo article text was extracted from that URL."))
                return
            self.articles.insert(0, article)
            print(C.green("\nArticle extracted and added to the loaded list."))
            self._print_article(article, 1)
            self._article_followup(article)
        except Exception as error:
            self._show_error(error)

    def _view_articles(self) -> None:
        if not self.articles:
            print(C.yellow("\nNo articles loaded yet."))
            return

        print("\nLoaded articles")
        print("-" * 64)
        self._print_article_list(self.articles)

        selection = input("\nArticle number (blank to return): ").strip()
        if not selection:
            return
        try:
            index = int(selection)
            if not 1 <= index <= len(self.articles):
                raise ValueError
        except ValueError:
            print(C.yellow("Invalid article number."))
            return
        article = self.articles[index - 1]
        self._print_article(article, index)
        self._article_followup(article)

    def _article_followup(self, article: Dict[str, Any]) -> None:
        choice = input("\n[o] Open in browser  [s] Save to file  [blank] Back: ").strip().lower()
        if choice == "o":
            url = article.get("url")
            if url:
                webbrowser.open(url)
            else:
                print(C.yellow("No URL to open."))
        elif choice == "s":
            self._save_to_file(article)

    def _save_to_file(self, data: Any) -> None:
        path = input("Save as (e.g. article.json): ").strip()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str, ensure_ascii=False)
            print(C.green(f"Saved to {path}"))
        except OSError as e:
            print(C.red(f"Could not save: {e}"))

    def _settings_menu(self) -> None:
        while True:
            print("\n" + C.bold("Settings"))
            print(f"[1] Language          ({self.settings.language or 'any'})")
            print(f"[2] Sort order        ({self.settings.sort_by})")
            print(f"[3] Full content      ({'on' if self.settings.full_content else 'off'})")
            print(f"[4] JS rendering      ({'on' if self.settings.js else 'off'})")
            print(f"[5] Default limit     ({self.settings.default_limit})")
            print(f"[6] Whitelist domains ({','.join(self.settings.whitelist) if self.settings.whitelist else 'none'})")
            print(f"[7] Blacklist domains ({','.join(self.settings.blacklist) if self.settings.blacklist else 'none'})")
            print(f"[8] Country (search)  ({self.settings.country or 'default (us)'})")
            print("[0] Back")
            choice = input("Choose an option: ").strip()
            if choice == "0" or not choice:
                return
            if choice == "1":
                v = input("Language code (e.g. en), blank for any: ").strip()
                self.settings.language = v or None
            elif choice == "2":
                v = input(f"Sort by {SORTS} (blank to keep): ").strip().lower()
                if v in SORTS:
                    self.settings.sort_by = v
                elif v:
                    print(C.yellow("Unknown sort option."))
            elif choice == "3":
                self.settings.full_content = not self.settings.full_content
            elif choice == "4":
                self.settings.js = not self.settings.js
                if self.settings.js:
                    print(C.dim("Note: JS rendering requires the 'js' extra "
                                "(pip install open-news-api[js] && playwright install chromium)."))
            elif choice == "5":
                v = input("New default limit: ").strip()
                try:
                    self.settings.default_limit = max(1, min(int(v), 200))
                except ValueError:
                    print(C.yellow("Invalid number."))
            elif choice == "6":
                v = input("Whitelist domains, comma-separated (blank = clear): ").strip()
                self.settings.whitelist = [d.strip() for d in v.split(",") if d.strip()] or None
            elif choice == "7":
                v = input("Blacklist domains, comma-separated (blank = clear): ").strip()
                self.settings.blacklist = [d.strip() for d in v.split(",") if d.strip()] or None
            elif choice == "8":
                v = input("Country code for search(), e.g. us, in, gb (blank = default): ").strip()
                self.settings.country = v or None
            else:
                print(C.yellow("Please choose a number from 0 to 8."))

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _replace_articles(self, results: Sequence[Dict[str, Any]], label: str) -> None:
        self.articles = list(results)
        print(f"\n{label}: {len(self.articles)} article(s).")
        self._print_article_list(self.articles)

    @staticmethod
    def _print_article_list(articles: Sequence[Dict[str, Any]]) -> None:
        for index, article in enumerate(articles, 1):
            title = article.get("title") or "Untitled"
            print(f"{C.cyan(f'[{index}]')} {title}")
            print(C.dim(f"    {_article_source(article)}"))

    @staticmethod
    def _clear_screen() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _print_article(self, article: Dict[str, Any], index: Optional[int] = None) -> None:
        title = article.get("title") or "Untitled"
        header = f"[{index}] {title}" if index is not None else title
        print(f"\n{C.bold(C.cyan(header))}")
        print(C.dim("-" * min(64, max(20, len(title)))))
        print(f"Source: {_article_source(article)}")
        print(f"Published: {article.get('publish_date') or article.get('published') or 'Unknown'}")
        print(f"URL: {article.get('url') or 'Unknown'}")
        authors = article.get("authors") or []
        if authors:
            print(f"Authors: {', '.join(authors)}")
        text = (article.get("text") or article.get("description")
                or article.get("meta", {}).get("description") or "No text available.").strip()
        print(f"\n{text[:2000]}")
        if len(text) > 2000:
            print(C.dim("\n[Text truncated. Open the URL for the complete article.]"))

    def _prompt_category(self) -> Optional[str]:
        print("\nCategories: " + ", ".join(CATEGORIES))
        category = input("Category (blank to cancel): ").strip().lower()
        if not category:
            return None
        if category not in CATEGORIES:
            print(C.yellow("Unknown category."))
            return None
        return category

    @staticmethod
    def _prompt_location() -> Optional[str]:
        location = input("Location/country code, e.g. us or in (blank for category): ").strip().lower()
        return location or None

    def _prompt_limit(self) -> int:
        value = input(f"Maximum articles [{self.settings.default_limit}]: ").strip()
        if not value:
            return self.settings.default_limit
        try:
            return max(1, min(int(value), 200))
        except ValueError:
            print(C.yellow(f"Invalid limit; using {self.settings.default_limit}."))
            return self.settings.default_limit

    @staticmethod
    def _prompt_refresh_interval() -> int:
        value = input("Refresh interval in seconds [60]: ").strip()
        if not value:
            return 60
        try:
            return max(5, int(value))
        except ValueError:
            print(C.yellow("Invalid interval; using 60 seconds."))
            return 60

    @staticmethod
    def _show_error(error: Exception) -> None:
        print(C.red(f"\nError: {error}"))


def run_tui() -> None:
    """Launch the terminal interface."""
    OpenNewsTUI().run()


if __name__ == "__main__":
    run_tui()