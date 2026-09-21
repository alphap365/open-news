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
| **10** | 🔴 Live refresh (category or keyword search) |
| **11** | 🧩 Cluster loaded articles |
| **12** | 📤 Export loaded articles / clusters |
| **0** | 🚪 Exit |

The current settings are displayed at the bottom of the interface so the active defaults remain visible.

---

### 📊 Rank query vs. rank method

Two different settings, easy to mix up:

- **`[10] Rank method`** — the backend used when ranking runs (`auto`, `bm25`, `tfidf`, `basic`). It does nothing on its own.
- **`[12] Rank query`** — the query string that ranking scores against, if set.

Setting **12** makes ranking apply automatically after every fetch and search, using the method from **10**. Leaving **12** blank means fetch/search results come back in engine order, and ranking only happens where you explicitly provide a query — currently in the cluster flow (menu 11).

> Earlier builds of this TUI prompted for a rank query on every fetch and search. That prompt has been removed; ranking is opt-in via setting 12 or via the cluster flow.

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
If a persistent rank query is set in Settings (12), the results are re-ranked after fetch before they're displayed. Otherwise they're shown in the acquisition engine's order.
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

# 1️⃣1️⃣ Cluster loaded articles

Groups the currently loaded articles into story clusters by title similarity.

Prompts, in order:

1. **Title similarity threshold** — defaults to the session setting (11). Lower means looser grouping.
2. **Drop single-article clusters?** — `y` / `N`.
3. **Sort clusters by** — Score / Size / Date.
4. **Rank representatives by relevance to** — pre-filled with the session's persistent rank query (setting 12) if one is set; blank keeps the current order.

The result is held in `self.clusters` for the rest of the session. Export it from menu 12, or inspect individual articles from menu 7.

Uses the same `cluster_articles()` API as the Python and CLI surfaces, so dedupe, topic filtering, and rank integration behave identically.

### When it returns zero clusters

If every loaded article is a distinct story, nothing pairs up above the threshold, and with **Drop single-article clusters** enabled, every size-1 cluster is removed. The TUI reports this explicitly:

```text
No clusters met the criteria. The 21 loaded articles look like distinct stories at threshold 0.75.
Try a lower threshold (e.g. 0.65), or allow single-article clusters.
```

Two ways to see clustering do something on a mixed feed:

- **Lower the threshold** (try `0.6`–`0.65`).
- **Allow single-article clusters** (`N` at step 2), which lets the score/size sort still be useful.

For the clearest demonstration, run menu 2 (search by keyword) with a narrow term first — e.g. one specific event — then cluster. Same-event coverage from different outlets is exactly what clustering is for.

---

# ⚙️ Settings

Settings are kept for the current TUI session.

Available settings include:

| Key | Setting |
|---:|---|
| 1 | 🌍 language filter |
| 2 | 📊 sort order |
| 3 | 📄 full-content extraction |
| 4 | 🌐 JavaScript rendering |
| 5 | 🔢 default result limit |
| 6 | ✅ domain whitelist |
| 7 | ⛔ domain blacklist |
| 8 | 🌐 country (search only) |
| 9 | 🏷️ topic filter + mode |
| 10 | 📊 rank method |
| 11 | 🧩 cluster threshold |
| 12 | 📊 persistent rank query |

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

The status footer under the main menu reflects the current session settings, including the persistent rank query (`rank_query=...` when set, `rank_query=none` otherwise) and the current cluster threshold.
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
