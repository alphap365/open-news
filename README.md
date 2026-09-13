<div align="center">

```
 ██████╗ ██████╗ ███████╗███╗   ██╗      ███╗   ██╗███████╗██╗    ██╗███████╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║      ████╗  ██║██╔════╝██║    ██║██╔════╝
██║   ██║██████╔╝█████╗  ██╔██╗ ██║█████╗██╔██╗ ██║█████╗  ██║ █╗ ██║███████╗
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║╚════╝██║╚██╗██║██╔══╝  ██║███╗██║╚════██║
╚██████╔╝██║     ███████╗██║ ╚████║      ██║ ╚████║███████╗╚███╔███╔╝███████║
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝      ╚═╝  ╚═══╝╚══════╝ ╚══╝╚══╝ ╚══════╝
```

# 📰 open-news

**A focused Python toolkit for discovering, extracting, filtering, and summarizing news.**

[![License](https://img.shields.io/github/license/alphap365/open-news?style=for-the-badge&color=blue)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)](https://github.com/alphap365/open-news)
[![PyPI version](https://img.shields.io/pypi/v/open-news-api?style=for-the-badge)](https://pypi.org/project/open-news-api/)

*Fetch, search, discover, and understand news — from a script, a shell, or a menu.*

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [CLI & TUI](#️-cli--tui) • [API Reference](#-api-reference) • [Contributing](#-contributing)

</div>

---

## 🔁 Latest updates

> **v1.0.2** — Custom date-range search (`search(start_date=..., end_date=...)`), a `country` parameter on `search()` for locale-correct Google News results, and **live/streaming keyword search** (`stream_search()` / `search(refresh_interval=...)`, plus `open-news search --stream SECONDS` and TUI menu 10) — closing the gap noted in earlier releases. Also fixes an `install.sh --uninstall` bug that left Developer installs' clones behind, and a broken shell-rc detection that silently skipped PATH setup on zsh/fish. See [docs/parameters-reference.md](docs/parameters-reference.md) for country codes, date formats, and other parameter formats in one place.

> **v1.0.1** — `open-news`/`open-news-tui` console commands (previously `python -m` only); CLI rewritten with full API coverage + fixed a `search --sort popularity` crash; TUI rewritten with a settings panel, richer search, save/open-in-browser; **more robust source attribution** — aggregator-hosted articles (MSN, Yahoo News, etc.) now attempt to resolve the *original* publisher instead of reporting the aggregator's domain; fixed full-content enrichment silently overwriting good search snippets with empty extracted fields.

> **v1.0.0** — Public API stabilized around `fetch()`, `search()`, `get_article()`, `discover_and_get()`, `search_site()`, `batch_summarize()`, `summarize_text()`. The old registry-backed `live_news()` / `get_live_news()` / `search_news()` / `clear_feed_cache()` interfaces from the 0.x series are **retired** — see [docs/changelog.md](docs/changelog.md) for the full migration notes.

> View the complete history in [docs/changelog.md](docs/changelog.md).

## 🎯 Features

<table>
<tr>
<td>

### 📄 Article Extraction
Full text + metadata (title, authors, publish date, top image, video) via a layered extractor: JSON-LD → Open Graph → HTML-heuristic fallback. No third-party extraction library required.

</td>
<td>

### 🌐 Live Discovery
Category or location news via DuckDuckGo News, queried live — no disk cache, so freshness is the point.

</td>
</tr>
<tr>
<td>

### 🔍 Google News Search
Query modes (`any`/`all`/`exact_phrase`), exclusion terms, domain allow/deny lists, and Google News redirect decoding to real article URLs.

</td>
<td>

### 🕸️ Website Discovery
RSS auto-discovery first; falls back to an async same-domain crawler (or a persistent-browser JS crawler) when a site has no feed.

</td>
</tr>
<tr>
<td>

### 🧭 Aggregator-aware sourcing
Articles syndicated through MSN, Yahoo News, and similar platforms attempt real-publisher resolution instead of reporting the aggregator's domain as the source — flagged as best-effort, not guaranteed.

</td>
<td>

### ✂️ Batch Summarization
Concurrent fetch + extractive summarization across many URLs, or straight from a topic search, with bounded worker threads.

</td>
</tr>
<tr>
<td>

### 🧹 Processing Pipeline
Language guard, token filtering, domain filters, exact + fuzzy dedupe, and date/relevance/popularity ranking — applied consistently to `fetch()` and `search()`.

</td>
<td>

### 🖥️ Three Interfaces
A scriptable Python API, a `open-news` CLI (JSON or pretty output), and a numbered `open-news-tui` menu for non-scripted use.

</td>
</tr>
</table>

---

## 📦 Installation

*Note: the distribution name is `open-news-api`, not `open-news` — the latter was taken on PyPI.*

### Interactive installer (recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install.sh | bash
```
Detects your OS (Linux/macOS/Termux/WSL), sets up an isolated environment, asks about the optional JS extra, and verifies the install before finishing. Full walkthrough: [docs/installation.md](docs/installation.md).

### With pip
```bash
pip install open-news-api
# a specific version:
pip install open-news-api==1.0.2
```

### With uv
```bash
uv add open-news-api

# or drop it straight into a throwaway environment to try it:
uvx --from open-news-api open-news --help
```

### From source (development)
```bash
git clone https://github.com/alphap365/open-news.git
cd open-news

# with pip
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"

# or with uv (matches this repo's CI)
uv sync
uv run pytest -q
```

### Optional: JavaScript rendering
For sites that render article content client-side:
```bash
pip install "open-news-api[js]"    # or: uv add "open-news-api[js]"
playwright install chromium         # one-time browser download, ~300MB
```
Then pass `js=True` to `get_article()`, `discover_and_get()`, `fetch()`/`search()` (with `full_content=True`), or `batch_summarize()`. If the extra isn't installed, it logs a warning and falls back to plain HTTP rather than raising.

**Dependencies installed automatically:** `lxml` • `python-dateutil` • `httpx` • `beautifulsoup4` • `feedparser` • `googlenewsdecoder` • `requests` • `ddgs` • `langdetect`

---

## 🚀 Quick Start

### 1️⃣ Extract one article
```python
from open_news import get_article

article = get_article("https://www.bbc.com/news/world-us-canada-12345678")
print(article["title"])
print(article["text"][:500])
print(f"Source: {article['source']}")
print(f"Published: {article['publish_date']}")
```

### 2️⃣ Search Google News
```python
from open_news import search

results = search("artificial intelligence", query_mode="all", exclude_terms=["sports"], max_results=5)
for a in results:
    print(f"✓ {a['title']}")
    print(f"  → {a['url']}\n")
```

### 2️⃣.1 Custom date range + country (v1.0.2)
```python
from open_news import search

# everything published in a specific window, India edition
results = search("monsoon forecast", start_date="2026-08-01", end_date="2026-08-31", country="in")
for a in results:
    print(f"✓ {a['title']} — {a.get('published')}")
```
`start_date`/`end_date` accept `'YYYY-MM-DD'`, an ISO datetime string, or a `date`/`datetime` object, and take precedence over `time_limit` when given. `country` is an ISO 3166-1 alpha-2 code (defaults to `"us"`). Full formats: [docs/parameters-reference.md](docs/parameters-reference.md).

### 2️⃣.2 Live keyword search (v1.0.2)
```python
from open_news import stream_search

# yields only newly-seen articles each poll, same shape as fetch(refresh_interval=...)
for new_articles in stream_search("budget 2026", refresh_interval=30):
    for a in new_articles:
        print(a["title"])
```
Or via `search(refresh_interval=...)` directly, or from the shell: `open-news search "budget 2026" --stream 30`.

### 3️⃣ Live category/location news
```python
from open_news import fetch

tech_news = fetch(category="tech", max_results=5)
india_news = fetch(location="in", max_results=5)   # location takes precedence over category

for a in tech_news:
    print(f"[{a['source']}] {a['title']}")
```

### 4️⃣ Discover any website
```python
from open_news import discover_and_get

articles = discover_and_get("https://techcrunch.com", limit=5)
for a in articles:
    print(f"✓ {a['title']}")
```
RSS auto-discovery is tried first; the async crawler follows same-domain links (respecting `robots.txt`) if no feed is found.

### 5️⃣ Batch fetch & summarize
```python
from open_news import batch_summarize

urls = ["https://example.com/article1", "https://example.com/article2"]
results = batch_summarize(urls, sentence_count=2, max_workers=3)

for r in results:
    if r["status"] == "success":
        print(f"📰 {r['title']}\n   {r['summary']}\n")
    else:
        print(f"❌ Failed: {r['error']}")
```

### 6️⃣ Search + summarize in one call
```python
from open_news import search_and_summarize

results = search_and_summarize("climate change", limit=5, sentence_count=2)
for a in results:
    print(f"🔗 {a['url']}\n📰 {a['title']}\n   {a['summary']}\n")
```

### 7️⃣ Search a single domain
```python
from open_news import search_site

results = search_site("budget", domain="reuters.com", limit=5)
for a in results:
    print(f"✓ {a['title']}\n  → {a['url']}\n")
```

### 8️⃣ Live polling
```python
from open_news import fetch

# yields only newly-seen articles each poll; minimum interval is 5s
for new_articles in fetch(category="general", refresh_interval=60):
    for a in new_articles:
        print(a["title"])
```

### 9️⃣ Dedupe articles yourself
```python
from open_news import dedupe_articles

raw = fetch(category="general", dedupe=False)
merged = dedupe_articles(raw, fuzzy=True)   # collapse same-story-different-outlet duplicates
```

---

## 🖥️ CLI & TUI

```bash
open-news fetch --category tech --limit 5
open-news search "AI regulation" --mode all --exclude sports
open-news search "elections" --start-date 2026-08-01 --end-date 2026-08-31 --country in
open-news search "budget 2026" --stream 30
open-news discover https://www.bbc.com --limit 10
open-news summarize --query "climate policy" --sentences 2
open-news --version
```

Or launch the numbered menu — no flags to remember:
```bash
open-news-tui
```

- **[docs/cli-reference.md](docs/cli-reference.md)** — every subcommand and flag
- **[docs/tui-guide.md](docs/tui-guide.md)** — menu walkthrough, settings panel, live-refresh limitations

---

## 🔀 Function names: current vs legacy alias

Two names, same function, both stable — pick whichever reads better:

| Current name | Legacy alias |
|---|---|
| `get_article` | `fetch_article` |
| `discover_and_get` | `get_articles_from_website_rss` |

⚠️ **Retired in v1.0.0, not aliases:** `live_news`, `get_live_news`, `search_news`, `clear_feed_cache`. If you're upgrading from 0.x, see [doc/changelog.md](docs/changelog.md) for the direct replacement of each.

---

## 📚 API Reference

Full parameter tables and return shapes for every function: **[docs/python-api.md](docs/python-api.md)**

| Function | Purpose |
|---|---|
| `fetch()` | Live category/location news, optional streaming via `refresh_interval` |
| `search()` | Google News search with query modes, exclusions, filtering, custom date ranges, country, and optional streaming via `refresh_interval` |
| `stream_search()` | Always-a-generator convenience wrapper for live/streaming keyword search |
| `get_article()` | Extract one article's full content + metadata |
| `discover_and_get()` | RSS-first, crawler-fallback discovery from any site |
| `search_site()` | Search scoped to one domain |
| `batch_summarize()` / `search_and_summarize()` | Concurrent extract + summarize |
| `summarize_text()` / `summarize_with_keywords()` | Standalone extractive summarization |
| `dedupe_articles()` | Exact + fuzzy dedup on any article list |

Parameter formats that span multiple functions (country/region codes, date formats, language codes): **[docs/parameters-reference.md](docs/parameters-reference.md)**

## 🧭 Known limitations

- **Source attribution is best-effort on aggregator sites.** MSN/Yahoo News/etc. don't consistently expose the original publisher in their markup; when no hint is found, the aggregator's own name is reported with `meta.source_is_aggregator=True, meta.source_resolved=False` so you can distinguish a confirmed publisher from a fallback. `tools/publisher_resolution_eval.ipynb` is a Colab notebook for spot-checking this against real aggregator pages.
- **`discover_and_get()` has no `whitelist`/`blacklist` parameters** yet, unlike `fetch()`/`search()`.
- **The TUI's Settings country field only affects `search()`**, not `fetch()`/`location` — the two use different underlying engines with different locale mechanisms (see [docs/parameters-reference.md](docs/parameters-reference.md#country--region-codes)).

Details and architecture context: [docs/architecture.md](docs/architecture.md).

---

## 🧪 Development

```bash
uv sync
uv run pytest -q
uv run python -m compileall -q open_news

# or with pip
python -m pip install -e ".[dev]"
pytest -q
python -m compileall -q open_news
```

CI runs this matrix across Python 3.10–3.13 on every push; see `.github/workflows/ci.yml`.

## 🤝 Contributing

Issues and PRs welcome:
- 🐛 Bug reports · ✨ Feature requests · 📝 Documentation · 💻 Pull requests

Please read [CONTRIBUTING.md](CONTRIBUTING.md), keep changes focused, and add tests for behavior changes. Feed-discovery targets aren't curated centrally in this version — `discover_and_get()` works against any site directly.

## 🙏 Acknowledgements

Built on: [**httpx**](https://www.python-httpx.org/) • [**lxml**](https://lxml.de/) • [**feedparser**](https://github.com/kurtmckee/feedparser) • [**BeautifulSoup4**](https://www.crummy.com/software/BeautifulSoup/) • [**googlenewsdecoder**](https://github.com/HeiseL/GoogleNewsDecoder) • [**ddgs**](https://github.com/deedy5/ddgs) • [**langdetect**](https://github.com/Mimino666/langdetect) • [**Playwright**](https://playwright.dev/) (optional)

## 📄 License

MIT — see [LICENSE](LICENSE).

<div align="center">

**Made with ❤️ by [Arajit Paul](https://github.com/alphap365)**

[⭐ Star on GitHub](https://github.com/alphap365/open-news) · [📧 Email](mailto:arajitpaul2010@gmail.com)

</div>