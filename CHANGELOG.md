# Changelog

All notable changes to `open-news` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Documentation and examples will continue to track the v1.0 public API.

## [1.0.0] - 2026-09-09

Version 1.0 introduces a new discovery and processing architecture. This is a breaking release for callers of the retired registry-backed API.

### Added
- `fetch()` for live category and location news through DuckDuckGo News.
- `search()` for Google News queries with `any`, `all`, and `exact_phrase` modes.
- `get_article()` for article extraction with text, metadata, media, source, and category fields.
- `discover_and_get()` with RSS auto-discovery and a same-domain async crawler fallback.
- `search_site()` for domain-scoped news search.
- Configurable language filtering, token matching, domain allow/deny lists, ranking, exact URL deduplication, and optional fuzzy title deduplication.
- Optional full-content enrichment and JavaScript rendering through Playwright.
- `refresh_interval` streaming support on `fetch()` for polling unseen articles.
- JSON command-line interface in `open_news.cli` with `fetch`, `search`, `extract`, and `discover` commands.
- Numbered input-driven terminal interface in `open_news.tui`.
- Live category refresh in the terminal interface, with configurable polling intervals and `Ctrl+C` shutdown.
- Optional country/region selection for normal fetches and live refreshes in the terminal interface.
- Configuration dataclasses for validating fetch and search options.
- Crawler safeguards including same-domain limits, page/depth budgets, URL classification, concurrency control, and `robots.txt` checks.
- `dev` optional dependency group in project metadata.

### Changed
- Public package exports now focus on `fetch`, `search`, `get_article`, `discover_and_get`, `search_site`, `batch_summarize`, and `summarize_text`.
- Processing now limits results before expensive full-content enrichment.
- Package discovery now includes all `open_news.*` subpackages in distributions.
- The TUI selection handler now resolves selected list items to their article index.

### Removed
- Retired the old registry-backed `live_news()`, `get_live_news()`, and `search_news()` interfaces.
- Removed the old feed-cache control workflow from the public API. Registry metadata still uses an internal 24-hour cache with stale-cache fallback.

### Migration

| Previous API | v1.0 replacement |
| --- | --- |
| `live_news(category=..., country=...)` | `fetch(category=..., location=...)` |
| `search_news(query, limit=...)` | `search(query, max_results=...)` |
| `fetch_article(url)` | `get_article(url)` |
| `get_articles_from_website_rss(url)` | `discover_and_get(url)` |
| `fetch_and_summarize_batch(urls)` | `batch_summarize(urls)` |

## [0.2.0] - 2026-06-29

### Added
- Reorganized the package into `core`, `fetch`, `feeds`, `processing`, and `utils` modules.
- Added the remote `open-feeds` registry, Google News feed integration, URL resolution, article deduplication, `search_site()`, feed cache controls, and registry introspection helpers.
- Added article category extraction and optional JavaScript rendering.

### Changed
- Existing feed and batch workflows deduplicated results by default.

## [0.1.2] - 2026-06-21

### Added
- Optional Playwright rendering for JavaScript-heavy pages.
- Rotating User-Agent support.

### Fixed
- Corrected the legacy article alias import order.
- Fixed publication-date parsing through metadata, JSON-LD, and `<time>` elements.

## [0.1.1] - 2026-06-18

### Fixed
- Corrected packaging metadata for the PyPI release.

## [0.1.0] - 2026-06-17

### Added
- Initial article extraction, RSS discovery, live feeds, Google News search, batch processing, summarization, and caching APIs.

[Unreleased]: https://github.com/alphap365/open-news/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/alphap365/open-news/releases/tag/v1.0.0
[0.2.0]: https://github.com/alphap365/open-news/releases/tag/v0.2.0
[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1
[0.1.0]: https://github.com/alphap365/open-news/releases/tag/v0.1.0
