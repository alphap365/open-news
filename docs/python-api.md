# Python API

Import public functions from `open_news`. This guide describes the current public API exposed by this repository version.

## Public entry points

### Acquisition and search

```python
from open_news import (
    fetch, fetch_async,
    search, search_async,
    stream_fetch, stream_search,
    search_site,
)
```

### Article retrieval and discovery

```python
from open_news import (
    get_article,
    get_article_async,
    discover_and_get,
)
```

### Processing and summarization

```python
from open_news import (
    filter_articles,
    dedupe_articles,
    rank_articles,
    cluster_articles,
    summarize_text,
    summarize_with_keywords,
    batch_summarize,
    batch_summarize_async,
    search_and_summarize,
    search_and_summarize_async,
)
```

### Export

```python
from open_news import export, to_markdown, to_json
```

## `fetch()`

Fetch category/location-oriented news.

```python
from open_news import fetch

articles = fetch(
    category="tech",
    location=None,
    max_results=10,
    time_limit="d",
    language=None,
    sort_by="date",
)
```

Common arguments include category, location, time window, maximum results, language, domain allow/deny lists, sorting, full-content enrichment, JavaScript rendering, and deduplication. Consult `open_news.api.fetch` for the exact signature in the installed release.

### Async equivalent

```python
import asyncio
from open_news import fetch_async

async def main():
    articles = await fetch_async(category="tech", max_results=10)
    print(len(articles))

asyncio.run(main())
```

`fetch_async()` is a coroutine; await it from an async function.

## `search()`

Search news by keyword.

```python
from open_news import search

articles = search(
    "climate policy",
    query_mode="all",
    country="in",
    max_results=10,
)
```

Search supports query matching modes, excluded terms, date bounds, country/language settings, domain filters, sorting, optional full-content extraction, and streaming via the refresh interval where supported.

### Async equivalent

```python
from open_news import search_async

async def main():
    articles = await search_async(
        "climate policy",
        country="in",
        max_results=10,
    )
```

## Streaming

The streaming helpers repeatedly acquire results and yield batches of newly seen articles.

```python
from open_news import stream_search

for batch in stream_search("AI policy", refresh_interval=30):
    for article in batch:
        print(article["title"])
```

Stop the loop with your application's normal cancellation mechanism or `Ctrl+C` in a terminal.

## Article retrieval

```python
from open_news import get_article

article = get_article("https://example.com/story", timeout=15)
print(article.get("title"))
print(article.get("text"))
```

Async version:

```python
from open_news import get_article_async

article = await get_article_async("https://example.com/story")
```

Typical article records may contain `url`, `title`, `text`, `authors`, `publish_date`, `category`, `top_image`, `images`, `videos`, `source`, and `meta`. Availability depends on the source page.

## Website discovery

```python
from open_news import discover_and_get

articles = discover_and_get("https://example.com", limit=10)
```

Discovery prefers RSS when it can identify a feed and can use same-domain crawling as a fallback.

## Filtering, ranking, and clustering

```python
from open_news import filter_articles, rank_articles, cluster_articles

topic_results = filter_articles(
    articles,
    topic="artificial intelligence",
    topic_mode="any",
)

ranked = rank_articles(
    topic_results,
    query="AI regulation",
    method="auto",
)

clusters = cluster_articles(
    ranked,
    threshold=0.75,
    drop_singletons=True,
)
```

Ranking methods include `auto`, `bm25`, `tfidf`, and `basic`. The BM25 backend requires the optional NLP extra; `auto` can fall back to TF-IDF.

Clustering groups similar article titles and returns cluster dictionaries containing cluster metadata and member articles.

## Summarization

```python
from open_news import summarize_text, batch_summarize

summary = summarize_text("A long article body...", sentence_count=3)
results = batch_summarize(
    ["https://example.com/story-a", "https://example.com/story-b"],
    sentence_count=3,
)
```

Async batch summarization:

```python
from open_news import batch_summarize_async

results = await batch_summarize_async(
    ["https://example.com/story-a"],
    sentence_count=3,
)
```

Search and summarize in one workflow:

```python
from open_news import search_and_summarize

results = search_and_summarize(
    "renewable energy",
    limit=5,
    sentence_count=2,
)
```

The async counterpart is `search_and_summarize_async()`.

## Export

```python
from open_news import export

markdown_text = export.to_markdown(
    clusters,
    path="out/clusters.md",
    include_all_members=True,
)

json_text = export.to_json(
    clusters,
    path="out/clusters.json",
)
```

Both functions return serialized text. JSON supports a schema-versioned envelope and a bare-list mode; see the exporter function documentation for its options.

## Compatibility guidance

Prefer public imports from `open_news` over imports from internal modules. Internal implementation paths may change between releases even when public functions remain available.
