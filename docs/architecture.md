# Architecture

Open News is organized into acquisition, extraction, processing, and output layers. `api.py` is the public orchestration boundary; the CLI delegates to that API rather than implementing a separate news-processing stack.

![Architecture](assets/architecture.svg)

[Open the full-size architecture diagram](assets/architecture.svg).

## Package map

```text
open_news/
├── __init__.py              Public exports and package version
├── api.py                   Sync/async public API and orchestration
├── cli.py                   Command-line interface
├── config.py                Validated configuration objects
├── core/
│   ├── extractor.py         Extraction strategy coordinator
│   ├── renderer.py          Optional browser rendering
│   ├── source_resolver.py   Publisher/source attribution
│   └── strategies.py        Structured-data and HTML extraction
├── feeds/
│   ├── duckduckgo_engine.py Multi-tier fetch orchestration
│   ├── googlenews_engine.py Google News acquisition
│   ├── bingnews_engine.py   Bing News acquisition
│   ├── yahoonews_engine.py  Yahoo News acquisition
│   ├── rss_discovery.py     RSS discovery
│   └── sources.py           Feed/source normalization
├── fetch/
│   ├── article.py           Sync/async article retrieval
│   ├── crawler.py           Website crawling
│   └── url_resolver.py      Redirect and URL classification
├── processing/
│   ├── pipeline.py          Sync/async processing pipelines
│   ├── batch.py             Batch and search summarization
│   ├── cluster.py           Similar-story clustering
│   ├── rank.py              Relevance ranking
│   ├── ranker.py            Ranking helpers
│   ├── token_filter.py      Query/topic filtering
│   ├── domain_filter.py     Domain allow/deny filters
│   ├── language_guard.py    Language checks
│   ├── dedupe.py            Duplicate removal
│   └── summarizer.py        Extractive summarization
├── export/
│   ├── markdown.py          Markdown serialization
│   ├── json.py              JSON serialization
│   └── _shape.py            Shared output normalization
└── utils/                   Date, text, HTTP, and user-agent helpers
```

## Request lifecycle

![Processing pipeline](assets/pipeline.svg)

[Open the full-size pipeline diagram](assets/pipeline.svg).

1. **Acquire:** `fetch()` or `search()` asks the feed layer for candidate records. Fetch acquisition uses a fallback-oriented chain rather than requiring every provider to succeed.
2. **Normalize:** provider-specific records are normalized into article dictionaries.
3. **Process:** configured language, topic/token, and domain filters run alongside deduplication and ranking.
4. **Enrich:** optional full-content extraction runs after the result set has been narrowed. The async pipeline provides async enrichment behavior.
5. **Present:** results are returned to Python callers or formatted by the CLI.
6. **Export:** Markdown and JSON exporters serialize article or cluster-shaped data.

## Sync and async execution

The newer source exposes async entry points in addition to synchronous functions. The async path is not merely a synchronous wrapper for the whole workflow: async feed retrieval, article retrieval, pipeline enrichment, and batch summarization are implemented in their respective modules.

Use async entry points when the calling application already runs an event loop or needs to coordinate concurrent I/O. Use the synchronous API for scripts and ordinary blocking workflows.

## Acquisition fallback

The fetch engine coordinates multiple sources. The exact provider outcome depends on availability, parsing success, and whether usable results are returned. A source failure should be treated as a fallback condition where supported, not as proof that all news discovery has failed.

Search is a separate keyword-oriented path and should not be described as an identical copy of the category-fetch chain.

## Extraction strategy

Article extraction combines multiple signals, including structured metadata such as JSON-LD, Open Graph metadata, and HTML heuristics. Publisher pages vary considerably, so fields such as `publish_date`, `description`, and `source` are best-effort.

The optional browser renderer is intended for pages whose useful content is not available in the initial HTML response.

## Processing behavior

- **Filtering:** query and topic matching can narrow results.
- **Domain filtering:** whitelists keep allowed publishers; blacklists remove matching domains.
- **Deduplication:** URL/title-oriented logic reduces repeated stories.
- **Ranking:** relevance ranking can use BM25, TF-IDF, or a basic method.
- **Clustering:** similar headlines are grouped and accompanied by cluster metadata.
- **Summarization:** extractive summaries are produced locally from available article text.

## Output contracts

The export package provides Markdown and JSON serialization. JSON output supports a schema-versioned envelope and can remove internal implementation fields from exported records. Export functions can return the serialized text and optionally write it to a path.

## Design boundaries

- External news providers are not controlled by Open News.
- Location hints do not guarantee publisher origin.
- Browser rendering and NLP ranking are optional dependencies.
- Internal modules may evolve; applications should prefer imports from `open_news` where a public export exists.
