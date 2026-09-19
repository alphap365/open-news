# 📺 TUI Guide

Launch the interactive terminal interface with:

```bash
open-news-tui
```

The TUI is designed for users who want Open News functionality without memorizing command-line flags.

---

## 🧭 Main menu

| # | Action |
|---:|---|
| **1** | 📰 Fetch category news |
| **2** | 🔎 Search by keyword |
| **3** | 🌐 Discover a website |
| **4** | 🎯 Search one domain |
| **5** | 📄 Extract one article |
| **6** | ✂️ Summarize URLs or a topic |
| **7** | 📚 View loaded articles |
| **8** | ⚙️ Settings |
| **9** | 🧹 Clear loaded articles |
| **10** | 🔴 Live refresh category news |
| **0** | 🚪 Exit |

The current settings are displayed at the bottom of the interface so the active defaults remain visible.

---

# 1️⃣ Fetch category news

Choose a category such as:

```text
general
business
tech
sports
health
science
entertainment
```

The TUI can also use a location/country code.

Results are obtained through the same `fetch()` API used by Python and the CLI, including the v1.0.3 acquisition fallback architecture.

---

# 2️⃣ Search by keyword

The search flow supports:

- `any` — any query term;
- `all` — all query terms;
- `exact_phrase` — exact phrase matching;
- exclusion terms;
- language;
- sorting;
- domain filtering;
- optional full-content extraction.

The underlying search API also supports country selection and custom date ranges.

---

# 3️⃣ Discover a website

Enter a homepage or section URL.

The discovery flow prefers RSS when available and otherwise falls back to same-domain crawling.

JavaScript rendering can be enabled from Settings when the optional Playwright installation is available.

---

# 4️⃣ Search one domain

Enter a keyword and a domain such as:

```text
keyword: climate policy
domain: reuters.com
```

The operation uses the public `search_site()` API.

---

# 5️⃣ Extract one article

Provide an article URL to retrieve its extracted title, text, metadata, media, and source information.

After viewing an article, the TUI can offer actions such as:

```text
o → open in browser
s → save JSON
```

---

# 6️⃣ Summarize

The summarization workflow can operate on:

- one or more URLs;
- a topic search.

It uses the same lightweight extractive summarization system exposed by the Python API.

---

# ⚙️ Settings

Settings are kept for the current TUI session.

Available settings include:

- 🌍 language filter;
- 📊 sort order;
- 📄 full-content extraction;
- 🌐 JavaScript rendering;
- 🔢 default result limit;
- ✅ domain whitelist;
- ⛔ domain blacklist.

The installer-created configuration file is separate from these session settings.

---

# 🔴 Live refresh

Menu **10** starts live category/location polling.

Conceptually:

```text
fetch()
  │
  ▼
poll
  │
  ▼
compare with previous results
  │
  ▼
show only newly-seen articles
  │
  ▼
wait
  │
  └──────────► poll again
```

Press `Ctrl+C` to stop and return to the main menu.

### Keyword streaming

The Python API and CLI already support live keyword search:

```python
stream_search("budget 2026", refresh_interval=30)
```

```bash
open-news search "budget 2026" --stream 30
```

The current TUI menu 10 remains focused on category/location refresh rather than exposing a separate keyword-stream menu.

---

# 📚 Loaded articles

Menu 7 lets you inspect articles accumulated during the current TUI session.

Crawler-discovered articles can have different metadata availability from RSS/search results. The TUI therefore uses the article URL/domain as a display fallback when a source name is unavailable.

---

# 🧪 TUI design principle

The TUI should remain a presentation layer.

```text
TUI
 │
 ▼
public Python API
 │
 ▼
Open News core
```

It should not duplicate acquisition, extraction, filtering, or ranking logic. This keeps behavior consistent between the TUI, CLI, and Python API.
