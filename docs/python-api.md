# Python API

Import public functions from `open_news`. This guide describes the current public API exposed by this repository version.

## Public entry points

### Acquisition and search

```python
from open_news import (
    fetch,
    search,
    stream_fetch, stream_search,
    search_site,
)
```

### Article retrieval and discovery

```python
from open_news import (
    get_article,
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
    search_and_summarize,
)
```

`fetch()`, `search()`, `search_site()`, and `discover_and_get()` return one
representative article per story. Each result includes `sources`, a list of
source names, `similar_articles`, a list of other source article records, and
`cluster_size`/`cluster_score` metadata. Exact normalized URL duplicates are
merged into one article; similar headlines at different URLs are preserved
inside the story rather than discarded.

`dedupe_articles()` is limited to merging exact normalized URLs. It does not
remove articles based on title similarity.

The feed engine is also available through the package-level API:

```python
from open_news import FeedEngine

feed = FeedEngine().build(articles)
```

Pass an already configured cache when constructing a personalized feed. The
`FeedCache` protocol defines the minimal `get`/`set` adapter contract for
application-owned persistence backends; `EncryptedCache` implements it.

### Export

```python
from open_news import (
    export,
    to_markdown,
    to_json,
    to_jsonld,
    to_csv,
    to_text,
)
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

Common arguments include category, location, time window, maximum results, language, domain allow/deny lists, sorting, full-content enrichment, and JavaScript rendering. Similar-story grouping is always enabled; exact normalized URL duplicates are merged. Consult `open_news.api.fetch` for the exact signature in the installed release.

### Async call

```python
import asyncio
from open_news import fetch

async def main():
    articles = await fetch(category="tech", max_results=10, async_=True)
    print(len(articles))

asyncio.run(main())
```

With `async_=True`, `fetch()` returns a coroutine that must be awaited. Without
the flag, it preserves the synchronous behavior. The same pattern works with
`search()`, `get_article()`, `batch_summarize()`, and
`search_and_summarize()`. `async` is a Python reserved word, so the supported
parameter spelling is `async_`.

The `*_async()` entry points remain available as deprecated compatibility
wrappers. They emit `DeprecationWarning`; use the corresponding public function
with `async_=True` in new code.

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

### Async call

```python
from open_news import search

async def main():
    articles = await search(
        "climate policy",
        country="in",
        max_results=10,
        async_=True,
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

Async call:

```python
from open_news import get_article

article = await get_article("https://example.com/story", async_=True)
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

Clustering groups similar article titles and returns cluster dictionaries containing cluster metadata and member articles. The discovery APIs use the same grouping by default and return the representative article enriched with related source coverage.

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
from open_news import batch_summarize

results = await batch_summarize(
    ["https://example.com/story-a"],
    sentence_count=3,
    async_=True,
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

Use `await search_and_summarize(..., async_=True)` for the asynchronous
counterpart.

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

jsonld_text = export.to_jsonld(
    clusters,
    path="out/clusters.jsonld",
)

csv_text = export.to_csv(
    clusters,
    path="out/clusters.csv",
)

llm_context = export.to_text(
    clusters,
    path="out/clusters.txt",
    max_text_chars=4000,
)
```

Each exporter returns the serialized content and writes it to `path` when
provided. `to_jsonld()` emits a Schema.org `ItemList` of `NewsArticle` records.
`to_csv()` uses stable columns and JSON-encodes nested values in cells.
`to_text()` creates labeled plain-text context for LLM prompts or retrieval
systems; set `include_text=False` or `max_text_chars` to control article-body
content. Article and cluster records are both supported. `to_json()` supports
a schema-versioned envelope and a bare-list mode.

## Compatibility guidance

Prefer public imports from `open_news` over imports from internal modules. Internal implementation paths may change between releases even when public functions remain available.
