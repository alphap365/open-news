#!/usr/bin/env python3
"""Simple numbered terminal interface for open-news."""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from open_news.api import discover_and_get, fetch, get_article, search


class OpenNewsTUI:
    """Input-driven terminal interface for the public open-news API."""

    CATEGORIES = ("general", "business", "tech", "sports", "health", "science", "entertainment")

    def __init__(self) -> None:
        self.articles: List[Dict[str, Any]] = []

    def run(self) -> None:
        """Run the menu until the user chooses Exit or sends EOF/Ctrl-C."""
        self._print_header()
        while True:
            self._print_menu()
            try:
                choice = input("Choose an option: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                return

            if choice == "0":
                print("Goodbye.")
                return
            if choice == "1":
                self._fetch_news()
            elif choice == "2":
                self._search_news()
            elif choice == "3":
                self._discover_news()
            elif choice == "4":
                self._extract_article()
            elif choice == "5":
                self._view_articles()
            elif choice == "6":
                self.articles.clear()
                print("\nArticle list cleared.")
            elif choice == "7":
                self._watch_news()
            else:
                print("\nPlease choose a number from 0 to 7.")

    def _print_header(self) -> None:
        print("\n" + "=" * 64)
        print("OPEN-NEWS | fetch, search, discover, understand")
        print("=" * 64)

    def _print_menu(self) -> None:
        print("\n[1] Fetch category news")
        print("[2] Search by keyword")
        print("[3] Discover a website")
        print("[4] Extract one article")
        print("[5] View loaded articles")
        print("[6] Clear loaded articles")
        print("[7] Live refresh category news")
        print("[0] Exit")
        if self.articles:
            print(f"Loaded articles: {len(self.articles)}")

    def _fetch_news(self) -> None:
        category = self._prompt_category()
        if category is None:
            return
        location = self._prompt_location()
        limit = self._prompt_limit()
        try:
            results = fetch(category=category, location=location, max_results=limit)
            label = f"Fetched {location} news" if location else f"Fetched {category} news"
            self._replace_articles(results, label)
        except Exception as error:
            self._show_error(error)

    def _search_news(self) -> None:
        query = input("Search query (blank to cancel): ").strip()
        if not query:
            return
        limit = self._prompt_limit()
        try:
            results = search(query, max_results=limit)
            self._replace_articles(results, f"Search results for {query!r}")
        except Exception as error:
            self._show_error(error)

    def _watch_news(self) -> None:
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
                category=category,
                location=location,
                max_results=limit,
                refresh_interval=interval,
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

    def _discover_news(self) -> None:
        url = input("Website URL (blank to cancel): ").strip()
        if not url:
            return
        limit = self._prompt_limit()
        try:
            results = discover_and_get(url, limit=limit)
            self._replace_articles(results, f"Discovered articles from {url}")
        except Exception as error:
            self._show_error(error)

    def _extract_article(self) -> None:
        url = input("Article URL (blank to cancel): ").strip()
        if not url:
            return
        try:
            article = get_article(url)
            if not article.get("text"):
                print("\nNo article text was extracted from that URL.")
                return
            self.articles.insert(0, article)
            print("\nArticle extracted and added to the loaded list.")
            self._print_article(article, 1)
        except Exception as error:
            self._show_error(error)

    def _view_articles(self) -> None:
        if not self.articles:
            print("\nNo articles loaded yet.")
            return

        print("\nLoaded articles")
        print("-" * 64)
        for index, article in enumerate(self.articles, 1):
            print(f"[{index}] {article.get('title') or 'Untitled'}")
            print(f"    {article.get('source') or 'Unknown source'} | {article.get('url', '')}")

        selection = input("\nArticle number (blank to return): ").strip()
        if not selection:
            return
        try:
            index = int(selection)
            if not 1 <= index <= len(self.articles):
                raise ValueError
        except ValueError:
            print("Invalid article number.")
            return
        self._print_article(self.articles[index - 1], index)

    def _replace_articles(self, results: Sequence[Dict[str, Any]], label: str) -> None:
        self.articles = list(results)
        print(f"\n{label}: {len(self.articles)} article(s).")
        self._print_article_list(self.articles)

    @staticmethod
    def _print_article_list(articles: Sequence[Dict[str, Any]]) -> None:
        for index, article in enumerate(articles, 1):
            print(f"[{index}] {article.get('title') or 'Untitled'}")

    @staticmethod
    def _clear_screen() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    def _print_article(self, article: Dict[str, Any], index: Optional[int] = None) -> None:
        title = article.get("title") or "Untitled"
        if index is not None:
            print(f"\n[{index}] {title}")
        else:
            print(f"\n{title}")
        print("-" * min(64, max(20, len(title))))
        print(f"Source: {article.get('source') or 'Unknown'}")
        print(f"Published: {article.get('publish_date') or article.get('published') or 'Unknown'}")
        print(f"URL: {article.get('url') or 'Unknown'}")
        authors = article.get("authors") or []
        if authors:
            print(f"Authors: {', '.join(authors)}")
        text = (article.get("text") or article.get("description") or "No text available.").strip()
        print(f"\n{text[:2000]}")
        if len(text) > 2000:
            print("\n[Text truncated. Open the URL for the complete article.]")

    def _prompt_category(self) -> Optional[str]:
        print("\nCategories: " + ", ".join(self.CATEGORIES))
        category = input("Category (blank to cancel): ").strip().lower()
        if not category:
            return None
        if category not in self.CATEGORIES:
            print("Unknown category.")
            return None
        return category

    @staticmethod
    def _prompt_location() -> Optional[str]:
        location = input("Location/country code, e.g. us or in (blank for category): ").strip().lower()
        return location or None

    @staticmethod
    def _prompt_limit() -> int:
        value = input("Maximum articles [5]: ").strip()
        if not value:
            return 5
        try:
            return max(1, min(int(value), 100))
        except ValueError:
            print("Invalid limit; using 5.")
            return 5

    @staticmethod
    def _prompt_refresh_interval() -> int:
        value = input("Refresh interval in seconds [60]: ").strip()
        if not value:
            return 60
        try:
            return max(5, int(value))
        except ValueError:
            print("Invalid interval; using 60 seconds.")
            return 60

    @staticmethod
    def _show_error(error: Exception) -> None:
        print(f"\nError: {error}")


def run_tui() -> None:
    """Launch the simple terminal interface."""
    OpenNewsTUI().run()


if __name__ == "__main__":
    run_tui()
