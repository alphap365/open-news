# 📺 TUI Guide

```bash
open-news-tui
```

A numbered menu — no flags to remember. The bottom of every screen shows your current **Settings** line so you always know what defaults are active.

## Menu

| # | Action |
|---|---|
| 1 | Fetch category news |
| 2 | Search by keyword — asks match mode (any/all/exact_phrase) and exclude terms |
| 3 | Discover a website (RSS-first, crawler fallback) |
| 4 | Search one domain |
| 5 | Extract one article |
| 6 | Summarize URL(s) or a topic search |
| 7 | View loaded articles |
| 8 | **Settings** |
| 9 | Clear loaded articles |
| 10 | Live refresh category news |
| 0 | Exit |

## Settings (menu 8)

Persists for the session (not written to disk — that's what the installer's `config.json` is for):

- **Language** filter
- **Sort order** (date/relevance/popularity)
- **Full content** toggle (crawl+extract full text for every result)
- **JS rendering** toggle (needs the `[js]` extra + `playwright install chromium`)
- **Default limit**
- **Whitelist / blacklist** domains

## Viewing an article

After extracting or selecting a loaded article, you get a follow-up prompt:
- `[o]` open in your browser
- `[s]` save to a JSON file

## Live refresh (menu 10)

Polls `fetch()` (category/location) on an interval and prints only newly-seen articles. Press `Ctrl+C` to stop and return to the menu.

> ⚠️ **Not available for keyword search.** The underlying `search()` API has no `refresh_interval` — this is a known gap, planned for v1.0.2. Menu 10 only covers category/location fetch.

## Fixed display behavior

Articles found via the **crawler path** (no RSS feed on the site) don't carry a `source` field the way search/RSS results do — the TUI falls back to showing the URL's domain instead of `Unknown`.
