"""Fetch stories, filter by topic, then rank them against a query."""

from open_news import fetch, filter_articles, rank_articles


def main() -> None:
    stories = fetch(
        category="business",
        time_limit="w",
        max_results=30,
        language="en",
        whitelist=["reuters.com", "bbc.com"],
    )
    if not isinstance(stories, list):
        raise TypeError("Expected finite results; do not set refresh_interval.")

    topical_stories = filter_articles(
        stories,
        topic=["markets", "interest rates"],
        topic_mode="any",
    )
    ranked_stories = rank_articles(
        topical_stories,
        query="central bank interest rate decisions",
        method="auto",
        top_k=10,
    )

    print(f"{len(ranked_stories)} matching story/stories")
    for story in ranked_stories:
        score = story.get("_rank_score", 0.0)
        print(f"\n[{score:.3f}] {story.get('title')}")
        print(f"  {story.get('url')}")
        print(f"  Sources: {', '.join(story.get('sources', []))}")


if __name__ == "__main__":
    main()
