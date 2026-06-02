# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-02

### Added
- **Article Extraction**: Extract full text and metadata from news articles with smart fallback pipeline (newspaper4k → trafilatura → BeautifulSoup)
- **Live News Feeds**: Access 50+ country-specific feeds (India, USA, Pakistan, etc.) and category feeds (business, politics, geopolitics)
- **Google News Search**: Search across Google News with decoded real URLs via `googlenewsdecoder`
- **RSS Discovery**: Auto-discover RSS feeds from any website using BeautifulSoup + lxml
- **Smart Caching**: 24-hour feed caching to minimize network requests
- **Batch Processing & Summarization**: Fetch and summarize multiple articles concurrently with configurable concurrency and timeouts
- **Core API Functions**:
  - `fetch_article()` - Extract article content and metadata
  - `search_news()` - Search Google News
  - `get_live_news()` - Fetch from curated RSS feeds
  - `get_articles_from_website_rss()` - Discover and fetch RSS feeds
  - `fetch_and_summarize_batch()` - Batch process articles
  - `fetch_and_summarize_search_results()` - Search, fetch, and summarize in one call

### Features
- Zero external configuration required
- Automatic dependency management
- Support for Python 3.7+
- MIT License

### Dependencies
- newspaper4k
- trafilatura
- beautifulsoup4
- lxml
- feedparser
- googlenewsdecoder
- httpx
- requests
