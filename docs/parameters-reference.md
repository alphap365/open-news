# 🌍 Parameters Reference

Consolidated reference for parameter formats that are used in more than one
place across `fetch()`, `search()`, `search_site()`, `get_article()`, the
CLI, and the TUI, but weren't documented in one spot before.

## Country / region codes

Used by `search(country=...)` / `open-news search --country CC` (v1.0.2)
and by `fetch(location=...)` / `open-news fetch --location CC`.

- **Format:** ISO 3166-1 **alpha-2**, case-insensitive (`"in"`, `"IN"`, and
  `"In"` are all accepted and normalized internally).
- **`fetch()`/`location`:** passed straight through to DuckDuckGo News as
  its `region` parameter (internally suffixed to `xx-en` when no explicit
  sub-region is given, e.g. `in` → `in-en`). DuckDuckGo accepts most
  standard two-letter country codes; there's no fixed enumerated list —
  an unrecognized code degrades to DuckDuckGo's global/worldwide results
  rather than erroring.
- **`search()`/`country`:** maps to Google News RSS's `gl` (geolocation)
  and `ceid` (country:language edition) parameters. Defaults to `"US"`
  when omitted. Common values:

  | Code | Region | Code | Region |
  |---|---|---|---|
  | `us` | United States | `gb` | United Kingdom |
  | `in` | India | `ca` | Canada |
  | `au` | Australia | `de` | Germany |
  | `fr` | France | `jp` | Japan |
  | `br` | Brazil | `za` | South Africa |
  | `sg` | Singapore | `ae` | UAE |

  This isn't an exhaustive list — Google News supports the same
  country set as its own edition picker. If a code isn't a recognized
  Google News edition, results silently fall back to a broader/global
  match rather than raising.
- **Not currently supported:** `discover_and_get()` and `search_site()`
  have no country/region parameter — both search the target site/domain
  directly regardless of locale.

## Language codes

Used by `language=...` across `fetch()`, `search()`, `search_site()`, and
`get_article()`'s extracted `meta.language`.

- **Format:** ISO 639-1 two-letter code (`"en"`, `"hi"`, `"es"`, `"fr"`,
  `"ja"`, ...), lowercase.
- Applied as a **post-download filter** (`processing/language_guard.py`)
  using `langdetect` — it doesn't change what the underlying engine
  searches for, it drops results whose detected title+description
  language doesn't match. Very short text is undetectable and is kept
  rather than dropped (see `language_guard.py`'s docstring).
- In `search()`, `language` also feeds Google News' `hl` parameter
  (interface/results language hint) alongside `country`'s `gl`/`ceid`.
- If `langdetect` isn't installed, language filtering is skipped
  entirely (with a one-time warning) rather than silently dropping all
  results.

## Date formats

### `search(start_date=..., end_date=...)` — custom date range (v1.0.2)

Accepts any of:
- A `'YYYY-MM-DD'` string (preferred, unambiguous): `"2026-08-01"`
- Any ISO-8601 datetime string `datetime.fromisoformat()` understands,
  e.g. `"2026-08-01T14:30:00"` — only the date portion is used, the time
  is discarded
- A Python `date` or `datetime` object

Both bounds are optional and independent:
- Only `start_date` → "everything published on/after that date"
- Only `end_date` → "everything published on/before that date"
- Both → an inclusive range

`start_date`/`end_date` **take precedence over `time_limit`** — if either
is set, the coarse `d`/`w`/`m` recency window is ignored. Internally these
map to Google News RSS's `after:YYYY-MM-DD` / `before:YYYY-MM-DD` search
operators.

```python
search("elections", start_date="2026-08-01", end_date="2026-08-31")
search("elections", start_date=date(2026, 8, 1))          # open-ended: since Aug 1
```

Invalid strings (anything `datetime.fromisoformat()` rejects) raise
`ValueError` at `SearchConfig` construction time — before any network
call — same as other config validation.

### `time_limit` — coarse recency window

Used by both `fetch()` and `search()` when no custom date range is given.

| Value | Meaning |
|---|---|
| `"d"` (default) | last 24 hours |
| `"w"` | last 7 days |
| `"m"` | last 30 days |

### Article `publish_date` (output field)

`get_article()`, `fetch()`, `search()`, and `discover_and_get()` results
report `publish_date` as an **ISO-8601 string** (`YYYY-MM-DDTHH:MM:SS[+TZ]`)
when a date could be extracted and passed `core/strategies.py`'s
`_valid_date()` sanity check (rejects pre-1995 dates and anything more
than ~2 days in the future), or `None` if no publish date was found.
Raw search-engine results (before extraction) instead carry a `published`
field, which is whatever free-text date string the engine itself returned
(not guaranteed to be ISO-8601) — `processing/ranker.py` parses this
leniently with `dateutil` for sorting.

## Category values

Used by `fetch(category=...)` / `open-news fetch --category ...`:

```
general · business · tech · sports · health · science · entertainment
```

Any other value raises `ValueError` from `FetchConfig` — this is a closed
enum, unlike `language`/`country` which are open-ended codes.

## Sort values

| Function | Accepted `sort_by` values |
|---|---|
| `fetch()` | `date`, `relevance`, `popularity` |
| `search()` | `date`, `relevance` *(no `popularity` — clustering isn't run on keyword search results)* |

Passing `"popularity"` to `search()` raises `ValueError` at config
construction (the CLI/TUI both narrow their own `--sort`/menu choices to
avoid this ever reaching the API layer).