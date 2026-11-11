# Installation

## Requirements

- Python 3.10 or newer.
- Network access for live news discovery and article retrieval.
- Optional Playwright browser installation only when JavaScript rendering is required.

## Install from PyPI

```bash
python -m pip install open-news-api
```

Verify the package and CLI:

```bash
python -c "import open_news; print(open_news.__version__)"
open-news --version
open-news --help
```

## Optional dependencies

### JavaScript rendering

```bash
python -m pip install "open-news-api[js]"
playwright install chromium
```

Use `js=True` in supported Python calls or `--js` in supported CLI commands. Browser rendering is optional; standard HTTP extraction remains available without it.

### NLP extras

```bash
python -m pip install "open-news-api[nlp]"
```

The `nlp` extra installs optional BM25 and summarization components. Ranking with `method="auto"` can use a pure-Python TF-IDF fallback when `bm25s` is unavailable.

### MCP server

```bash
python -m pip install "open-news-api[mcp]"
open-news-mcp
```

This installs FastMCP and provides the `open-news-mcp` stdio server command.
See the [MCP guide](mcp.md) for client setup, tool descriptions, and a runnable
client example. MCP support is still growing; some Python API features are not
yet available as MCP tools.

## Install with uv

Install Open News into the current project's environment:

```bash
uv add open-news-api
```

Add optional features when your application needs them:

```bash
uv add "open-news-api[js]"
uv add "open-news-api[nlp]"
# Or combine optional features:
uv add "open-news-api[js,nlp]"
uv add "open-news-api[mcp]"
```

Run the CLI without adding it to the current project:

```bash
uvx --from open-news-api open-news --help
uvx --from open-news-api open-news search "artificial intelligence" --limit 10
```

For repeated CLI use, install it as an isolated tool:

```bash
uv tool install open-news-api
open-news --help
```

To use JavaScript rendering from an application, install the `js` extra and Chromium:

```bash
uv add "open-news-api[js]"
uv run playwright install chromium
```

The `nlp` extra provides optional BM25 ranking and summarization components. Without `bm25s`, `method="auto"` can fall back to TF-IDF.

## Install from source

Clone the repository and sync its development dependencies:

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news
uv sync --group dev
uv run pytest -q
```

Run the CLI, type checks, and package build in the managed environment:

```bash
uv run open-news --help
uv run mypy src/open_news
uv build
```

For source development with optional JavaScript support, sync the `js` group too:

```bash
uv sync --group dev --group js
uv run playwright install chromium
```

`uv sync` creates and maintains the project's virtual environment; commands run through `uv run` do not require manual environment activation. A pip-based editable install is also available:

```bash
python -m pip install -e ".[dev]"
```

## Common installation issues

### `open-news` command not found

Ensure the Python environment where the package was installed is active. For `pip --user` installs, add that environment's scripts directory to `PATH`, or use:

```bash
python -m open_news.cli --help
```

### Playwright cannot find Chromium

Install the browser after installing the `js` extra:

```bash
playwright install chromium
```

### Native dependency/build errors

Use a supported Python version and ensure your platform has the build prerequisites required by binary dependencies such as `lxml`. Prefer a prebuilt wheel when one is available for your platform.

## Release notes

For the current release history and changes, see the [changelog](changelog.md).
