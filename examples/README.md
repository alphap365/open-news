# Open News examples

These small scripts demonstrate the public API against live news sources.
Run them from the repository root after installing the project.

## Set up with `uv`

```bash
uv sync --group dev
```

Run any example through the project environment:

```bash
uv run python examples/story_groups_demo.py
uv run python examples/filter_rank_demo.py
uv run python examples/async_search_demo.py
uv run python examples/structured_export_demo.py
uv run python examples/discover_site_demo.py https://www.reuters.com/world/
uv run python examples/stream_search_demo.py "artificial intelligence" --interval 30 --batches 3
```

For the MCP client example, install the MCP dependency group and run:

```bash
uv sync --group mcp
uv run python examples/mcp_client_demo.py
```

`discover_site_demo.py` takes a site, section, or feed URL. Add `--js` if the
site requires browser rendering; install the browser first with
`uv sync --group dev --group js` and `uv run playwright install chromium`.
`stream_search_demo.py` exits after the requested number of updates. Use
`--batches` and `--interval` to limit how long it polls.

## Included demos

| Script | Demonstrates |
|---|---|
| `story_groups_demo.py` | Representative stories, source names, and related articles |
| `filter_rank_demo.py` | Publisher allowlists, topic filters, and relevance ranking |
| `async_search_demo.py` | Awaitable search and grouped result handling |
| `structured_export_demo.py` | JSON-LD, CSV, and LLM-friendly text exports |
| `discover_site_demo.py` | RSS-first website discovery and optional browser rendering |
| `stream_search_demo.py` | Polling for newly discovered stories |
| `mcp_client_demo.py` | Calls the Open News MCP server over stdio |
| `colab/fetch_demo.py` | Category feed retrieval |
| `colab/search_demo.py` | Country and date-bounded search |
| `colab/export_demo.py` | Ranking, explicit clustering, and Markdown/JSON exports |
| `colab/open_news_colab_demo.ipynb` | Notebook walkthrough for Google Colab |

These examples make live network requests, so results vary with provider
availability and publication activity.
