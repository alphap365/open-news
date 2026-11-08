"""Poll a search for new stories, then stop after a bounded number of batches."""

import argparse

from open_news import stream_search


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="artificial intelligence")
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Poll interval in seconds.",
    )
    parser.add_argument(
        "--batches",
        type=int,
        default=3,
        help="Number of updates to read.",
    )
    args = parser.parse_args()

    if args.interval < 5:
        parser.error("--interval must be at least 5 seconds")
    if args.batches < 1:
        parser.error("--batches must be at least 1")

    for batch_number, stories in enumerate(
        stream_search(args.query, refresh_interval=args.interval),
        start=1,
    ):
        print(f"\nUpdate {batch_number}: {len(stories)} new story/stories")
        for story in stories:
            sources = ", ".join(story.get("sources", [])) or story.get(
                "source", "Unknown"
            )
            print(f"- {story.get('title')} [{sources}]")
            print(f"  {story.get('url')}")
        if batch_number >= args.batches:
            break


if __name__ == "__main__":
    main()
