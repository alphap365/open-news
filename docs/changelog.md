# Changelog

All notable changes to `open-news` are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned
- Live/streaming keyword search: `search(refresh_interval=...)`, mirroring the existing `fetch()` support, plus TUI live-refresh support for search results (menu 10 currently only covers category/location fetch).

## [1.0.1] - 2026-09-11

### Added
- `open-news` and `open-news-tui` console-script entry points (`[project.scripts]` in `pyproject.toml`). Previously only `python -m open_news.cli` / `python -m open_news.tui` worked — no installed command existed at all.
- CLI (`open_news.cli`) rewritten with full public-API coverage: new `search-site` and `summarize` subcommands, consistent `--whitelist/--blacklist/--dedupe/--save/--format` flags across all subcommands, `--version`, and pretty (human-readable) output by default with `--format json` for scripting.
- TUI (`open_news.tui`) rewritten: persistent Settings panel (language/sort/full-content/js/default-limit/whitelist/blacklist) instead of re-prompting every action; search now supports match mode (`any`/`all`/`exact_phrase`) and exclude terms; new "Search one domain" and "Summarize" menu items; open-in-browser and save-to-file follow-up on any viewed article.
- `__init__.py` now exports `search_and_summarize`, `summarize_with_keywords`, and `dedupe_articles` — previously implemented in `processing/` but not part of the public package surface.
- Interactive `install.sh` installer: OS/Termux/WSL detection, Python version check, isolated-venv setup, optional `[js]` (Playwright) extra, automatic `PATH` fix, first-run preferences written to `~/.config/open-news/config.json` (read by the CLI as argparse defaults), and post-install verification via `open-news --version`.
- `core/source_resolver.py`: aggregator-aware source resolution. Articles served through a known syndication platform (MSN, Yahoo News, Google News, Flipboard, Apple News, SmartNews, Yandex News, NewsBreak) now attempt to resolve the *original* publisher via JSON-LD/meta-tag hints instead of reporting the aggregator's own domain. Every extracted article gains `meta.source_is_aggregator` and `meta.source_resolved` flags so a best-effort guess (aggregator name, unresolved) can be distinguished from a confirmed publisher name.

### Fixed
- `search --sort popularity` raised a `ValueError` from deep inside `SearchConfig.__post_init__` (`config.VALID_SORT_SEARCH` never included `popularity`) — now rejected cleanly at the CLI/TUI layer with the correct, narrower choice set.
- TUI showed `Unknown` as the source for every article discovered via the crawler path (crawler-extracted articles had no top-level `source` field at all) — fixed at the root by giving `core/extractor.py` a `source` field on every result (see below), so this is fixed for every caller, not just the TUI's display fallback.
- `fetch/article.py`'s `get_article()` computed `source` purely from `urlparse(url).netloc`, ignoring any `site_name`/publisher data the extractor had already collected — this was the actual root cause of aggregator domains (`msn.com`, `news.yahoo.com`) appearing as the reported source for *any* article, not just crawler-discovered ones. Now uses the extractor's resolved source.
- `processing/pipeline.py`'s full-content enrichment (`full_content=True`) used `{**art, **full}` to merge extracted content into search results, which let any *empty* field from extraction (e.g. no description found on a paywalled or JS-heavy page) silently overwrite a perfectly good value already present (e.g. the search engine's snippet). Now only non-empty fields from the enrichment step are allowed to overwrite.
- `discover_and_get()`'s crawler path produced a structurally different article shape than its RSS path (no top-level `source` or `description`) despite both being documented as the same return type. Now consistent, since both flow through the same extractor.

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

[Unreleased]: https://github.com/alphap365/open-news/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/alphap365/open-news/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/alphap365/open-news/releases/tag/v1.0.0
[0.2.0]: https://github.com/alphap365/open-news/releases/tag/v0.2.0
[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1
[0.1.0]: https://github.com/alphap365/open-news/releases/tag/v0.1.0