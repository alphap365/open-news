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

## Install with uv

```bash
uv add open-news-api
```

For a CLI-only isolated installation:

```bash
uv tool install open-news-api
```

## Install from source

```bash
git clone https://github.com/alphap365/open-news.git
cd open-news

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install -e ".[dev]"
pytest -q
```

With uv:

```bash
uv sync --group dev
uv run pytest -q
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
