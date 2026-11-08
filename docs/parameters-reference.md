# Parameters reference

This page summarizes common parameter conventions. For the definitive signature of a particular installed release, inspect the function docstring or run `open-news <command> --help`.

With `uv`, prefix CLI examples with `uv run` inside a project environment, or use `uvx --from open-news-api open-news ...` to run the installed package without adding it to a project.

## Story grouping and exact URL merging

`fetch()`, `search()`, `search_site()`, and `discover_and_get()` group similar
articles by default. Each result is a representative article with `sources`,
`similar_articles`, and cluster-size/score metadata. Similar headlines from
different URLs remain available as related articles; they are not discarded.

Exact normalized URL copies are merged. This URL-level merging is separate
from story grouping: it removes duplicate copies of the same article, while
clustering groups distinct articles that report on the same story.

Use `cluster_articles()` when you need explicit cluster records with a
representative, member `articles`, `size`, `score`, source names, and date
range. Use the `cluster` CLI command to acquire and group stories directly.

## Categories

`fetch()` category values in the source include:

```text
general
business
tech
sports
health
science
entertainment
```

Example:

```python
from open_news import fetch

stories = fetch(
    category="science",
    time_limit="w",
    max_results=8,
    language="en",
    sort_by="relevance",
)
for story in stories:
    print(story["title"], story.get("sources", []))
```

## Country and location

- `search(country=...)` supplies a country/edition hint to the news search provider. Use a two-letter country code such as `in`, `us`, or `gb`.
- `fetch(location=...)` steers acquisition toward a region. It is a query hint and a provider hint, not a strict post-acquisition publisher filter.

If publisher geography must be constrained, use a domain whitelist:

```python
articles = fetch(
    category="general",
    location="in",
    whitelist=["thehindu.com", "indianexpress.com", "ndtv.com"],
)
```

A location hint can still surface syndicated or aggregator-hosted stories from outside the requested region.

For a country edition search, set `country` on `search()` instead:

```python
from open_news import search

stories = search(
    "solar power",
    country="in",
    max_results=10,
)
```

## Language

Language values use common ISO 639-1 two-letter codes, such as `en`, `hi`, `fr`, or `de`. Language handling can involve both provider hints and post-download checks. Very short records may not be reliably classifiable.

```python
from open_news import search

stories = search("election results", country="gb", language="en")
```

## Date ranges

Search supports date bounds in common string/date/datetime forms. Examples:

```python
from open_news import search

search("elections", start_date="2026-01-01")
search("elections", start_date="2026-01-01", end_date="2026-01-31")
```

When custom date bounds are provided, they take precedence over the relative
time window for search. The bounds are inclusive.

Combine dates and query matching to narrow a search:

```python
from open_news import search

stories = search(
    "climate policy",
    query_mode="all",
    start_date="2026-10-01",
    end_date="2026-10-31",
    max_results=20,
)
```

## Relative time windows

| Value | Meaning |
|---|---|
| `d` | Day |
| `w` | Week |
| `m` | Month |

## Search matching modes

| Mode | Meaning |
|---|---|
| `any` | Any query term may match |
| `all` | All query terms should match |
| `exact_phrase` | Treat the input as a phrase |

CLI spelling is `--mode`; Python search uses `query_mode`.

```python
from open_news import search

# Either "battery" or "storage" can match.
any_match = search("battery storage", query_mode="any")

# Both terms must be present in the searchable article fields.
all_match = search("battery storage", query_mode="all")

# Treat the words as a phrase.
phrase_match = search("battery storage", query_mode="exact_phrase")
```

Exclude terms independently of the query mode:

```python
from open_news import search

stories = search(
    "electric vehicles",
    query_mode="all",
    exclude_terms=["toy review", "giveaway"],
    search_in=["title", "description"],
)
```

## Domain filters

Use a whitelist to keep only matching domains and a blacklist to remove domains.

```python
from open_news import fetch

fetch(
    whitelist=["reuters.com", "bbc.com"],
    blacklist=["example.com"],
)
```

CLI values are comma-separated:

```bash
--whitelist reuters.com,bbc.com
--blacklist example.com
```

Python APIs accept domain names as lists. These filters constrain publisher
domains; a country or location hint alone does not guarantee publisher
geography.

To search one publisher domain, use `search_site()`:

```python
from open_news import search_site

stories = search_site(
    "central bank rates",
    domain="reuters.com",
    limit=5,
    query_mode="all",
)
```

## Topic filtering

Topic matching is distinct from the primary search query. Supported topic modes in the processing/CLI surface are:

- `any`
- `all`
- `exact_phrase`

When both query and topic filters are supplied in a pipeline, they narrow the results together.

Python functions use `topic` and `topic_mode`; the CLI options are `--topic`
and `--topic-mode`. CLI topic terms are comma-separated.

`search()` accepts query matching parameters, but not `topic` directly. Apply
topic filtering to fetched or searched results with `filter_articles()`:

```python
from open_news import fetch, filter_articles

stories = fetch(category="business", max_results=30)
filtered = filter_articles(
    stories,
    topic=["markets", "interest rates"],
    topic_mode="any",
)
```

## Ranking

Ranking methods exposed by the API/CLI include:

| Method | Description |
|---|---|
| `auto` | Prefer BM25 when available; otherwise use TF-IDF fallback |
| `bm25` | Optional `bm25s` backend |
| `tfidf` | TF-IDF ranking |
| `basic` | Basic term-frequency ranking |

The `nlp` optional extra installs the optional `bm25s` ranking backend and
summarization helpers. Without BM25, `auto` falls back to TF-IDF.

Rank already-grouped stories by query relevance:

```python
from open_news import fetch, rank_articles

stories = fetch(category="tech", max_results=30)
ranked = rank_articles(
    stories,
    query="open source language models",
    method="auto",
    top_k=10,
)
for story in ranked:
    print(story.get("_rank_score", 0), story["title"])
```

To generate explicit cluster records (with `articles`, `size`, and date
metadata), call `cluster_articles()`:

```python
from open_news import cluster_articles, fetch

stories = fetch(category="tech", max_results=30)
clusters = cluster_articles(
    stories,
    threshold=0.72,
    min_cluster_size=2,
    sort_by="size",
)
for cluster in clusters:
    print(cluster["size"], cluster["label"], cluster["sources"])
```

## Streaming

Streaming helpers poll repeatedly and yield batches containing newly seen
stories. Intervals are measured in seconds; the streaming API enforces a
minimum interval of five seconds. Choose a cadence that is respectful of
upstream providers and suitable for your application.

```python
from open_news import stream_search

for batch in stream_search("AI", refresh_interval=30):
    for story in batch:
        print(story["title"])
    break  # Remove this to keep polling until interrupted.
```

The CLI equivalent is:

```bash
uv run open-news search "AI" --stream 30
```

Without a project environment:

```bash
uvx --from open-news-api open-news search "AI" --stream 30
```

## Full-content extraction

Full-content extraction is optional because it adds network requests and
parsing work. JavaScript rendering is separately optional and requires the
`js` extra and a Playwright browser installation:

```bash
uv add "open-news-api[js]"
uv run playwright install chromium
```

Request full text for search results with the synchronous or asynchronous API:

```python
from open_news import search

stories = search(
    "deep sea research",
    max_results=5,
    full_content=True,
)
for story in stories:
    print(story["title"])
    print(story.get("text", "")[:500])
```

Use JavaScript rendering only for sites that need it:

```python
from open_news import search

stories = search("deep sea research", max_results=5, full_content=True, js=True)
```

## CLI demos with `uv`

Run these commands from a project environment with Open News installed, or
replace `uv run` with `uvx --from open-news-api`:

```bash
# Get recent technology stories as JSON.
uv run open-news fetch --category tech --time-limit w --limit 10 --format json

# Search a region and constrain the query terms.
uv run open-news search "solar power" --mode all --country in --limit 10

# Filter/rank and export results.
uv run open-news search "climate policy" --topic "energy,environment" --rank-query "renewable energy" --export-md climate.md --format json

# Discover and group stories from a publisher site.
uv run open-news discover https://www.reuters.com --limit 10
```

## Article fields

Article dictionaries may include:

```text
url
title
text
description
authors
publish_date
category
top_image
images
videos
source
meta
sources
similar_articles
cluster_size
cluster_score
```

`sources` lists source names represented in the story; `similar_articles`
contains the distinct related article records. Cluster metadata is available
when the pipeline groups a result. Fields depend on publishers and extraction
signals; use `.get()` or validate required keys rather than assuming every
source provides every field.
