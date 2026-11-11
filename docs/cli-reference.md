# CLI reference

The command-line program is:

```bash
open-news <command> [options]
```

Start with:

```bash
open-news --help
open-news --version
open-news <command> --help
```

## Global output options

Commands that produce article results share output controls where applicable:

- `--format pretty|json` selects human-readable or JSON output.
- `--save FILE` saves the raw result payload.
- `--export-md FILE` writes a Markdown export.
- `--export-json FILE` writes a clean JSON export.
- `--export-jsonld FILE` writes Schema.org JSON-LD.
- `--export-csv FILE` writes structured CSV.
- `--export-text FILE` writes labeled plain text for LLM context and retrieval.
- `--export-title TITLE` sets the Markdown document title.
- `--export-all-members` includes all members of clusters in Markdown output.

Use `--help` for the exact options available on each command.

## `fetch`

```bash
open-news fetch --category tech --location in --limit 10
```

Fetch category-oriented news. Common options include `--category`, `--location`, `--limit`, `--language`, `--sort`, `--time-limit`, `--full-content`, `--js`, `--whitelist`, `--blacklist`, `--topic`, `--topic-mode`, `--rank-query`, and `--rank-method`.

## `search`

```bash
open-news search "artificial intelligence" --country in --limit 10
```

Search by keyword. Common options include:

- `--mode any|all|exact_phrase`
- `--exclude TERMS`
- `--limit N`
- `--language CODE`
- `--sort date|relevance`
- `--time-limit d|w|m`
- `--start-date YYYY-MM-DD`
- `--end-date YYYY-MM-DD`
- `--country CC`
- `--stream SECONDS`
- `--full-content` and `--js`
- `--whitelist DOMAINS` and `--blacklist DOMAINS`
- `--topic TERMS`, `--topic-mode MODE`
- `--rank-query QUERY`, `--rank-method METHOD`

Example:

```bash
open-news search "climate policy" \
  --mode all \
  --country in \
  --topic "energy,environment" \
  --rank-query "India climate policy" \
  --format json
```

## `extract`

```bash
open-news extract https://example.com/article
```

Retrieves and extracts one article. Options include `--js` and `--timeout SECONDS`.

## `discover`

```bash
open-news discover https://example.com --limit 10
```

Discovers and groups stories from a website. Options include `--limit`, `--max-pages`, `--max-depth`, `--js`, `--no-rss`, and `--full-content`. Same-URL records are merged; similar articles remain attached to their story.

## `search-site`

```bash
open-news search-site "climate policy" reuters.com --limit 5
```

Searches within one domain. Options include `--limit`, `--mode`, `--language`, `--topic`, and `--topic-mode`.

## `cluster`

```bash
open-news cluster --query "AI regulation" --limit 40 --drop-singletons
```

Acquires source articles and groups related stories. Options include query or category acquisition, location, result limit, similarity threshold, minimum cluster size, singleton handling, cluster sorting, language/time settings, topic filters, ranking options, and domain filters. Story grouping is always enabled.

## `summarize`

Summarize supplied URLs or search for a topic and summarize the resulting articles.

```bash
open-news summarize --query "renewable energy" --limit 5 --sentences 2
open-news summarize https://example.com/story --sentences 3
```

Options include `--query`, `--limit`, `--sentences`, `--workers`, and `--js`.

## `export`

Re-export a saved JSON file without fetching news again.

```bash
open-news export input.json --md output.md --json clean.json \
  --jsonld stories.jsonld --csv stories.csv --text context.txt
```

Any combination of `--md`, `--json`, `--jsonld`, `--csv`, and `--text` can be
used. Optional Markdown flags include `--title` and `--all-members`. JSON-LD
exports Schema.org `ItemList` and `NewsArticle` objects; CSV JSON-encodes
nested values; text exports labeled article and cluster context.

## JSON pipelines

```bash
open-news search "AI" --format json | jq '.[].title'
```

For automation, check the command's exit status and handle empty result sets. Network providers and publishers can change independently of the CLI.
