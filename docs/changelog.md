# 📝 Changelog

All notable Open News changes are documented here.

The release history follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

# [1.0.4] — 2026-09-21

> v1.0.4 is a feature release on top of the v1.0.3 stable baseline. Acquisition, extraction, and URL handling are unchanged; the new work is concentrated in **processing** (clustering, topic filtering, relevance ranking) and **output** (Markdown/JSON export), plus a keyboard-driven TUI refresh.

## 🎯 Release focus

v1.0.3 froze the acquisition architecture. v1.0.4 makes the *results* of that acquisition more useful out of the box — grouping related stories, filtering by topic rather than just keyword, ranking by relevance with an optional BM25 backend, and exporting clean Markdown/JSON without post-processing in a shell pipeline.

## ✨ Added

### 🧩 Story clustering — `cluster_articles()`

- New `open_news.processing.cluster` module.
- Groups articles by normalized title similarity using a union-find pass with `SequenceMatcher` fuzzy prefiltering.
- Composes the existing pipeline: URL dedupe → topic filter → optional relevance rank → cluster.
- Emits per-cluster metadata: `id`, `label`, `size`, `score`, `sources`, `first_seen`, `last_seen`, `representative`, `articles`.
- Sortable by `score` (default), `size`, or `date`; supports `drop_singletons`.

### 🏷️ Topic filtering — `filter_articles(topic=...)`

- `open_news.processing.token_filter.filter_articles()` now accepts `topic` and `topic_mode`.
- Topic matching scans a broader field set than `query`: title, description, text, category, and `keywords`.
- `topic_mode` accepts `any` (default), `all`, or `exact_phrase`; accepts comma-separated strings or lists.
- Query and topic are ANDed when both are supplied — existing `query=` call sites are unchanged.

### 📊 Relevance ranking — `rank_articles()`

- New `open_news.processing.rank` module.
- Backends: **BM25** (via `bm25s`), **TF-IDF** (pure-Python fallback), **basic** (term-frequency).
- `method="auto"` (default) tries BM25 and transparently falls back to TF-IDF when `bm25s` isn't installed.
- Adds a numeric `_rank_score` to each article and returns the list sorted by it.
- Supports `search_in` field selection and `top_k` truncation.

### 📤 Structured export — `open_news.export`

- New `open_news.export` package with `to_markdown()` and `to_json()`.
- Both accept a `path` (parent dirs created automatically) and **always return the serialized string**.
- Auto-detects cluster-shaped input (dicts containing `articles` + `size`) and renders per-cluster.
- Markdown output: TOC, blockquote summary, source/published/authors line, read-original link, optional full-member listing.
- JSON output: schema-versioned envelope (`schema_version`, `generated_at`, `count`, `kind`) with internal keys (`_tier`, `_field_sources`, `_full_content*`) stripped by default. Set `envelope=False` for a bare list.

### 🖥️ CLI additions

- New `cluster` subcommand: sources articles from `--query` or `--category`, then clusters.
- New `export` subcommand: re-exports a saved JSON file to Markdown and/or clean JSON without re-fetching.
- `fetch`, `search`, and `search-site` gain `--topic`, `--topic-mode`, `--rank-query`, `--rank-method`.
- All article-producing commands gain `--export-md`, `--export-json`, `--export-title`, `--export-all-members`.

### 📺 TUI overhaul

- Keyboard-driven menus: **↑ / ↓** navigate, **Enter / →** confirm, **← / Esc / q** back.
- Every menu item still has a number/letter shortcut you can type directly.
- Two new main-menu items: **11** Cluster loaded articles, **12** Export loaded articles / clusters.
- Settings menu extended with topic filter (9), rank method (10), and cluster threshold (11).
- Line-based fallback when stdin isn't a TTY — every existing TUI test still passes.
- Unicode box drawing with ASCII fallback when the terminal encoding isn't UTF-8.

### 🧪 Test infrastructure

- New test files: `test_cluster.py`, `test_rank.py`, `test_export.py`.
- Extended `test_cli.py`, `test_tui.py`, `test_token_filter.py` for the new surfaces.
- All new tests are offline — `bm25s` absence is simulated via monkeypatch, so the suite runs without the `nlp` extra.

### 📦 Packaging

- New `nlp` optional extra containing `sumy>=0.10.0` and `bm25s>=0.2.0`.
- Removed invalid `"lxml.*"` entry from the top-level `dependencies` list — the pinned `"lxml"` already covers it, and the wildcard string made `uv`/`pip` reject the `pyproject.toml`.
- `[dependency-groups]` and `[project.optional-dependencies]` both carry the updated `nlp` group.
- Overloaded `fetch()` / `search()` signatures in `api.py` so Pylance narrows the return type to `List[Dict]` when `refresh_interval` is omitted.

## 🔄 Changed

- `tui.py` is a full rewrite. The public `OpenNewsTUI` / `run_tui()` API is preserved; internal method names and prompt sequences changed where the corresponding prompt became a menu (see TUI guide).
- `open_news/__init__.py` re-exports `cluster_articles`, `rank_articles`, `filter_articles`, and `export`.
- `open_news/api.py` promotes the three processing helpers to the public surface.
- `pyproject.toml` classifiers and keyword set unchanged; `requires-python` unchanged.

## 🐛 Fixed / hardened

- `pyproject.toml` is now accepted by `uv lock`, `uv sync`, and `uv pip install .` after removing the invalid `"lxml.*"` requirement.
- `fetch()` and `search()` no longer produce Pylance `reportArgumentType` errors at CLI call sites where the return type was a `Union` including `Iterator`.
- TUI `_replace_articles()` clears stale clusters whenever the underlying article set changes, so `[12] Export` never writes a cluster list that doesn't correspond to the currently loaded articles.

## ⚠️ Compatibility notes

The public API introduced in v1.0 and stabilized in v1.0.3 remains the basis for v1.0.4. Existing v1.0.3 call sites continue to work unchanged. The new api's are as follows:

```python
cluster_articles()
rank_articles()
filter_articles()
export.to_markdown()
export.to_json()
```
## ⚠️ Known issues

- **`location=` is a query hint, not a post-acquisition filter.** An
  India query can still return stories syndicated through non-Indian
  domains (e.g. `yahoo.com/entertainment/...`, `msn.com/en-in/...`). Use
  `whitelist=[...]` (optionally with `blacklist=["yahoo.com", "msn.com"]`)
  when region correctness matters. A first-class region filter is
  planned for a future release. See `docs/parameters-reference.md`.
- **Extracted `description` is passed through verbatim.** When a feed
  engine supplies boilerplate ("Read today's breaking news at ...",
  NSE disclaimer text) instead of a real summary, the export renders it
  unchanged. A heuristic cleaner is planned for a future release.
- **Liveblog and stock-quote `publish_date` is unreliable.** Liveblogs
  (Times Now, News9Live) and quote pages (Zeebiz, Moneycontrol) refresh
  their JSON-LD `dateModified` on request or on a CMS schedule, so the
  reported publish date can reflect "now", "a week ago", or the site's
  last content update rather than when the story was written. Treat these
  dates as approximate. A `meta.date_source` / `meta.date_is_modified`
  marker is planned for a future release.

# [1.0.3] — 2026-09-20

> v1.0.3 freezes the architecture developed through the `1.0.3a1`–`1.0.3b2` pre-release cycle.

## 🎯 Release focus

The central goal of v1.0.3 is to make news acquisition more resilient without replacing the public API with a new interface.

The major architectural work is concentrated around the acquisition layer, URL handling, source attribution, portability, installation, and test infrastructure.

## ✨ Added

### 📰 Resilient live-news acquisition

`fetch()` now uses a five-tier fallback chain:

1. **DDGS**
2. **Google News**
3. **Bing News**
4. **Yahoo News**
5. **DuckDuckGo HTML**

The chain returns when a tier produces results. This replaces the previous single-route `fetch()` acquisition model.

### 📱 Termux / Android support

- Added `install-on-android.sh`.
- Added Termux-aware acquisition behavior.
- Added Android/Termux test coverage and environment handling.
- DDGS is skipped on Termux by default unless explicitly enabled.

### 🧭 URL classification and resolution

- Expanded URL resolution and classification.
- Added broader aggregator recognition.
- Added hub/listing URL detection.
- Improved Google News redirect handling.
- Prevented known listing/home/topic URLs from being treated as individual articles.

### 🏷️ Aggregator-aware publisher resolution

The source resolver now considers, in order:

1. canonical/AMP URLs;
2. `og:url`;
3. JSON-LD publisher/provider fields;
4. publisher-related metadata;
5. in-body attribution text.

Resolved and unresolved aggregator cases are explicitly distinguishable in article metadata.

### 🧪 Test infrastructure

The release cycle added stronger infrastructure for:

- local deterministic article servers;
- Android/Termux emulation;
- network-dependent tests;
- native-dependency tests;
- feed-engine contracts;
- extraction behavior;
- URL resolution;
- processing contracts;
- CLI behavior.

### 📦 Installation and packaging improvements

- More robust Python interpreter detection.
- Better shell-specific PATH handling.
- Installation-state tracking.
- Version-aware installer behavior.
- Developer-install cleanup support.
- Project dependency metadata centered in `pyproject.toml`.

## 🔄 Changed

- `fetch()` is now an acquisition orchestrator rather than a single-engine call.
- Full-content enrichment remains after filtering, deduplication, ranking, and result slicing.
- Resolved article URLs are preserved downstream after redirect resolution.
- Aggregator source metadata now distinguishes distributor attribution from best-effort original-publisher resolution.
- Article enrichment avoids replacing useful existing values with empty extracted fields.
- The installer has become a more complete environment/bootstrap layer.
- Documentation now describes the v1.0.3 architecture as the stable baseline rather than the experimental pre-release sequence.

## 🐛 Fixed / hardened

- Improved resilience when an individual acquisition source fails or returns no usable results.
- Reduced the chance of hub/listing pages entering article-processing flows.
- Improved publisher attribution for syndicated/aggregated pages.
- Hardened installer uninstall behavior for developer installations.
- Fixed shell-specific PATH setup behavior.
- Improved Python discovery on environments where versioned `python3.x` executables are not named conventionally.

## ⚠️ Compatibility notes

The public API introduced in v1.0 remains the basis for v1.0.3:

```python
fetch()
search()
stream_search()
get_article()
discover_and_get()
search_site()
batch_summarize()
search_and_summarize()
summarize_text()
summarize_with_keywords()
dedupe_articles()
```

The internal feed and extraction engines are implementation details and may continue to evolve.

---

# [1.0.3b2] - 2026-09-20
Testing some Featurees and resolving bugs.

# [1.0.3b1] - 2026-09-19
Testing some Featurees and resolving bugs.

# [1.0.3a6] - 2026-09-19
Testing some Featurees and resolving bugs.

# [1.0.3a5] - 2026-09-19
Testing some Featurees and resolving bugs.

# [1.0.3a4] - 2026-09-19
Testing some Featurees and resolving bugs.

# [1.0.3a3] - 2026-09-19
Testing some Featurees and resolving bugs.

# [1.0.3a2] - 2026-09-18
Testing some Featurees and resolving bugs.

# [1.0.3a1] - 2026-09-18
Testing some Featurees and resolving bugs.

# [1.0.2] — 2026-09-13

## ✨ Added

- Live/streaming keyword search through `search(refresh_interval=...)` and `stream_search()`.
- CLI keyword streaming through `open-news search QUERY --stream SECONDS`.
- Custom `search(start_date=..., end_date=...)` date ranges.
- `country` support for `search()` and the CLI `--country` option.
- Consolidated parameter documentation in `docs/parameters-reference.md`.
- Additional publisher-resolution evaluation tooling.
- Additional source-resolution signals using canonical/AMP links, `og:url`, and last-resort in-body attribution.

## 🐛 Fixed

- Improved developer-install cleanup during `install.sh --uninstall`.
- Corrected installer state-file generation.
- Fixed shell-specific PATH handling for zsh/fish environments.
- Improved Python interpreter discovery across environments including Windows Git Bash.

---

# [1.0.1] — 2026-09-11

## ✨ Added

- `open-news` and `open-news-tui` console entry points.
- Reworked CLI with public-API coverage, JSON output, save support, and additional commands.
- Reworked TUI with persistent settings, richer search, domain search, summarization, browser opening, and saving.
- Public exports for summarization and deduplication helpers.
- Interactive `install.sh` installer.
- Aggregator-aware source resolution for syndication platforms.

## 🐛 Fixed

- Clean handling of unsupported `search --sort popularity`.
- Missing source values for crawler-discovered articles.
- Aggregator hostnames incorrectly being used as article sources when better source information existed.
- Full-content enrichment overwriting useful existing fields with empty values.
- Structural differences between RSS and crawler discovery results.

---

# [1.0.0] — 2026-09-09

v1.0 introduced the modern discovery and processing architecture and retired the old registry-backed public API.

## ✨ Added

- `fetch()` for live category/location news.
- `search()` for Google News queries.
- `get_article()` for article extraction.
- `discover_and_get()` with RSS discovery and crawler fallback.
- `search_site()` for domain-scoped search.
- Language filtering, token filtering, domain filtering, ranking, and deduplication.
- Full-content enrichment and optional JavaScript rendering.
- `fetch(refresh_interval=...)` streaming.
- CLI and TUI interfaces.
- Configuration dataclasses.
- Crawler safety controls and `robots.txt` handling.

## 🔄 Changed

- Public exports were reduced to the new v1 API surface.
- Expensive full-content enrichment was moved after result slicing.
- Package discovery was expanded to include `open_news.*` subpackages.

## 🗑️ Removed

The old registry-backed interfaces were retired:

- `live_news()`
- `get_live_news()`
- `search_news()`
- old feed-cache control workflow

### Migration

| Previous API | v1 API |
|---|---|
| `live_news(category=..., country=...)` | `fetch(category=..., location=...)` |
| `search_news(query, limit=...)` | `search(query, max_results=...)` |
| `fetch_article(url)` | `get_article(url)` |
| `get_articles_from_website_rss(url)` | `discover_and_get(url)` |
| `fetch_and_summarize_batch(urls)` | `batch_summarize(urls)` |

---

# [0.2.0] — 2026-06-29

- Reorganized the package into `core`, `fetch`, `feeds`, `processing`, and `utils`.
- Added the remote `open-feeds` registry, Google News integration, URL resolution, article deduplication, `search_site()`, feed-cache controls, and registry helpers.
- Added article category extraction and optional JavaScript rendering.
- Existing feed and batch workflows deduplicated results by default.

# [0.1.2] — 2026-06-21

- Added optional Playwright rendering.
- Added rotating User-Agent support.
- Corrected article alias import order.
- Improved publication-date parsing.

# [0.1.1] — 2026-06-18

- Corrected packaging metadata for the PyPI release.

# [0.1.0] — 2026-06-17

- Initial article extraction, RSS discovery, live feeds, Google News search, batch processing, summarization, and caching APIs.

---

## 🔗 Release comparison links

[Unreleased]: https://github.com/alphap365/open-news/compare/v1.0.3...HEAD
[1.0.3]: https://github.com/alphap365/open-news/releases/tag/1.0.3
[1.0.3b2]: https://github.com/alphap365/open-news/releases/tag/1.0.3b2
[1.0.3b1]: https://github.com/alphap365/open-news/releases/tag/1.0.3b1
[1.0.3a6]: https://github.com/alphap365/open-news/releases/tag/1.0.3a6
[1.0.3a5]: https://github.com/alphap365/open-news/releases/tag/1.0.3a5
[1.0.3a4]: https://github.com/alphap365/open-news/releases/tag/1.0.3a4
[1.0.3a3]: https://github.com/alphap365/open-news/releases/tag/1.0.3a3
[1.0.3a2]: https://github.com/alphap365/open-news/releases/tag/1.0.3a2
[1.0.3a1]: https://github.com/alphap365/open-news/releases/tag/1.0.3a1
[1.0.2]: https://github.com/alphap365/open-news/releases/tag/v1.0.2
[1.0.1]: https://github.com/alphap365/open-news/releases/tag/v1.0.1
[1.0.0]: https://github.com/alphap365/open-news/releases/tag/v1.0.0
[0.2.0]: https://github.com/alphap365/open-news/releases/tag/v0.2.0
[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1
[0.1.0]: https://github.com/alphap365/open-news/releases/tag/v0.1.0
