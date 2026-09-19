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
```

`pretty` is designed for people; `json` is designed for scripts.

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

### Example

```bash
open-news fetch \
  --category tech \
  --location in \
  --language en \
  --limit 10 \
  --sort date
```

### v1.0.3 acquisition behavior

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
