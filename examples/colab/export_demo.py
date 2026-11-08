from open_news import cluster_articles, export, fetch, rank_articles


def main():
    articles = fetch(category="tech", max_results=20)
    if not isinstance(articles, list):
        raise TypeError("Expected finite results; do not set refresh_interval.")

    ranked = rank_articles(articles, query="artificial intelligence", method="auto")
    clusters = cluster_articles(ranked, threshold=0.72, drop_singletons=True)

    markdown = export.to_markdown(clusters, path="demo_output.md")
    json_text = export.to_json(clusters, path="demo_output.json")

    print(f"Markdown length: {len(markdown)}")
    print(f"JSON length: {len(json_text)}")
    print(f"Clusters produced: {len(clusters)}")


if __name__ == "__main__":
    main()
