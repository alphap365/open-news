# 📝 Changelog

All notable Open News changes are documented here.

The release history follows the spirit of [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## 🧭 How to read the v1.0.3 history

The **1.0.3 pre-release sequence was one architectural development cycle**, not a set of unrelated stable releases.

```text
Issue #1
   │
   ▼
Large system-change attempt
   │
   ├── v1.0.3a1
   ├── v1.0.3a2
   ├── v1.0.3a3
   ├── v1.0.3a4
   ├── v1.0.3a5
   ├── v1.0.3a6
   │
   ├── v1.0.3b1
   └── v1.0.3b2
            │
            ▼
       stabilization
            │
            ▼
       v1.0.3 stable
```

The pre-release versions were used to explore, implement, test, and harden the Issue #1 changes. **The actual release-to-release changelog is therefore v1.0.2 → v1.0.3.**

---

# [1.0.3] — Stable

> **Status: Stable**
>
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
[1.0.3]: https://github.com/alphap365/open-news/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/alphap365/open-news/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/alphap365/open-news/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/alphap365/open-news/releases/tag/v1.0.0
[0.2.0]: https://github.com/alphap365/open-news/releases/tag/v0.2.0
[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1
[0.1.0]: https://github.com/alphap365/open-news/releases/tag/v0.1.0
