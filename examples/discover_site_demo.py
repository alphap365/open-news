"""Discover and group articles from a news site."""

import argparse

from open_news import discover_and_get


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="A news homepage, section page, or feed URL.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--js", action="store_true", help="Render pages with a browser.")
    args = parser.parse_args()

    stories = discover_and_get(args.url, limit=args.limit, js=args.js)
    for story in stories:
        sources = ", ".join(story.get("sources", [])) or story.get("source", "Unknown")
        print(f"\n{story.get('title')} [{sources}]")
        print(story.get("url"))
        for article in story.get("similar_articles", []):
            print(f"  - {article.get('title')} | {article.get('url')}")


if __name__ == "__main__":
    main()
