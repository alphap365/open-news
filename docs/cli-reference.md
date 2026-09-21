# 🖥️ CLI Reference

The command-line interface is available as:

```bash
open-news <command> [options]
```

The CLI is a thin interface over the public Python API.

---

## ⚡ Global behavior

### Version

```bash
open-news --version
```

### Output

Most commands support:

```bash
--format pretty
--format json
--save FILE
--export-md FILE
--export-json FILE
--export-title TITLE
--export-all-members
```

- `--save` writes the **raw** JSON dump (internal keys included).
- `--export-json` writes the **clean** schema-versioned envelope.
- `--export-md` writes clean Markdown.
- `--export-title` overrides the Markdown document title.
- `--export-all-members` includes every cluster member in Markdown.

These are independent — pass all three in the same invocation if you want raw + clean + Markdown.

Example:

```bash
open-news search "AI" --format json | jq '.[].title'
```

---

# 📰 `fetch`

Fetch live category/location news.

```bash
open-news fetch --category tech --limit 5
```

### Options

| Option | Values / example | Purpose |
|---|---|---|
| `--category` | `general`, `business`, `tech`, `sports`, `health`, `science`, `entertainment` | News category |
| `--location` | `in`, `us`, `gb` | Country/region |
| `--limit` | `5` | Maximum results |
| `--language` | `en`, `hi` | Language filter |
| `--sort` | `date`, `relevance`, `popularity` | Ranking |
| `--time-limit` | `d`, `w`, `m` | Recency window |
| `--full-content` | flag | Extract full content |
| `--js` | flag | Use browser rendering for full-content work |
| `--whitelist` | `bbc.com,reuters.com` | Keep selected domains |
| `--blacklist` | `example.com` | Remove domains |
| `--dedupe` | flag | Enable dedupe |
| `--no-dedupe` | flag | Disable dedupe |
| `--topic` | `AI, LLM` | *v1.0.4* topic filter |
| `--topic-mode` | `any`, `all`, `exact_phrase` | *v1.0.4* topic combining |
| `--rank-query` | `eu ai act` | *v1.0.4* relevance re-rank |
| `--rank-method` | `auto`, `bm25`, `tfidf`, `basic` | *v1.0.4* ranking backend |

### Example

```bash
open-news fetch \
  --category tech \
  --location in \
  --language en \
  --limit 10 \
  --sort date
```

### acquisition behavior

`fetch` uses the resilient five-tier acquisition chain:

```text
DDGS → Google News → Bing News → Yahoo News → DDG HTML
```

It returns when an acquisition tier produces results.

---

# 🔎 `search`

Search Google News by keyword.

```bash
open-news search "artificial intelligence" --mode all --limit 10
```

### Options

| Option | Values / example | Purpose |
|---|---|---|
| `query` | positional | Search text |
| `--mode` | `any`, `all`, `exact_phrase` | Query matching mode |
| `--exclude` | `sports,football` | Exclude terms |
| `--limit` | `10` | Maximum results |
| `--language` | `en`, `hi` | Language |
| `--sort` | `date`, `relevance` | Ranking |
| `--time-limit` | `d`, `w`, `m` | Recency |
| `--start-date` | `2026-08-01` | Inclusive start |
| `--end-date` | `2026-08-31` | Inclusive end |
| `--country` | `in`, `us`, `gb` | Google News locale |
| `--stream` | `30` | Poll every 30 seconds |
| `--full-content` | flag | Extract full content |
| `--js` | flag | Browser rendering |
| `--whitelist` | domains | Keep domains |
| `--blacklist` | domains | Remove domains |
| `--dedupe` / `--no-dedupe` | flag | Deduplication |
| `--topic` | `AI, LLM` | *v1.0.4* topic filter |
| `--topic-mode` | `any`, `all`, `exact_phrase` | *v1.0.4* topic combining |
| `--rank-query` | `eu ai act` | *v1.0.4* relevance re-rank |
| `--rank-method` | `auto`, `bm25`, `tfidf`, `basic` | *v1.0.4* ranking backend |

### Examples

```bash
open-news search "climate policy" --mode all --limit 5
```

Custom date range:

```bash
open-news search "elections" \
  --start-date 2026-08-01 \
  --end-date 2026-08-31
```

India edition:

```bash
open-news search "monsoon" --country in --language hi
```

Live keyword search:

```bash
open-news search "budget 2026" --stream 30
```

Press `Ctrl+C` to stop a stream.

---

# 📄 `extract`

Extract a single article.

```bash
open-news extract https://example.com/article
```

Options:

```text
--js
--timeout SECONDS
--format {pretty,json}
--save FILE
```

Example:

```bash
open-news extract https://example.com/article --js --save article.json
```

---

# 🌐 `discover`

Discover articles from a website.

```bash
open-news discover https://example.com --limit 10
```

Options:

```text
--limit
--max-pages
--max-depth
--js
--no-rss
--full-content
--no-dedupe
```

RSS discovery is preferred by default. `--no-rss` forces the crawler path.

---

# 🎯 `search-site`

Search within a single domain.

```bash
open-news search-site "climate policy" reuters.com --limit 5
```

Options:

```text
--limit
--mode {any,all,exact_phrase}
--language
--full-content
--js
```

---

# 🧩 `cluster`

Group related stories into clusters by title similarity.

```bash
open-news cluster --query "openai" --limit 40 --drop-singletons
```

### Options

| Option | Values / example | Purpose |
|---|---|---|
| `--query` | `openai` | Keyword-search source (mutually exclusive with `--category`) |
| `--category` | `tech` | Category-feed source |
| `--location` | `in`, `us` | Region for `--category` |
| `--limit` | `30` | Max source articles before clustering |
| `--threshold` | `0.75` | Title-similarity cutoff |
| `--min-cluster-size` | `1` | Drop smaller clusters |
| `--drop-singletons` | flag | Convenience for `min_cluster_size=2` |
| `--sort-clusters` | `score`, `size`, `date` | Sort order |
| `--language` | `en`, `hi` | Language filter |
| `--time-limit` | `d`, `w`, `m` | Recency for the source query |
| `--topic` / `--topic-mode` | as above | Post-source narrowing |
| `--rank-query` / `--rank-method` | as above | Representative ranking |
| `--whitelist` / `--blacklist` | domains | Domain filters |
| `--no-dedupe` | flag | Disable pre-cluster dedupe |
| *(output flags)* | | `--format`, `--save`, `--export-md`, `--export-json`, `--export-title`, `--export-all-members` |

### Examples

```bash
# Cluster openai coverage, keep only multi-outlet stories
open-news cluster --query "openai" --limit 40 --drop-singletons

# Cluster tech feed, export both formats
open-news cluster --category tech --limit 30 \
    --export-md out/tech-clusters.md --export-all-members \
    --export-json out/tech-clusters.json
```

Requires either `--query` or `--category`.

---

# 📤 `export`

Re-export a saved JSON file to Markdown and/or clean JSON, without re-fetching.

```bash
open-news export out/ai-act.json --md out/ai-act.md
```

### Options

| Option | Values / example | Purpose |
|---|---|---|
| `input` | `out/ai-act.json` | Input JSON file |
| `--md` | `out/ai-act.md` | Write Markdown |
| `--json` | `out/ai-act-clean.json` | Write schema-versioned JSON |
| `--title` | `AI Act roundup` | Markdown document title |
| `--all-members` | flag | Include all cluster members in Markdown |

### Input auto-detection

The command accepts either:

- a raw `--save` dump (a bare list),
- a `--export-json` envelope (`{articles: [...]}` or `{clusters: [...]}`).

Either way it extracts the items and re-serializes them.

### Example

```bash
open-news search "eu ai act" --save /tmp/raw.json
open-news export /tmp/raw.json --md out/ai-act.md --title "EU AI Act"
```

---

# ✂️ `summarize`

Summarize URLs or search a topic and summarize its results.

### URLs

```bash
open-news summarize \
  https://example.com/article-1 \
  https://example.com/article-2
```

### Topic search

```bash
open-news summarize \
  --query "renewable energy" \
  --limit 8 \
  --sentences 2
```

Options:

| Option | Purpose |
|---|---|
| positional `urls` | One or more article URLs |
| `--query` | Search a topic instead of passing URLs |
| `--limit` | Topic-search result limit |
| `--sentences` | Sentences per summary |
| `--workers` | Concurrent fetch/extraction workers |
| `--js` | Browser rendering |

---

# 🧾 Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success |
| `1` | Runtime error |
| `2` | Argument/usage error |
| `130` | Interrupted with Ctrl+C |

---

# 🔧 Shell scripting

Prefer JSON output for machine-readable workflows:

```bash
open-news fetch --category tech --limit 10 --format json > tech.json
```

With `jq`:

```bash
open-news search "AI" --format json \
  | jq -r '.[] | [.title, .url] | @tsv'
```

This keeps the human-oriented renderer separate from the machine-readable result contract.
