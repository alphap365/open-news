"""Fetch stories and inspect the articles grouped under each representative."""

from open_news import fetch


def main() -> None:
    stories = fetch(category="science", time_limit="w", max_results=10)
    if not isinstance(stories, list):
        raise TypeError("Expected finite results; do not set refresh_interval.")

    for story in stories:
        sources = story.get("sources", [])
        print(f"\n{story.get('title')}")
        print(f"Sources ({len(sources)}): {', '.join(sources) or 'Unknown'}")
        print(f"Representative: {story.get('url')}")

        related = story.get("similar_articles", [])
        for article in related:
            print(f"  - {article.get('title')} | {article.get('url')}")


if __name__ == "__main__":
    main()
