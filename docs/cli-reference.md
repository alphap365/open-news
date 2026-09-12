# 🖥️ CLI Reference

```bash
open-news <command> [options]
```

Global: `--version` prints the installed version.

Every subcommand shares `--format {pretty,json}` (default: pretty, or your `~/.config/open-news/config.json` default) and `--save FILE` (writes full JSON alongside the pretty output).

## `fetch`
```bash
open-news fetch --category tech --limit 5 --sort date --time-limit d
```
`--category`, `--location`, `--limit`, `--language`, `--sort {date,relevance,popularity}`, `--time-limit {d,w,m}`, `--full-content`, `--js`, `--whitelist`, `--blacklist`, `--dedupe`/`--no-dedupe`.

## `search`
```bash
open-news search "artificial intelligence" --mode all --exclude sports --limit 10
```
`query` (positional), `--mode {any,all,exact_phrase}`, `--exclude TERMS` (comma-separated), `--sort {date,relevance}` *(no popularity)*, plus the same filter/output flags as `fetch`.

## `extract`
```bash
open-news extract https://example.com/article --js --save article.json
```
`url` (positional), `--js`, `--timeout`.

## `discover`
```bash
open-news discover https://www.bbc.com --limit 10 --max-pages 20 --no-rss
```
`url` (positional), `--limit`, `--max-pages`, `--max-depth`, `--js`, `--no-rss`, `--full-content`, `--no-dedupe`.

## `search-site`
```bash
open-news search-site "climate policy" reuters.com --limit 5
```
`keyword domain` (positional), `--mode`, `--language`, `--full-content`, `--js`.

## `summarize`
```bash
open-news summarize https://a.com/1 https://a.com/2
open-news summarize --query "renewable energy" --limit 8 --sentences 2
```
`urls` (positional, one or more) **or** `--query TOPIC`, `--sentences`, `--workers`, `--js`.

---

### Exit codes
`0` success · `1` runtime error (network, extraction, bad input caught at runtime) · `2` argparse usage error (bad flag/choice) · `130` interrupted (Ctrl-C).

### Scripting
Use `--format json` to get clean JSON on stdout for piping into `jq` etc.:
```bash
open-news search "AI" --format json | jq '.[].title'
```
