from open_news import fetch


def main():
    articles = fetch(category="tech", max_results=5)
    print(f"Fetched {len(articles)} article(s)")
    for article in articles:
        print(f"- {article.get('title')} | {article.get('url')}")


if __name__ == "__main__":
    main()
