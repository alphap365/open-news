from datetime import date, timedelta

from open_news import search


def main():
    today = date.today()
    start_date = (today - timedelta(days=30)).isoformat()
    end_date = today.isoformat()
    stories = search(
        "renewable energy",
        country="in",
        start_date=start_date,
        end_date=end_date,
        max_results=5,
    )
    if not isinstance(stories, list):
        raise TypeError("Expected finite results; do not set refresh_interval.")

    print(f"Found {len(stories)} grouped story/stories ({start_date} to {end_date})")
    for story in stories:
        sources = ", ".join(story.get("sources", [])) or story.get("source", "Unknown")
        print(f"\n- {story.get('title')} [{sources}]")
        print(f"  {story.get('url')}")
        for related in story.get("similar_articles", [])[:3]:
            print(f"  Related: {related.get('title')} | {related.get('url')}")


if __name__ == "__main__":
    main()
