from open_news import search


def main():
    articles = search(
        "renewable energy",
        country="in",
        start_date="2026-01-01",
        max_results=5,
    )
    print(f"Found {len(articles)} result(s)")
    for article in articles:
        print(f"- {article.get('title')} | {article.get('source')}")


if __name__ == "__main__":
    main()
