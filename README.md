<div align="center">

# 📰 Open News

### A lightweight Python toolkit for discovering, extracting, filtering, and summarizing news.

[![License](https://img.shields.io/github/license/alphap365/open-news?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-v1.0.3%20Stable-brightgreen?style=for-the-badge)](https://github.com/alphap365/open-news)
[![PyPI](https://img.shields.io/pypi/v/open-news-api?style=for-the-badge)](https://pypi.org/project/open-news-api/)

**Fetch. Search. Discover. Extract. Process. Summarize.**

Open News provides one small, scriptable interface over live news discovery, article extraction, website discovery, filtering, deduplication, ranking, and extractive summarization — with CLI and TUI interfaces included.

[🚀 Quick Start](#-quick-start) · [🏗️ Architecture](#️-architecture) · [📦 Installation](#-installation) · [🐍 Python API](#-python-api) · [📚 Documentation](#-documentation) · [🤝 Contributing](#-contributing)

</div>

---

## ✨ What is Open News?

Open News is intentionally **not a full news platform**. It is a reusable library and set of interfaces for applications that need reliable access to news data without building the entire acquisition and processing stack themselves.

```text
                         ┌─────────────────────┐
                         │      Your App       │
                         └──────────┬──────────┘
                                    │
                         Python API / CLI / TUI
                                    │
                         ┌──────────▼──────────┐
                         │    Open News API    │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                 Acquire         Process         Extract
                    │               │               │
                    ▼               ▼               ▼
              live sources    filter · dedupe   article text
              RSS / search    rank · enrich     metadata/media
```

### 🎯 Design goals

- **Lightweight** — use ordinary Python tooling where possible.
- **Resilient** — acquisition can fall back across multiple sources.
- **Composable** — public functions can be embedded into other projects.
- **Local-first processing** — filtering, deduplication, ranking, and summarization do not require an LLM or hosted AI service.
- **Scriptable** — JSON output makes the CLI suitable for pipelines.
- **Portable** — desktop Linux, macOS, WSL/Git Bash, and Termux are supported by the installation workflow.
- **Stable core** — v1.0.3 freezes the architecture developed and validated during the 1.0.3 pre-release cycle.

---

## 🧭 v1.0.3 at a glance

> **v1.0.3 is the stabilized result of the Issue #1 architecture effort.**
>
> The `v1.0.3a1` → `a6` → `b1` → `b2` sequence was a development and validation cycle for a substantial acquisition/resilience change. Those pre-releases are historical milestones; **the meaningful release comparison is v1.0.2 → v1.0.3**.

### The central change

`fetch()` is no longer dependent on a single acquisition route. It now uses a five-tier fallback chain:

```text
1. DDGS
   │
   ├── results ───────────────► return
   │
   ▼ empty / unavailable
2. Google News
   │
   ├── results ───────────────► return
   │
   ▼ empty / failed
3. Bing News
   │
   ├── results ───────────────► return
   │
   ▼ empty / failed
4. Yahoo News
   │
   ├── results ───────────────► return
   │
   ▼ empty / failed
5. DuckDuckGo HTML
   │
   └─────────────────────────► final attempt
```

This is complemented by stronger URL resolution, aggregator-aware source attribution, hub/listing detection, deterministic test infrastructure, Android/Termux support, and a hardened installer.

---

## 🌟 Features

| Capability | What it provides |
|---|---|
| 📰 **Live news** | Category/location news through a resilient multi-tier acquisition chain |
| 🔎 **Keyword search** | Google News RSS search with query modes, exclusions, locale, and date ranges |
| 🔴 **Streaming search** | Polling APIs that yield only newly-seen articles |
| 📄 **Article extraction** | Title, text, authors, dates, images, videos, source, and metadata |
| 🌐 **Website discovery** | RSS-first discovery with same-domain crawler fallback |
| 🧭 **Source resolution** | Best-effort original-publisher resolution for aggregator-hosted stories |
| 🧹 **Processing** | Language guard, token filtering, domain filters, dedupe, and ranking |
| ✂️ **Summarization** | Lightweight extractive summaries with no network requirement for raw text |
| 🖥️ **CLI** | Human-readable or JSON output for shell workflows |
| 📺 **TUI** | Numbered terminal interface for interactive use |
| 📱 **Termux** | Dedicated installation flow and acquisition safeguards |
| 🧪 **Testing** | Unit, contract, network, native-dependency, and local-server test infrastructure |

---

## 📦 Installation

> **Package name:** `open-news-api`  
> **Python:** `3.10+`

### ⚡ Interactive installer

```bash
curl -fsSL https://raw.githubusercontent.com/alphap365/open-news/main/install.sh | bash
```

The installer detects the environment, can create an isolated environment, optionally installs JavaScript rendering, configures PATH, saves CLI preferences, and verifies the resulting installation.

### 🐍 pip

```bash
pip install open-news-api
```

Pin v1.0.3 explicitly when you want the stable release:

```bash
pip install open-news-api==1.0.3
```

### ⚡ uv

```bash
uv add open-news-api
```

Or try the CLI without adding it to a project:

```bash
uvx --from open-news-api open-news --help
```

### 🛠️ From source

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest -q
```

Windows activation:

```powershell
.venv\Scripts\activate
```

### 🌐 Optional JavaScript rendering

```bash
pip install "open-news-api[js]"
playwright install chromium
```

JavaScript rendering is optional. Plain HTTP extraction remains the default.

---

## 🚀 Quick Start

### 1. Fetch live news

```python
from open_news import fetch

articles = fetch(category="tech", max_results=5)

for article in articles:
    print(article["title"])
    print(article["url"])
```

### 2. Search news

```python
from open_news import search

articles = search(
    "artificial intelligence",
    query_mode="all",
    exclude_terms=["sports"],
    country="in",
    max_results=5,
)

for article in articles:
    print(f"{article['title']} → {article['url']}")
```

### 3. Extract an article

```python
from open_news import get_article

article = get_article("https://example.com/article")

print(article["title"])
print(article["text"])
print(article["source"])
```

### 4. Discover a website

```python
from open_news import discover_and_get

articles = discover_and_get("https://example.com", limit=5)
```

Open News tries RSS discovery first and falls back to same-domain crawling when appropriate.

### 5. Stream new search results

```python
from open_news import stream_search

for articles in stream_search("budget 2026", refresh_interval=30):
    for article in articles:
        print(article["title"])
```

### 6. Summarize

```python
from open_news import search_and_summarize

results = search_and_summarize(
    "renewable energy",
    limit=5,
    sentence_count=2,
)

for result in results:
    print(result["summary"])
```

---

## 🏗️ Architecture

Open News is organized around a small number of layers rather than one monolithic engine.

```text
open_news/
│
├── api.py                  Public API boundary
├── config.py               Validated configuration objects
│
├── feeds/                  News acquisition and feed discovery
│   ├── duckduckgo_engine.py   Five-tier fetch orchestrator
│   ├── googlenews_engine.py   Google News search/fetch
│   ├── bingnews_engine.py     Bing News fallback
│   ├── yahoonews_engine.py    Yahoo News fallback
│   ├── sources.py             RSS/search sources
│   └── rss_discovery.py       RSS detection
│
├── fetch/                  URL and website acquisition
│   ├── article.py             Single article retrieval
│   ├── crawler.py             Async + JS crawlers
│   └── url_resolver.py        Redirect/hub/aggregator classification
│
├── processing/             Shared result processing
│   ├── pipeline.py            Filter → dedupe → rank → enrich
│   ├── dedupe.py
│   ├── ranker.py
│   ├── language_guard.py
│   ├── domain_filter.py
│   ├── token_filter.py
│   ├── batch.py
│   └── summarizer.py
│
└── core/                   Article extraction
    ├── extractor.py           Strategy coordinator
    ├── strategies.py          JSON-LD / Open Graph / HTML heuristics
    └── renderer.py            Playwright support
```

For the full data flow, see **[`docs/architecture.md`](docs/architecture.md)**.

---

## 🖥️ CLI & 📺 TUI

### CLI

```bash
open-news fetch --category tech --limit 5
open-news search "artificial intelligence" --country in --limit 5
open-news extract https://example.com/article
open-news discover https://example.com --limit 10
open-news search-site "climate policy" reuters.com
open-news summarize --query "renewable energy" --limit 5
```

For scripting:

```bash
open-news search "AI" --format json | jq '.[].title'
```

### TUI

```bash
open-news-tui
```

The TUI provides a numbered workflow for fetching, searching, discovery, extraction, summarization, settings, and live category refresh.

---

## 🔐 Resilience & failure behavior

Open News deliberately treats acquisition as a best-effort operation.

A source failure does not automatically mean the whole `fetch()` operation fails. The acquisition orchestrator can continue through its fallback chain.

Likewise, article enrichment does not intentionally destroy good existing metadata merely because a later extraction step returned an empty field.

For aggregator-hosted stories, source resolution is explicitly **best effort**. The library records whether the source was identified as an aggregator and whether the original publisher was resolved. Consumers should not treat an unresolved aggregator attribution as ground truth.

---

## 🧪 Testing

The v1.0.3 development cycle expanded the test environment beyond ordinary unit tests.

It includes infrastructure for:

- deterministic local article-server tests;
- Android/Termux emulation;
- network-dependent test separation;
- native-dependency test separation;
- acquisition-engine contracts;
- extraction and URL-resolution behavior;
- processing and deduplication contracts;
- CLI behavior.

Run the suite locally with:

```bash
pytest -q
```

---

## 📚 Documentation

| Document | Purpose |
|---|---|
| 🏗️ [`architecture.md`](docs/architecture.md) | Internal structure and data flow |
| 📦 [`installation.md`](docs/installation.md) | Installer, manual setup, JS, Termux, uninstall |
| 🐍 [`python-api.md`](docs/python-api.md) | Public Python API |
| 🖥️ [`cli-reference.md`](docs/cli-reference.md) | Complete CLI commands and options |
| 📺 [`tui-guide.md`](docs/tui-guide.md) | Interactive terminal interface |
| 🌍 [`parameters-reference.md`](docs/parameters-reference.md) | Parameter formats and accepted values |
| 📝 [`changelog.md`](docs/changelog.md) | Release history and v1.0.3 stabilization story |

---

## 🧭 Versioning philosophy

Open News follows semantic-version-style release numbering.

The **1.0.3 pre-release series is intentionally treated as one development cycle** rather than a collection of unrelated public feature releases:

```text
Issue #1
   │
   ▼
1.0.3a1 → a2 → a3 → a4 → a5 → a6
   │
   ▼
1.0.3b1 → 1.0.3b2
   │
   ▼
1.0.3 stable
```

The stable release freezes the resulting architecture and makes the v1.0.3 behavior the documented baseline.

---

## 🤝 Contributing

Contributions are welcome, especially around:

- new acquisition fallbacks;
- extraction strategies;
- deterministic tests;
- portability improvements;
- documentation;
- performance and resource usage.

Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

---

## 📄 License

Open News is released under the **MIT License**. See [`LICENSE`](LICENSE).

<div align="center">

### 📰 Open News — small enough to embed, capable enough to build on.

</div>
