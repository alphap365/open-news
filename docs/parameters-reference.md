# Parameters reference

This page summarizes common parameter conventions. For the definitive signature of a particular installed release, inspect `help()` or the function docstring.

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

## Language

Language values use common ISO 639-1 two-letter codes, such as `en`, `hi`, `fr`, or `de`. Language handling can involve both provider hints and post-download checks. Very short records may not be reliably classifiable.

## Date ranges

Search supports date bounds in common string/date/datetime forms. Examples:

```python
search("elections", start_date="2026-01-01")
search("elections", start_date="2026-01-01", end_date="2026-01-31")
```

When custom date bounds are provided, they take precedence over the relative time window where the API supports both.

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

## Domain filters

Use a whitelist to keep only matching domains and a blacklist to remove domains.

```python
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

## Topic filtering

Topic matching is distinct from the primary search query. Supported topic modes in the processing/CLI surface are:

- `any`
- `all`
- `exact_phrase`

Example:

```python
filter_articles(articles, topic=["AI", "machine learning"], topic_mode="any")
```

When both query and topic filters are supplied in a pipeline, they narrow the results together.

## Ranking

Ranking methods exposed by the API/CLI include:

| Method | Description |
|---|---|
| `auto` | Prefer BM25 when available; otherwise use TF-IDF fallback |
| `bm25` | Optional `bm25s` backend |
| `tfidf` | TF-IDF ranking |
| `basic` | Basic term-frequency ranking |

The `nlp` optional extra installs BM25 support.

## Streaming

Streaming helpers poll repeatedly and yield batches containing newly seen articles. Intervals are measured in seconds. Choose an interval that is respectful of upstream providers and appropriate for your application.

```python
for batch in stream_search("AI", refresh_interval=30):
    ...
```

The CLI equivalent is:

```bash
open-news search "AI" --stream 30
```

## Full-content extraction

Full-content extraction is optional because it costs additional network and parsing work. JavaScript rendering is separately optional and requires the `js` extra and a Playwright browser installation.

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
```

Fields depend on the publisher and extraction signals; consumers should use `.get()` or validate required keys rather than assume every publisher provides every field.
