<div align="center">

<img src="https://raw.githubusercontent.com/alphap365/open-news/main/assets/open-news-banner.svg" alt="open-news: fetch, search, understand" width="900">

# open-news

**A focused Python toolkit for discovering, extracting, filtering, and summarizing news.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-173f5f?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-34%20passing-2a9d8f?style=flat-square)](tests/)
[![License](https://img.shields.io/github/license/alphap365/open-news?style=flat-square)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/open-news-api?style=flat-square)](https://pypi.org/project/open-news-api/)

[Install](#installation) · [Python API](#python-api) · [CLI](#command-line) · [TUI](#terminal-interface) · [Contributing](#contributing)

</div>

## What it does

`open-news` turns a source URL, a topic, or a category into structured article dictionaries. It combines live news search, RSS discovery, an async same-domain crawler, HTML extraction, language and domain filters, deduplication, ranking, and optional full-content enrichment.

The default path is deliberately lightweight: plain HTTP and RSS first, with an optional Playwright backend for JavaScript-heavy pages.

## Highlights

- **Live discovery:** fetch category or location news through DuckDuckGo News.
- **Topic search:** search Google News with query modes, exclusions, domain filters, and sorting.
- **Website discovery:** use RSS auto-discovery when available, then crawl pages when needed.
- **Article extraction:** return title, text, authors, dates, images, videos, source, and metadata.
- **Processing pipeline:** language guard, token filtering, domain allow/deny lists, exact and fuzzy deduplication, and ranking.
- **Batch summaries:** extractive summaries over multiple URLs with bounded concurrency.
- **Two interfaces:** a scriptable Python API, a JSON CLI, and a numbered terminal UI.
- **Optional JavaScript rendering:** reuse a persistent Chromium instance while crawling JS-rendered sites.

## Installation

The distribution name is `open-news-api`:

```bash
pip install open-news-api
```

For local development:

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional extras:

```bash
# JavaScript-rendered pages and browser-backed crawling
pip install "open-news-api[js]"
playwright install chromium

# The numbered terminal interface is included in the core package.
```

The core package needs an internet connection for live feeds, search, and remote article pages. The extractor itself can be used with supplied HTML in the lower-level modules.

## Python API

### Fetch live news

```python
from open_news import fetch

articles = fetch(
    category="tech",
    max_results=10,
    language="en",
    sort_by="date",
)

for article in articles:
    print(article["title"], article["url"])
```

Supported categories are `general`, `business`, `tech`, `sports`, `health`, `science`, and `entertainment`. A `location` such as `us` or `in` can be supplied when regional news should take precedence.

### Search by topic

```python
from open_news import search

articles = search(
    "renewable energy",
    query_mode="all",          # any, all, or exact_phrase
    exclude_terms=["sports"],
    max_results=8,
    language="en",
)
```

### Extract one article

```python
from open_news import get_article

article = get_article("https://example.com/article")
print(article["title"])
print(article["text"][:500])
```

The result contains the source URL, title, text, authors, `publish_date`, `top_image`, images, videos, source domain, category, and metadata when available.

### Discover a website

```python
from open_news import discover_and_get

articles = discover_and_get(
    "https://www.bbc.com",
    limit=10,
    prefer_rss=True,
    max_pages=20,
)
```

RSS discovery is attempted first. If it produces no usable entries, the async crawler follows same-domain links while respecting `robots.txt` by default. Use `js=True` for sites whose article links or content require browser rendering.

### Search one domain

```python
from open_news import search_site

articles = search_site("climate policy", domain="reuters.com", limit=5)
```

### Batch summarization

```python
from open_news import batch_summarize

results = batch_summarize(
    ["https://example.com/one", "https://example.com/two"],
    sentence_count=2,
    max_workers=3,
)

for result in results:
    if result["status"] == "success":
        print(result["title"], result["summary"])
    else:
        print(result["url"], result["error"])
```

### Refreshing news

Set `refresh_interval` on `fetch()` to receive a generator that polls periodically and yields only previously unseen articles:

```python
stream = fetch(category="general", refresh_interval=60)
for new_articles in stream:
    for article in new_articles:
        print(article["title"])
```

The minimum refresh interval is five seconds. Normal feed requests are live; the feed registry itself uses a 24-hour cache and falls back to stale data when the remote registry is unavailable.

## Command line

The CLI prints JSON, making it suitable for shell scripts and pipelines:

```bash
python -m open_news.cli fetch --category tech --limit 5
python -m open_news.cli search "artificial intelligence" --mode all --limit 5
python -m open_news.cli extract https://example.com/article
python -m open_news.cli discover https://example.com --limit 10 --max-pages 20
```

Add `--full-content` to `fetch` or `search`, `--js` to `extract`, and `--no-rss` to `discover` when those modes are needed. Run `python -m open_news.cli --help` for the complete option list.

## Terminal interface

Launch the included numbered terminal interface:

```bash
python -m open_news.tui
```

The interface provides numbered actions for fetch, search, RSS/crawler discovery, single-article extraction, loaded-article viewing, clearing, and live refresh. Fetch and live refresh both accept an optional country/region code such as `us` or `in`; leaving it blank uses the selected category. Live refresh prints only new articles and returns to the menu when you press `Ctrl+C`. It uses the same public API as the CLI.

## Processing model

For `fetch()` and `search()`, results pass through this sequence:

1. Language filtering, when `language` is supplied.
2. Query and exclusion-term filtering.
3. Whitelist and blacklist domain filtering.
4. URL deduplication and optional fuzzy title deduplication.
5. Date, relevance, or popularity ranking.
6. Result limiting.
7. Optional full-content extraction.

This ordering avoids downloading full article bodies for results that will later be filtered out.

## Public API

The package-level API in v1.0 is:

| Function | Purpose |
| --- | --- |
| `fetch()` | Fetch live category or location news |
| `search()` | Search Google News with filtering and ranking |
| `get_article()` | Extract one article |
| `discover_and_get()` | Discover articles from a website or feed |
| `search_site()` | Search within one domain |
| `batch_summarize()` | Extract and summarize multiple URLs |
| `summarize_text()` | Summarize supplied text |

The old registry-backed `live_news()` and `search_news()` interfaces are retired in v1.0. See [CHANGELOG.md](CHANGELOG.md) for the migration summary.

## Development

Run the test suite from the repository root:

```bash
python -m pytest -q
python -m compileall -q open_news
```

The tests use mocked network behavior where appropriate. Live provider availability, robots policies, and publisher HTML layouts can change independently of this project.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md), keep changes focused, and add tests for behavior changes. Feed definitions are maintained separately in [open-feeds](https://github.com/alphap365/open-feeds).

## License

MIT. See [LICENSE](LICENSE).

<div align="center">

Made by [Arajit Paul](https://github.com/alphap365)

</div>
