# 🏗️ Architecture

## Package layout

```
open_news/
├── api.py            # public entrypoints: fetch, search, get_article, discover_and_get, search_site
├── config.py          # FetchConfig / SearchConfig dataclasses + validation
├── cli.py / tui.py     # the two interfaces, both built only on api.py
├── fetch/
│   ├── article.py      # get_article(): HTTP or JS render -> extractor
│   ├── crawler.py       # AsyncCrawler / JSCrawler for discover_and_get()
│   └── url_resolver.py   # Google News redirect decoding
├── feeds/
│   ├── sources.py        # from_rss(), search_site(), from_google_news()
│   ├── rss_discovery.py   # <link rel="alternate"> / heuristic feed discovery
│   ├── googlenews_engine.py  # search() backend
│   └── duckduckgo_engine.py  # fetch() backend
├── processing/
│   ├── pipeline.py        # run_pipeline(): the shared filter/sort/enrich chain
│   ├── token_filter.py, domain_filter.py, language_guard.py, dedupe.py, ranker.py
│   ├── batch.py            # batch_summarize, search_and_summarize
│   └── summarizer.py        # extractive summarization
├── core/
│   ├── extractor.py         # ArticleExtractor: runs strategies in priority order
│   ├── strategies.py         # JsonLdStrategy, OpenGraphStrategy, HeuristicStrategy
│   └── renderer.py            # Playwright wrappers (one-shot + persistent)
└── utils/user_agents.py
```

## The `fetch()`/`search()` pipeline

Both funnel raw engine results through the same `run_pipeline()`, in this fixed order:

1. **Language filter** (`language_guard.py`) — skip if `language=None`
2. **Query/exclusion filter** (`token_filter.py`) — word-boundary re-check + `exclude_terms`
3. **Domain filter** (`domain_filter.py`) — whitelist wins if both given
4. **Dedupe** (`dedupe.py`) — exact URL always; fuzzy title dedupe optional
5. **Sort** (`ranker.py`) — date / relevance / popularity (clustering-based)
6. **Slice to `max_results`**
7. **Optional full-content enrichment** — deliberately *after* slicing, so we never crawl articles that would be discarded anyway

## Article extraction strategy chain

`core/extractor.py`'s `ArticleExtractor` runs strategies in priority order, filling only fields still missing:

1. **JSON-LD** (`schema.org` Article/NewsArticle) — best source when present
2. **Open Graph / meta tags** — near-universal fallback
3. **HTML heuristic** — DOM scoring (stopword density, tag bonus, link-density penalty, sibling merging) as the last resort, and the *only* source for raw `text`

## Two crawl backends, not one slow/fast pair

`fetch/crawler.py` has `AsyncCrawler` (many concurrent `httpx` requests, BFS frontier) and `JSCrawler` (one persistent Playwright browser, sequential). They're genuinely different execution shapes — `JSCrawler` isn't just "AsyncCrawler but slower," it can't fan out the way a browser context can.

## Known structural gaps (as of v1.0.2)

- `discover_and_get()` has no `whitelist`/`blacklist` parameters.
- The TUI's live-refresh menu (10) still only covers `fetch()` (category/location); it hasn't been wired up to `stream_search()` / `search(refresh_interval=...)` yet even though the underlying API gap closed in v1.0.2.
- `feeds/registry.py` (a `requests`-based feed-registry system) exists in the tree but isn't imported anywhere in the current public surface — likely legacy, worth removing or wiring up.