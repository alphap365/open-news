# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- *(Nothing yet – this section tracks upcoming features for the next release)*

---

## [0.2.0] - 2026-06-29

### Added
- **Complete package restructure**: code reorganized into `core/` (extractor, JS renderer — untouched logic), `fetch/` (article fetching, URL resolution), `feeds/` (RSS sources, feed registry), `processing/` (summarizer, batch, dedupe), and `utils/`. Public API (`__init__.py` exports) is unchanged — this is an internal-only reorg.
- **Auto-discovering feed registry**: `live_news()` now resolves categories/countries through a remote `index.json` manifest in [open-feeds](https://github.com/alphap365/open-feeds) instead of hardcoded filenames. New countries/categories can be added to open-feeds without a package release.
- **Google News merged into curated feeds**: every open-feeds category and country file now includes a locale-targeted Google News RSS entry alongside direct outlet feeds, so `live_news()` gets aggregator coverage without a separate call.
- **Smart Google News URL resolution**: new `fetch/url_resolver.py` detects and decodes Google News redirect URLs anywhere they appear — RSS feed entries, search results — not just in `search()`.
- **Article deduplication**: new `dedupe_articles()` (exported at package level), with exact normalized-URL matching (always) and opt-in fuzzy title matching for same-story-different-outlet cases. Enabled by default (`dedupe=True`) on `live_news()`, `discover_and_get()`, `batch_summarize()`, and `search_and_summarize()`.
- **`category` field** added to article extraction output (`get_article()`, batch results) — derived from `article:section`/`og:section` meta tags, falling back to URL path heuristics.
- **`search_site(keyword, domain, limit)`**: search a single news domain for a keyword, scoped via Google News RSS + a `site:` filter and a domain-match safety filter. New public function and alias-free (no legacy name).
- **Force-refresh & cache control**: `live_news(force_refresh=True)` bypasses and refreshes the 24h feed-list cache; new `clear_feed_cache()` clears one feed's cache or the entire cache directory.
- **`list_categories()` / `list_countries()`**: introspect what's available in the feed registry without hardcoding strings.

### Changed
- `live_news()`, `discover_and_get()`, `batch_summarize()`, `search_and_summarize()` now dedupe results by default — this changes article counts/output for existing callers relying on raw, undeduplicated results. Pass `dedupe=False` to restore the old behavior.
- Internal module paths changed (e.g. `get_article.py` → `fetch/article.py`); this only matters if you were importing internal modules directly rather than the public `open_news` package API, which is unaffected.

### Notes
- No crawler / quality-score features in this release — out of scope by design (see project discussion).

## [0.1.2] - 2026-06-21

### Added
- Optional `js=True` parameter on `fetch_article`, `fetch_and_summarize_batch`, `fetch_and_summarize_search_results` for rendering JS-heavy pages via headless Chromium (`pip install open-news-api[js]`)
- Rotating User-Agent pool for outgoing requests
- Documented `include_images_videos`, corrected inaccurate `**kwargs` description on `fetch_and_summarize_search_results`
- Removed duplicate `python-dateutil` line in requirements.txt

### Fixed
- **Critical:** `get_article.py` defined the `fetch_article` legacy alias *before* `get_article` was defined, causing `NameError` on `import open_news` — the entire package was unimportable. Alias moved to the end of the module.
- `publish_date` extraction was silently broken in two of three code paths (JSON-LD and `<time>` tag) — `dateutil.parser` module was being called instead of `.parse()`. All three paths (meta tags, JSON-LD, `<time>`) now parse correctly.

---

## [0.1.1] - 2026-06-18

### Fixed
- Packaging metadata for PyPI release (no functional changes).

*The package name may vary due to some PyPI issue, so it is recomended to use correct package name provided in README*

---

## [0.1.0] - 2026-06-17

### Added
- **Core Article Extraction**: Fetch and parse full-text articles from any news URL using a custom built pipeline.
- **Live News Feeds**: Access real-time headlines from 10+ countries and multiple categories (business, tech, sports, etc.).
- **Google News Search**: Search for specific topics and automatically decode obfuscated Google News URLs to get clean article links.
- **RSS Discovery & Fetching**: Automatically discover RSS/Atom feeds from a website URL and fetch full feed entries.
- **Batch Processing**: Process multiple URLs or feeds in bulk with efficient concurrency.
- **Simple Summarization**: Generate concise summaries of articles (supports multiple backends).
- **Smart Caching**: Built-in caching mechanism to reduce API calls and speed up repeated requests.
- **Python 3.8+ Support**: Compatible with Python 3.8, 3.9, 3.10, 3.11, and 3.12.

---

## [Unreleased] - Future Plans

- **No Plans Yet**: Please help / suggest features that could be plugged here.

---

[0.2.0]: https://github.com/alphap365/open-news/releases/tag/v0.2.0
[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1
[0.1.0]: https://github.com/alphap365/open-news/releases/tag/v0.1.0