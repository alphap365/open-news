"""Search asynchronously and print grouped article sources."""

import asyncio

from open_news import search


async def main() -> None:
    stories = await search(
        "renewable energy storage",
        query_mode="all",
        country="in",
        max_results=10,
        language="en",
        async_=True,
    )
    for story in stories:
        sources = ", ".join(story.get("sources", [])) or "Unknown"
        print(f"\n{story.get('title')} [{sources}]")
        print(story.get("url"))
        for article in story.get("similar_articles", []):
            print(f"  - {article.get('title')} | {article.get('url')}")


if __name__ == "__main__":
    asyncio.run(main())
