# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- *(Nothing yet – this section tracks upcoming features for the next release)*

---

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

[0.1.2]: https://github.com/alphap365/open-news/releases/tag/v0.1.2
[0.1.1]: https://github.com/alphap365/open-news/releases/tag/v0.1.1