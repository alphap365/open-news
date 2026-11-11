"""Export news stories in JSON-LD, CSV, and LLM-friendly text formats."""

from open_news import fetch, to_csv, to_jsonld, to_text


def main() -> None:
    stories = fetch(category="tech", max_results=5)

    to_jsonld(stories, path="out/news.jsonld")
    to_csv(stories, path="out/news.csv")
    to_text(stories, path="out/news.txt", max_text_chars=4000)

    print(f"Exported {len(stories)} stories to out/news.jsonld, .csv, and .txt")


if __name__ == "__main__":
    main()
