from open_news import fetch


def main():
    stories = fetch(category="tech", time_limit="w", max_results=5)
    if not isinstance(stories, list):
        raise TypeError("Expected finite results; do not set refresh_interval.")

    print(f"Fetched {len(stories)} grouped story/stories")
    for story in stories:
        sources = ", ".join(story.get("sources", [])) or story.get("source", "Unknown")
        print(f"\n- {story.get('title')} [{sources}]")
        print(f"  {story.get('url')}")
        for related in story.get("similar_articles", [])[:3]:
            print(f"  Related: {related.get('title')} | {related.get('url')}")


if __name__ == "__main__":
    main()
