# 🐍 Python API Reference

```python
from open_news import fetch, search, get_article, discover_and_get, search_site, batch_summarize, search_and_summarize, summarize_text, summarize_with_keywords, dedupe_articles
```

## `fetch(...)`
Live category/location news via DuckDuckGo News. Always queries live (no disk cache).

| Param | Default | Notes |
|---|---|---|
| `category` | `"general"` | one of general/business/tech/sports/health/science/entertainment |
| `location` | `None` | country/region code (`"in"`, `"us"`) — takes precedence over category |
| `time_limit` | `"d"` | `d`/`w`/`m` recency window |
| `max_results` | `20` | hard cap |
| `language` | `None` | ISO 639-1, enforced pre-download |
| `whitelist`/`blacklist` | `None` | domain allow/deny lists |
| `sort_by` | `"date"` | `date`/`relevance`/`popularity` |
| `full_content` | `False` | crawl+extract full text per result |
| `refresh_interval` | `None` | if set (≥5s), returns a **generator** yielding only newly-seen articles each poll |
| `js` | `False` | headless-browser backend for `full_content` |
| `dedupe` | `True` | exact + fuzzy dedup |

```python
for a in fetch(category="tech", max_results=10, language="en"):
    print(a["title"], a["url"])

# live polling
for new in fetch(category="general", refresh_interval=60):
    ...
```

## `search(query, ...)`
Direct keyword search via Google News RSS.

| Param | Default | Notes |
|---|---|---|
| `query_mode` | `"any"` | `any`/`all`/`exact_phrase` |
| `exclude_terms` | `None` | word-boundary exclusion list |
| `sort_by` | `"date"` | `date`/`relevance` only (no `popularity`) |
| *(shares `time_limit`, `max_results`, `language`, `whitelist`, `blacklist`, `full_content`, `search_in`, `js`, `dedupe` with `fetch`)* | | |

> ⚠️ No `refresh_interval` — live/streaming search isn't supported yet (planned for v1.0.2).

## `get_article(url, timeout=15, js=False)`
Full extraction for one URL: `title`, `text`, `authors`, `publish_date`, `category`, `top_image`, `images`, `videos`, `source`, `meta`.

## `discover_and_get(website_url, ...)`
Discover + fetch from any provider URL (homepage or section page). Tries RSS auto-discovery first (`prefer_rss=True`); falls back to the async same-domain crawler otherwise.

Key params: `limit`, `dedupe`, `js`, `max_pages`, `max_depth`, `prefer_rss`, `full_content`.

> Note: unlike `fetch`/`search`, this has **no `whitelist`/`blacklist`** parameter yet.

## `search_site(keyword, domain, ...)`
Search one news domain via Google News RSS + `site:` filter.

## `batch_summarize(urls, ...)` / `search_and_summarize(query, ...)`
Concurrently fetch + extractively summarize many URLs (or a topic search's results). Returns per-URL dicts with `status`, `title`, `summary`, and `error` on failure.

## `summarize_text(text, sentence_count=3)` / `summarize_with_keywords(...)`
Standalone extractive summarization, no network — usable on any text you already have.

## `dedupe_articles(articles, fuzzy=False, ...)`
Exact URL dedup (always), optional fuzzy title dedup across outlets (`fuzzy=True`).

---

**Legacy aliases** (fully supported, not deprecated): `fetch_article` = `get_article`, `get_articles_from_website_rss` = `discover_and_get`.
