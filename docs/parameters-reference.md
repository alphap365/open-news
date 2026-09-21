# 🌍 Parameters Reference

This page collects parameter formats and validation rules that appear across the Open News API and CLI.

---

## 🌐 Country / region codes

### `search(country=...)`

`country` is an ISO 3166-1 alpha-2 style region code such as:

```text
us · in · gb · ca · au · de · fr · jp · br · za · sg · ae
```

The value controls Google News locale parameters (`gl` / `ceid`) and is case-insensitive.

Example:

```python
search("monsoon", country="in", language="hi")
```

### `fetch(location=...)`

`location` is passed to the live acquisition layer as a region hint. Common examples include:

```text
in · us · gb · au · ca · nz · pk · bd · lk
```

The fetch engine does not enforce a fixed Python enum for location values. Unrecognized values may degrade to broader results rather than producing a validation error.

> `discover_and_get()` does not currently expose a country/region parameter.

---

## 🗣️ Language codes

`language` uses ISO 639-1-style two-letter language codes:

```text
en · hi · es · fr · de · ja · ...
```

Language filtering is performed by the processing layer using `langdetect` when available.

The guard operates on downloaded title/description text rather than acting as a hard upstream query constraint.

Very short text may be kept when language detection cannot reliably identify a language.

---

## 📅 Date formats

### `search(start_date=..., end_date=...)`

Accepted forms:

```python
"2026-08-01"
"2026-08-01T14:30:00"
date(2026, 8, 1)
datetime(2026, 8, 1, 14, 30)
```

Both bounds are optional:

```python
search("elections", start_date="2026-08-01")
search("elections", end_date="2026-08-31")
search("elections", start_date="2026-08-01", end_date="2026-08-31")
```

When either custom bound is supplied, it takes precedence over `time_limit`.

Internally, the search engine maps these bounds to Google News RSS date operators.

### `time_limit`

| Value | Window |
|---|---|
| `d` | Last day |
| `w` | Last week |
| `m` | Last month |

---

## 🕐 Publication dates

Extracted article results use `publish_date` as an ISO-style datetime string when a valid date is available.

Raw search/fetch engine records may instead carry a `published` field containing the source engine's original date representation.

Ranking uses tolerant date parsing for ordering.

---

## 📰 Categories

`fetch(category=...)` accepts exactly:

```text
general
business
tech
sports
health
science
entertainment
```

An unsupported category raises a configuration validation error.

---

## 📊 Sorting

| Function | Values |
|---|---|
| `fetch()` | `date`, `relevance`, `popularity` |
| `search()` | `date`, `relevance` |

`search()` does not support popularity sorting because its processing path does not run the popularity clustering stage.

---

## 🔎 Search modes

`search(query_mode=...)` accepts:

```text
any
all
exact_phrase
```

CLI equivalent:

```bash
--mode any
--mode all
--mode exact_phrase
```

---

## ⏱️ Streaming intervals

`fetch(refresh_interval=...)`, `search(refresh_interval=...)`, and `stream_search(..., refresh_interval=...)` use seconds.

The documented minimum interval is **5 seconds**.

Example:

```python
stream_search("AI", refresh_interval=30)
```

CLI:

```bash
open-news search "AI" --stream 30
```

Streaming yields only articles not previously seen by that generator instance.

---

## 🌐 Domain filters

`whitelist` and `blacklist` accept lists of domain names:

```python
fetch(
    whitelist=["reuters.com", "bbc.com"],
    blacklist=["example.com"],
)
```

At the processing layer, a whitelist restricts the surviving domain set; a blacklist removes matching domains.

CLI form:

```bash
--whitelist reuters.com,bbc.com
--blacklist example.com
```

---

## 📄 Full content

`full_content=True` performs additional article retrieval and extraction after the normal result-processing stages.

This ordering is intentional:

```text
raw results
 → filters
 → dedupe
 → ranking
 → max_results
 → full-content enrichment
```

It avoids expensive crawling of articles that will not be returned.

---

## 🌐 JavaScript rendering

`js=True` enables Playwright-backed rendering where supported.

It is useful for sites whose content is generated client-side.

It is not required for normal RSS/search or static HTML workflows.

---

## 🧹 Deduplication

`dedupe=True` is the default on public fetch/search flows.

The processing system can use exact URL deduplication and, where requested, fuzzy title matching.

The streaming layer additionally tracks normalized URLs and normalized titles so previously yielded articles are not emitted again.

---

## 🏷️ Topic filtering (v1.0.4)

`filter_articles(topic=...)`, `cluster_articles(topic=...)`, and the CLI `--topic` flag all accept the same input forms:

```python
topic=None                                # no filtering
topic="AI"                                # single term
topic="AI, LLM"                           # comma-separated
topic=["AI", "LLM"]                       # list
```

Matching scans a broader field set than `query` does:

```text
title · description · text · category · keywords
```

### `topic_mode`

| Value | Meaning |
|---|---|
| `any` (default) | Match if any term is present |
| `all` | Match only if every term is present |
| `exact_phrase` | Treat the whole topic string as one phrase |

When `query` and `topic` are both supplied to `filter_articles()`, they are ANDed.

---

## 📊 Rank methods (v1.0.4)

`rank_articles(method=...)` and the CLI `--rank-method` accept:

| Value | Backend | Notes |
|---|---|---|
| `auto` (default) | BM25 → TF-IDF | Falls back silently |
| `bm25` | `bm25s` | Requires `open-news-api[nlp]` |
| `tfidf` | Pure-Python TF-IDF | No optional deps |
| `basic` | Term frequency | No IDF weighting |

`--rank-query` is required for ranking to do anything. Without it, articles pass through with `_rank_score = 0.0` and their original order preserved.

---

## 🧩 Cluster parameters (v1.0.4)

`cluster_articles(...)` and the CLI `cluster` subcommand:

| Parameter | Default | Range / values |
|---|---:|---|
| `threshold` | `0.75` | `0 < t ≤ 1`; higher = tighter grouping |
| `min_cluster_size` | `1` | Integer ≥ 1 |
| `drop_singletons` | `False` | Convenience for `min_cluster_size=2` |
| `sort_by` | `"score"` | `score`, `size`, `date` |
| `rank_query` | `None` | Optional; uses the ranking system above |
| `rank_method` | `"auto"` | As above |

At `threshold=0.75`, titles that differ by a suffix (e.g. "Live", "Update", "(video)") tend to group; titles that differ by a proper noun usually don't. Tune between `0.65` and `0.85` in practice.

---

## 📤 Export parameters (v1.0.4)

`export.to_markdown(...)`:

| Parameter | Default | Meaning |
|---|---:|---|
| `path` | `None` | Write target; parent dirs created |
| `title` | `None` | Overrides the auto-generated `# News Export` heading |
| `include_text` | `True` | Include the article body |
| `include_summary` | `True` | Include the description blockquote |
| `include_metadata` | `True` | Source / published / authors line |
| `include_toc` | `True` | Emit a table of contents for multi-item input |
| `max_text_chars` | `4000` | Truncate long bodies |
| `include_all_members` | `False` | For cluster input: list every member, not just the representative |

`export.to_json(...)`:

| Parameter | Default | Meaning |
|---|---:|---|
| `path` | `None` | Write target; parent dirs created |
| `indent` | `2` | JSON indent; `None` for compact |
| `envelope` | `True` | Wrap in `{schema_version, generated_at, count, kind, ...}` |
| `include_internal` | `False` | Keep keys like `_tier`, `_field_sources` |
| `ensure_ascii` | `False` | Preserve non-ASCII characters |
| `extra_meta` | `None` | Extra top-level keys merged into the envelope |

