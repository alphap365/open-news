<div align="center">

# 📰 open-news

**Zero-Config News Fetching & Article Extraction for Python**

[![License](https://img.shields.io/github/license/alphap365/open-news?style=for-the-badge&color=blue)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)](https://github.com/alphap365/open-news)

*A lightweight, batteries-included Python package for fetching news articles, extracting content, discovering RSS feeds, and batch processing with summarization.*

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [API Reference](#-api-reference) • [Contributing](#-contributing)

</div>

---

## 🎯 Features

<table>
<tr>
<td>

### 📄 Article Extraction
Pulls full text and metadata (title, authors, publish date, top image) straight from a page's HTML using a built-in lxml-based extractor — no third-party extraction library required.

</td>
<td>

### 📡 Live News Feeds
Access curated RSS feeds with zero local configuration:
- **50+ country-specific feeds** (India, USA, Pakistan, etc.)
- **Category feeds** (business, politics, geopolitics)
- Sourced from [open-feeds](https://github.com/alphap365/open-feeds)

</td>
</tr>
<tr>
<td>

### 🔍 Google News Search
Search across Google News with decoded URLs:
- Real article links (via `googlenewsdecoder`), with a graceful fallback to the raw redirect URL if decoding fails
- Rich metadata included

</td>
<td>

### 🔗 RSS Discovery
Auto-discover RSS feeds from any website:
- No external `feedfinder2` dependency
- Built with BeautifulSoup + lxml
- Fetch articles from discovered feeds instantly

</td>
</tr>
<tr>
<td>

### ⚡ Smart Caching
24-hour feed caching to minimize network requests and improve performance

</td>
<td>

### 🚀 Batch Processing & Summarization
Process multiple articles concurrently with built-in summarization:
- Fetch and summarize batch URLs
- Search Google News + fetch + summarize in one call
- Configurable concurrency and timeouts
- Lightweight extractive summarization

</td>
</tr>
</table>

---

## 📦 Installation

### From GitHub
\`\`\`bash
git clone https://github.com/alphap365/open-news.git
cd open-news
pip install -e .
\`\`\`

### Direct Install
\`\`\`bash
pip install git+https://github.com/alphap365/open-news.git
\`\`\`

**Dependencies installed automatically:**
- `beautifulsoup4` • `lxml` • `python-dateutil`
- `feedparser` • `googlenewsdecoder` • `httpx` • `requests`

---

## 🚀 Quick Start

### 1️⃣ Extract Article Content
```python
from open_news import fetch_article

article = fetch_article("https://www.bbc.com/news/world-us-canada-12345678")

print(article["title"])
print(article["text"][:500])
print(f"Source: {article['source']}")
print(f"Published: {article['publish_date']}")
```

### 2️⃣ Search Google News
```python
from open_news import search_news

results = search_news("artificial intelligence", limit=5)

for article in results:
    print(f"✓ {article['title']}")
    print(f"  → {article['url']}\n")
```

### 3️⃣ Get Live News (Country-Specific)
```python
from open_news import get_live_news

# Get top news from India
india_news = get_live_news(country="india", limit_per_feed=3)

for article in india_news:
    print(f"[{article['source']}] {article['title']}")
    print(f"Published: {article['published']}\n")
```

### 4️⃣ Get Category News
```python
# Business news from curated feeds
business = get_live_news(category="business", limit_per_feed=2)

for article in business:
    print(f"{article['title']}")
```

### 5️⃣ Discover & Fetch RSS Feeds
```python
from open_news import get_articles_from_website_rss

# Auto-discover RSS from any website
articles = get_articles_from_website_rss("https://techcrunch.com", limit=5)

for article in articles:
    print(f"✓ {article['title']}")
```

### 6️⃣ Batch Fetch & Summarize Articles
```python
from open_news import fetch_and_summarize_batch

urls = [
    "https://example.com/article1",
    "https://example.com/article2",
    "https://example.com/article3",
]

results = fetch_and_summarize_batch(urls, sentence_count=2, max_workers=3)

for result in results:
    if result["status"] == "success":
        print(f"📰 {result['title']}")
        print(f"   Summary: {result['summary']}\n")
    else:
        print(f"❌ Failed: {result['error']}")
```

### 7️⃣ Search & Summarize in One Call
```python
from open_news import fetch_and_summarize_search_results

results = fetch_and_summarize_search_results(
    "climate change",
    limit=5,
    sentence_count=2,
    max_workers=3
)

for article in results:
    print(f"🔗 {article['url']}")
    print(f"📰 {article['title']}")
    print(f"   {article['summary']}\n")
```

---

## 📚 API Reference

### `fetch_article(url: str) → Dict`

Extract article content and metadata from a given URL.

**Returns:**
\`\`\`python
{
    "url": str,            # Original article URL
    "title": str,          # Article headline
    "text": str,           # Full article text
    "authors": list,       # Author names, if found
    "publish_date": str,   # ISO 8601 timestamp, or None if undetected
    "top_image": str,      # Best-guess main image URL, or None
    "images": list,        # All image URLs found in the article body
    "videos": list,        # Embedded video URLs (YouTube, Vimeo, etc.)
    "source": str,         # Website domain
    "meta": dict           # Raw metadata: description, site name, keywords, JSON-LD
}
\`\`\`

**Example:**
\`\`\`python
article = fetch_article("https://example.com/article")
if article["text"]:
    print(f"✓ Successfully extracted: {article['title']}")
else:
    print("✗ Could not extract article content")
\`\`\`

A note on reliability: extraction quality depends entirely on how clean and structured the page's HTML is. Heavily templated sites with lots of navigation or ad markup around the article body may need some trial and error — if a result looks off, check `meta` and `images` for clues about what got picked up.

---

### `search_news(query: str, limit: int = 10) → List[Dict]`

Search Google News for recent articles.

**Parameters:**
- `query` (str): Search terms
- `limit` (int): Maximum results to return (default: 10)

**Returns:**
```python
[
    {
        "title": str,
        "url": str,           # Decoded real URL (when possible)
        "source": str,
        "published": str,     # ISO 8601 timestamp
        "description": str
    },
    ...
]
```

**Example:**
```python
results = search_news("climate change", limit=5)
print(f"Found {len(results)} articles")
```

---

### `get_live_news(country: str = None, category: str = "news", limit_per_feed: int = None) → List[Dict]`

Fetch articles from curated RSS feeds.

**Parameters:**
- `country` (str, optional): Two-letter country code
  - Examples: `"india"`, `"usa"`, `"uk"`, `"pakistan"`
  - When set, `category` is ignored
- `category` (str): News category when no country specified
  - Options: `"news"`, `"business"`, `"politics"`, `"geopolitics"`
  - Default: `"news"`
- `limit_per_feed` (int, optional): Articles per feed (default from remote config)

**Returns:**
```python
[
    {
        "title": str,
        "url": str,
        "source": str,
        "published": str,
        "description": str
    },
    ...
]
```

**Examples:**
```python
# Country-specific
india_news = get_live_news(country="india", limit_per_feed=5)

# Category-specific
business = get_live_news(category="business")

# Default news
general = get_live_news()
```

---

### `get_articles_from_website_rss(website_url: str, limit: int = 10) → List[Dict]`

Discover and fetch articles from a website's RSS feed.

**Parameters:**
- `website_url` (str): Website homepage URL
- `limit` (int): Maximum articles to return

**Returns:** Same structure as `get_live_news()`

**Example:**
```python
articles = get_articles_from_website_rss("https://hackernews.com", limit=10)
for article in articles:
    print(f"• {article['title']}")
```

---

### `fetch_and_summarize_batch(urls: List[str], include_full_text: bool = False, sentence_count: int = 3, max_workers: int = 5, timeout_per_article: int = 30) → List[Dict]`

Fetch and summarize multiple articles concurrently.

**Parameters:**
- `urls` (List[str]): Article URLs to process
- `include_full_text` (bool): Include full article text in results (default: False)
- `sentence_count` (int): Sentences per summary (default: 3)
- `max_workers` (int): Concurrent threads (default: 5, adjust based on CPU/network)
- `timeout_per_article` (int): Timeout per article in seconds (default: 30)

**Returns:**
\`\`\`python
[
    {
        "url": str,
        "status": str,        # "success" or "failed"
        "title": str,         # Article title (empty string if failed)
        "summary": str,       # Summarized content (empty string if failed)
        "text": str,          # Full text (only present if include_full_text=True)
        "error": str          # Present only when status is "failed" — includes timeouts
    },
    ...
]
\`\`\`

A timeout just shows up as a `"failed"` result with the timeout message in `error` — there's no separate `"timeout"` status, so check `error` if you need to distinguish *why* something failed.

**Example:**
\`\`\`python
from open_news import fetch_and_summarize_batch

urls = ["https://example.com/1", "https://example.com/2"]
results = fetch_and_summarize_batch(urls, sentence_count=2)

for result in results:
    if result["status"] == "success":
        print(f"✓ {result['title']}")
        print(f"  {result['summary']}")
    else:
        print(f"✗ {result['url']}: {result['error']}")
\`\`\`

---

### `fetch_and_summarize_search_results(query: str, limit: int = 10, sentence_count: int = 3, **kwargs) → List[Dict]`

Search Google News, fetch, and summarize all results in one call.

**Parameters:**
- `query` (str): Search term
- `limit` (int): Max results (default: 10)
- `sentence_count` (int): Sentences per summary (default: 3)
- `**kwargs`: Additional arguments passed to `fetch_and_summarize_batch` (e.g., `max_workers`, `timeout`)

**Returns:** Merged list combining search metadata with extracted & summarized content

**Example:**
```python
from open_news import fetch_and_summarize_search_results

results = fetch_and_summarize_search_results(
    "artificial intelligence",
    limit=5,
    sentence_count=2,
    max_workers=3
)

for article in results:
    print(f"Title: {article['title']}")
    print(f"Summary: {article['summary']}")
```

---

## 📡 RSS Feeds

This package uses curated RSS feed definitions from the **[open-feeds](https://github.com/alphap365/open-feeds)** repository.

### Feed Sources
- **50+ country-specific feeds** (India, USA, UK, Pakistan, etc.)
- **Category feeds**: General news, Business, Politics, Geopolitics
- All feeds are community-maintained and regularly tested

### Using the Feeds
The `get_live_news()` function fetches feeds dynamically from the [open-feeds](https://github.com/alphap365/open-feeds) repository, so you always get the latest available feeds.

### Contributing to Feeds
To add new RSS feeds or report broken feeds, visit the **[open-feeds repository](https://github.com/alphap365/open-feeds)** and follow their contributing guidelines.

---

## ⚙️ Caching

Feeds are automatically cached for **24 hours** in `~/.open_news/feeds_cache/` to reduce network requests.

**Current implementation:** Cache is managed internally. Force refresh by clearing the cache directory if needed.

---

## 🔧 Requirements

- **Python:** 3.7+
- **Network:** Internet connection for live feeds

---

## 📝 License

Licensed under the **MIT License** – see [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

We'd love your contributions! Whether it's:
- 🐛 Bug reports
- ✨ Feature requests
- 📝 Documentation improvements
- 🔗 Feed suggestions (see [open-feeds](https://github.com/alphap365/open-feeds))
- 💻 Pull requests

Please check out our [Contributing Guide](CONTRIBUTING.md) before getting started.

**Ways to help:**
- Improve article extraction quality
- Add language/region support
- Write tests and documentation
- Share and star the project ⭐
- Contribute feeds to [open-feeds](https://github.com/alphap365/open-feeds)

---

## 🙏 Acknowledgements

Built on the shoulders of amazing open-source projects:

- [**feedparser**](https://github.com/kurtmckee/feedparser) – RSS parsing
- [**googlenewsdecoder**](https://github.com/HeiseL/GoogleNewsDecoder) – URL decoding
- [**BeautifulSoup4**](https://www.crummy.com/software/BeautifulSoup/) – HTML parsing
- [**lxml**](https://lxml.de/) – XML processing
- [**open-feeds**](https://github.com/alphap365/open-feeds) – RSS feed curations

---

<div align="center">

**Made with ❤️ by [Arajit Paul](https://github.com/alphap365)**

[⭐ Star us on GitHub](https://github.com/alphap365/open-news) | [📧 Email](mailto:dev.arajit.2010@gmail.com)

</div>
