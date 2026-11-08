# Open News Colab examples

This folder contains a simple Colab notebook and a few small Python scripts you can run locally or adapt for notebook experiments.

For the full set of runnable API demos, see the [examples index](../README.md).

## Notebook

- `open_news_colab_demo.ipynb` — quick install + fetch/search/export demo for Google Colab

## Scripts

- `fetch_demo.py` — fetch technology stories and print a short summary
- `search_demo.py` — search by query, country, and date range
- `export_demo.py` — fetch stories, rank them, and export Markdown/JSON

## Quick usage

### In Google Colab

Open the notebook and run the cells in order.

### Locally

```bash
uv run python examples/colab/fetch_demo.py
uv run python examples/colab/search_demo.py
uv run python examples/colab/export_demo.py
```

Run these commands from the repository root after `uv sync --group dev`.
