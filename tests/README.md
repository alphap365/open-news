# Tests

Tests are grouped by subsystem and execution scope:

- `unit/api/`, `unit/processing/`, and `unit/extraction/` cover library behavior.
- `unit/feeds/` covers individual news-provider adapters.
- `unit/export/`, `unit/cli/`, and `unit/mcp/` cover user-facing interfaces.
- `integration/` contains end-to-end flows, including network-dependent tests.
- `conftest.py` provides fixtures and shared pytest configuration.

Run the complete suite with `uv run pytest`. Run a subsystem with a path, for
example `uv run pytest tests/unit/export` or `uv run pytest tests/integration`.
Network-dependent tests use pytest markers and skip when network access is
unavailable.
