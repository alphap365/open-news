# 🐍 Python API Reference

> **Stable v1.0.3 public API**

Open News keeps its public Python surface intentionally small. Import from `open_news` rather than reaching into internal modules unless you are developing the library itself.

```python
from open_news import (
    fetch,
    search,
    stream_search,
    get_article,
    discover_and_get,
    search_site,
    batch_summarize,
    search_and_summarize,
    summarize_text,
    summarize_with_keywords,
    dedupe_articles,
)
```

---

## 📰 `fetch()`

Fetch live category or location news.

```python
fetch(
    category="general",
    location=None,
    time_limit="d",
    max_results=20,
    language=None,
    whitelist=None,
    blacklist=None,
    sort_by="date",
    full_content=False,
    search_in=None,
    refresh_interval=None,
    js=False,
    dedupe=True,
)
```

### Acquisition model

In v1.0.3, `fetch()` uses a five-tier acquisition orchestrator:

1. DDGS
2. Google News
3. Bing News
4. Yahoo News
5. DuckDuckGo HTML

The chain stops when a tier returns results. It is a fallback chain, **not a merge of all five sources**.

### Parameters

| Parameter | Default | Description |
|---|---:|---|
| `category` | `"general"` | `general`, `business`, `tech`, `sports`, `health`, `science`, or `entertainment` |
| `location` | `None` | Country/region code; takes precedence over `category` |
| `time_limit` | `"d"` | `d`, `w`, or `m` |
| `max_results` | `20` | Maximum returned articles |
| `language` | `None` | ISO 639-1 language filter |
| `whitelist` | `None` | Domains to keep |
| `blacklist` | `None` | Domains to remove |
| `sort_by` | `"date"` | `date`, `relevance`, or `popularity` |
| `full_content` | `False` | Extract full content after processing/slicing |
| `search_in` | `None` | Fields used by token filtering; defaults internally to title/description |
| `refresh_interval` | `None` | Polling interval in seconds; `>=5` returns a generator |
| `js` | `False` | Use browser rendering for full-content work |
| `dedupe` | `True` | Enable deduplication |

> **Note on `location`:** it is a query hint, not a filter. Off-region
> articles can appear. Use `whitelist=[...]` to enforce. See
> `docs/parameters-reference.md` for the rationale.

### Basic usage

```python
articles = fetch(category="tech", max_results=10)

for article in articles:
    print(article["title"])
    print(article["url"])
```

### Live polling

```python
for new_articles in fetch(category="general", refresh_interval=60):
    for article in new_articles:
        print(article["title"])
```

---

## 🔎 `search()`

Search news by keyword through Google News RSS.

```python
search(
    query,
    query_mode="any",
    exclude_terms=None,
    time_limit="d",
    start_date=None,
    end_date=None,
    country=None,
    max_results=20,
    language=None,
    whitelist=None,
    blacklist=None,
    sort_by="date",
    full_content=False,
    search_in=None,
    refresh_interval=None,
    js=False,
    dedupe=True,
)
```

### Query modes

| Mode | Meaning |
|---|---|
| `any` | Match any query term |
| `all` | Match all query terms |
| `exact_phrase` | Treat the query as an exact phrase |

### Date range

```python
search(
    "monsoon forecast",
    start_date="2026-08-01",
    end_date="2026-08-31",
)
```

`start_date` and `end_date` accept:

- `YYYY-MM-DD` strings;
- ISO-8601 datetime strings;
- Python `date` objects;
- Python `datetime` objects.

If either custom bound is supplied, it takes precedence over `time_limit`.

### Country / language

```python
search(
    "monsoon",
    country="in",
    language="hi",
)
```

`country` controls Google News locale parameters. `language` participates in both locale hints and post-download language filtering.

### Streaming

```python
for articles in search("budget 2026", refresh_interval=30):
    for article in articles:
        print(article["title"])
```

---

## 🔴 `stream_search()`

Convenience wrapper for streaming keyword search.

```python
stream_search(
    query,
    refresh_interval=60,
    query_mode="any",
    exclude_terms=None,
    country=None,
    max_results=20,
    language=None,
    whitelist=None,
    blacklist=None,
    sort_by="date",
    full_content=False,
    js=False,
    dedupe=True,
)
```

Unlike `search()`, it always returns a generator.

```python
for articles in stream_search("AI", refresh_interval=30):
    for article in articles:
        print(article["title"])
```

---

## 📄 `get_article()`

Extract one article.

```python
get_article(url, timeout=15, js=False)
```

Typical fields include:

```text
url
 title
text
authors
publish_date
category
top_image
images
videos
source
meta
```

The extraction system uses JSON-LD, Open Graph/meta tags, and HTML heuristics.

When the source is an aggregator, `meta` can contain source-resolution information describing whether the publisher was resolved.

---

## 🌐 `discover_and_get()`

Discover articles from a website and optionally extract them.

```python
discover_and_get(
    website_url,
    limit=10,
    dedupe=True,
    js=False,
    max_pages=None,
    max_depth=None,
    prefer_rss=True,
    full_content=False,
)
```

The discovery order is:

```text
website
  │
  ├── RSS available → use RSS
  │
  └── no RSS → same-domain crawler
```

The crawler supports ordinary HTTP and optional JavaScript rendering.

> `discover_and_get()` currently does not expose the `whitelist`/`blacklist` parameters available to `fetch()` and `search()`.

---

## 🌍 `search_site()`

Search within a single domain.

```python
search_site(
    keyword,
    domain,
    limit=10,
    query_mode="any",
    language=None,
    full_content=False,
    js=False,
)
```

Example:

```python
articles = search_site(
    "climate policy",
    domain="reuters.com",
    limit=5,
)
```

---

## ✂️ `batch_summarize()`

Fetch and summarize multiple URLs concurrently.

```python
batch_summarize(
    urls,
    sentence_count=3,
    max_workers=5,
    js=False,
)
```

Results contain a status and either summary information or an error.

```python
for result in batch_summarize(urls, sentence_count=2):
    if result["status"] == "success":
        print(result["summary"])
    else:
        print(result["error"])
```

---

## 🔎 `search_and_summarize()`

Search a topic and summarize the resulting articles.

```python
search_and_summarize(
    query,
    limit=10,
    sentence_count=3,
    max_workers=5,
    js=False,
)
```

---

## 📝 `summarize_text()`

Standalone extractive summarization.

```python
summarize_text(text, sentence_count=3)
```

No network access is required when the text is already available.

---

## 🧠 `summarize_with_keywords()`

Keyword-aware extractive summarization helper exported from the public package surface.

Its purpose is to bias sentence selection toward supplied terms without introducing a hosted or generative model.

---

## 🧹 `dedupe_articles()`

Deduplicate an existing article list.

```python
dedupe_articles(articles, fuzzy=False)
```

Exact URL deduplication is the baseline. Optional fuzzy title deduplication can collapse similar stories published by different outlets.

---

## 🔁 Legacy aliases

The following aliases remain supported:

```python
fetch_article = get_article
get_articles_from_website_rss = discover_and_get
```

They are retained for compatibility.

The old registry-backed 0.x interfaces are **not** part of the v1 API. See the changelog for migration information.

---

## 📦 Result philosophy

Open News returns ordinary Python dictionaries and lists rather than forcing callers into a large object hierarchy.

That makes results easy to:

- serialize as JSON;
- pipe through the CLI;
- store in databases;
- transform with ordinary Python;
- integrate into other projects.

The exact internal acquisition engine is deliberately hidden behind the public API.
