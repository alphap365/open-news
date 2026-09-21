# 🏗️ Open News Architecture

> **v1.0.4 architecture baseline**
>
> This document describes the stabilized architecture produced by the Issue #1 development cycle (v1.0.3) plus the processing/output additions in v1.0.4. The `1.0.3a1`–`1.0.3b2` releases were pre-release validation stages; the design described here is the stable v1.0.4 model.

---

## 🧭 Architectural idea

Open News separates **acquisition**, **processing**, and **extraction**.

```text
                    ┌─────────────────────────┐
                    │       Public API        │
                    │ fetch / search / ...    │
                    └────────────┬────────────┘
                                 │
             ┌───────────────────┼───────────────────┬──────────────┐
             │                   │                   │              │
             ▼                   ▼                   ▼              ▼
        Acquisition           Processing          Extraction      Output
             │                   │                   │              │
             ▼                   ▼                   ▼              ▼
       feeds / crawler      filter / dedupe     HTML / JSON-LD   markdown
       search / RSS        rank / cluster        Open Graph       json
             │                   │                   │              │
             └───────────────────┴───────────────────┴──────────────┘
                                 │
                                 ▼
                         normalized articles
```

The public API is deliberately small. Internals can evolve behind it as long as the documented contracts remain stable.

---

## 📁 Package layout

```text
open_news/
├── __init__.py
├── api.py
├── cli.py
├── config.py
├── tui.py
│
├── core/
│   ├── extractor.py
│   ├── renderer.py
│   ├── source_resolver.py
│   └── strategies.py
│
├── feeds/
│   ├── bingnews_engine.py
│   ├── duckduckgo_engine.py
│   ├── googlenews_engine.py
│   ├── registry.py
│   ├── rss_discovery.py
│   ├── sources.py
│   └── yahoonews_engine.py
│
├── fetch/
│   ├── article.py
│   ├── crawler.py
│   └── url_resolver.py
│
├── processing/
│   ├── batch.py
│   ├── cluster.py          ← v1.0.4
│   ├── dedupe.py
│   ├── domain_filter.py
│   ├── language_guard.py
│   ├── pipeline.py
│   ├── rank.py             ← v1.0.4
│   ├── ranker.py
│   ├── summarizer.py
│   └── token_filter.py
│
├── export/                 ← v1.0.4
│   ├── __init__.py
│   ├── _shape.py
│   ├── markdown.py
│   └── json_export.py
│
└── utils/
    ├── httpx_compat.py
    ├── textutil.py
    └── user_agents.py
```

### Layer responsibilities

| Layer | Responsibility |
|---|---|
| `api.py` | Stable public entrypoints and orchestration |
| `feeds/` | Live news/search acquisition and RSS sources |
| `fetch/` | Single-URL retrieval, crawling, URL classification |
| `core/` | Turn HTML into article metadata/content |
| `cli.py` | Shell interface over the public API |
| `tui.py` | Interactive terminal interface |
| `config.py` | Validation and configuration contracts |
| `processing/` | Normalize, filter, deduplicate, rank, cluster, enrich |
| `export/` | Structured Markdown / JSON output for article or cluster lists |
| `tui.py` | Interactive terminal interface |

---

# 📰 `fetch()` acquisition architecture

This is the most important architectural change in v1.0.3.

`fetch()` enters through `open_news.feeds.duckduckgo_engine.fetch_raw()`, which acts as a **five-tier acquisition orchestrator**.

```text
                     fetch(category/location)
                              │
                              ▼
                    ┌───────────────────┐
                    │  Tier 1: DDGS    │
                    └─────────┬─────────┘
                              │
                    results? ─┴─ yes ──► return
                              │ no
                              ▼
                    ┌───────────────────┐
                    │ Tier 2: Google    │
                    │       News RSS    │
                    └─────────┬─────────┘
                              │
                    results? ─┴─ yes ──► return
                              │ no/fail
                              ▼
                    ┌───────────────────┐
                    │ Tier 3: Bing News │
                    └─────────┬─────────┘
                              │
                    results? ─┴─ yes ──► return
                              │ no/fail
                              ▼
                    ┌───────────────────┐
                    │ Tier 4: Yahoo     │
                    │       News        │
                    └─────────┬─────────┘
                              │
                    results? ─┴─ yes ──► return
                              │ no/fail
                              ▼
                    ┌───────────────────┐
                    │ Tier 5: DDG HTML  │
                    └─────────┬─────────┘
                              │
                              ▼
                           results
```

### Tier behavior

| Tier | Engine | Purpose |
|---:|---|---|
| 1 | **DDGS** | Fast native news acquisition with dates |
| 2 | **Google News** | Pure-Python RSS fallback with strong date data |
| 3 | **Bing News** | Additional independent fallback; HTML/RSS parsing |
| 4 | **Yahoo News** | Additional pure-Python fallback |
| 5 | **DuckDuckGo HTML** | Final general-search fallback |

The orchestrator returns when a tier produces results. It does not combine all five tiers into one result set.

### Termux behavior

On Termux, tier 1 is skipped by default because the native DDGS path may not be appropriate for that environment. The portable fallback chain remains available.

The following environment variable can explicitly opt into DDGS on Termux:

```bash
OPEN_NEWS_TRY_DDGS_ON_TERMUX=1
```

Individual tiers also have environment-variable escape hatches. See the implementation module and release documentation before changing them in production deployments.

---

# 🔎 `search()` architecture

Keyword search remains based on Google News RSS.

```text
search(query, options)
       │
       ▼
Google News RSS engine
       │
       ├── query mode
       ├── date range
       ├── country / language
       └── raw article records
       │
       ▼
shared processing pipeline
```

Unlike `fetch()`, `search()` does **not** use the five-tier `fetch()` fallback chain. This distinction is intentional: category/location acquisition and keyword search have different source contracts.

---

# 🔄 Shared processing pipeline

Both `fetch()` and `search()` send raw results through `run_pipeline()`.

```text
raw engine results
       │
       ▼
┌──────────────────────┐
│ 1. Language guard    │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 2. Token/query filter│
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 3. Domain filter     │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 4. URL/title dedupe  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 5. Ranking           │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 6. max_results slice │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ 7. optional enrich   │
└──────────┬───────────┘
           ▼
      final articles
```

Full-content enrichment happens **after** slicing. This avoids crawling articles that would already be discarded by the result limit.

### v1.0.4: post-pipeline composition

`run_pipeline()` itself is unchanged. The v1.0.4 additions (`topic`, `rank_query`, `cluster`, `export`) are **post-pipeline** and can be layered by callers:

```text
search() / fetch()          ← run_pipeline() inside
       │
       ▼
filter_articles(topic=...)  ← topic narrowing  (v1.0.4)
       │
       ▼
rank_articles(query=...)    ← BM25 / TF-IDF     (v1.0.4)
       │
       ▼
cluster_articles()          ← story grouping    (v1.0.4)
       │
       ▼
export.to_markdown()/to_json()  ← serialization (v1.0.4)
```
---

# 🧩 Story clustering

processing/cluster.py groups articles into story clusters by title similarity.

```text
articles
    │
    ▼
dedupe_articles()           ← exact URL dedupe (existing)
    │
    ▼
filter_articles(topic=)     ← optional topic narrowing
    │
    ▼
rank_articles(rank_query=)  ← optional relevance scores
    │
    ▼
normalize_title() per article
    │
    ▼
union-find over SequenceMatcher(title_i, title_j) ≥ threshold
    │
    ▼
cluster dicts:
    { id, label, size, score, sources,
      first_seen, last_seen, representative, articles }
    │
    ▼
sort by score | size | date
```

Clustering preserves every article — unlike dedupe, which drops. size is therefore meaningful as "how many outlets reported this story."

The default threshold is 0.75. Similarity uses the same normalize_title helper as dedupe and ranker.

Cluster score combines log1p(size), a recency factor derived from the newest member's date, and the mean of any _rank_score values already present.

---

# 📊 Relevance ranking

processing/rank.py scores articles against a query and re-sorts.

```text
articles + query
        │
        ▼
tokenize (title/description/text depending on search_in)
        │
        ▼
score = bm25 | tfidf | basic
        │
        ▼
write _rank_score, sort descending
        │
        ▼
return
```

`method`|Backend|Notes
`auto`|BM25 → TF-IDF|Default. Silent fallback when `bm25s` isn't installed.
`bm25`|`bm25s`|Explicit; falls back with a warning if unavailable.
`tfidf`|Pure-Pytho|No optional deps.
`basic`|Term frequency|No IDF weighting.

`rank_articles()` mutates in place and adds `_rank_score: float`, mirroring `ranker.sort_articles()`.

# 📤 Export architecture

```text
items (articles or clusters)
    │
    ▼
_shape.normalize_input()
    │
    ├── detects cluster shape via {articles: list, size: int}
    │
    ▼
to_markdown(...)  |  to_json(...)
    │
    ▼
string  ──► written to path when given
```
Both functions accept a path (parent dirs auto-created) and always return the string.

JSON output uses a schema-versioned envelope:

```text
{
  "schema_version": "1.0",
  "generated_at": "2026-09-21T12:00:00+00:00",
  "count": 12,
  "kind": "articles",
  "articles": [ ... ]
}
```
nternal keys (`_tier`, `_aggregator_source`, `_field_sources`, `_full_content`, `_full_content_reason`, `_cluster_size`) are stripped by default; `include_internal=True` preserves them.


# 🧭 URL resolution & classification

`fetch/url_resolver.py` now has three related responsibilities:

1. resolve Google News redirects;
2. recognize known aggregator sources;
3. identify hub/listing URLs that should not be treated as individual articles.

### Google News redirects

```text
Google News redirect
        │
        ▼
  resolve_url()
        │
        ▼
real destination URL
```

If decoding is unavailable or fails, the original URL is preserved rather than causing a hard failure.

### Hub detection

A URL such as a homepage, topic hub, section page, or RSS endpoint is not necessarily an article.

```text
candidate URL
     │
     ▼
 is_hub_url()?
   /       \
 yes        no
  │          │
 skip       continue
```

This prevents crawler/feed noise from entering the article-processing path.

---

# 🧭 Aggregator-aware source resolution

Aggregator-hosted stories require special treatment because the hostname may belong to a distributor rather than the original publisher.

The source resolver uses a best-effort signal hierarchy:

```text
1. canonical / AMP URL pointing off-domain
                 ↓
2. og:url pointing off-domain
                 ↓
3. JSON-LD provider/sourceOrganization/copyrightHolder
                 ↓
4. publisher-related meta tags
                 ↓
5. in-body attribution text
                 ↓
6. aggregator name + unresolved flag
```

The result carries source-resolution metadata so consumers can distinguish:

- a normal publisher source;
- an aggregator that was successfully resolved;
- an aggregator that remains unresolved.

> ⚠️ **Important:** source resolution is explicitly best effort. It should not be treated as authoritative publisher verification.

---

# 📄 Article extraction

`core/extractor.py` uses layered extraction strategies.

```text
HTML document
     │
     ▼
JSON-LD strategy
     │ missing fields?
     ▼
Open Graph / meta strategy
     │ missing fields?
     ▼
HTML heuristic strategy
     │
     ▼
normalized article
```

The strategies fill missing fields rather than treating each strategy as an all-or-nothing replacement.

### JavaScript rendering

When `js=True`, Playwright-backed rendering can supply HTML that is only available after client-side execution.

The JS path is optional and is not required for ordinary HTTP/RSS workflows.

---

# 🌐 Website discovery

`discover_and_get()` uses a two-path discovery model:

```text
website URL
    │
    ▼
RSS discovery?
  /       \
 yes       no
  │         │
  ▼         ▼
RSS       crawler
  │         │
  └────┬────┘
       ▼
 article URLs
       │
       ▼
 extraction / optional enrichment
```

The non-RSS path can use:

- `AsyncCrawler` for ordinary concurrent HTTP crawling;
- `JSCrawler` for JavaScript-heavy sites.

The crawler is constrained by same-domain rules, page/depth budgets, URL classification, concurrency controls, and `robots.txt` handling.

---

# 🔴 Streaming model

`fetch(refresh_interval=...)` and `search(refresh_interval=...)` return generators.

```text
poll
 │
 ▼
process
 │
 ▼
normalize URL/title
 │
 ▼
seen before?
 ├── yes → suppress
 └── no  → yield
 │
 ▼
sleep(interval)
 │
 └──────────────► poll again
```

`stream_search()` is a convenience wrapper that always returns a generator.

---

# 🧩 Public API boundary

The stable package surface is exposed from `open_news`:

```python
from open_news import (
    # v1.0 baseline
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
    # v1.0.4 additions
    cluster_articles,
    rank_articles,
    filter_articles,
    export,
)
```

The CLI and TUI are consumers of this public layer rather than independent business-logic implementations.

---

# 🧪 Testing architecture

The v1.0.3 cycle strengthened tests around the parts most vulnerable to environmental drift.

```text
                 pytest
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   deterministic  network     native/OS
      local       marked       marked
      tests       tests        tests
        │           │           │
        └───────────┼───────────┘
                    ▼
             contract coverage
```

The test suite includes local HTTP fixtures for deterministic article pages, Termux emulation, acquisition-engine tests, processing contracts, and CLI coverage.

---

# 🧠 Stability boundary for v1.0.4

The goal of the stable release is not to freeze every private implementation detail. The intended boundary is:

### Stable

- public Python entrypoints;
- documented parameter semantics;
- article/result contracts;
- CLI commands and documented options;
- documented fallback behavior;
- core processing order.

### Internal / replaceable

- individual feed parser implementation details;
- HTML selectors and heuristics;
- crawler internals;
- source-resolution heuristics;
- retry timing;
- internal helper names.
- ranking backend selection beyond `auto` / `bm25` / `tfidf` / `basic`;
- cluster scoring formula;

This separation allows future releases to improve individual engines without unnecessarily redesigning the public API.
