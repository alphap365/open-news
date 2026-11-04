"""Verify the public API surface that open_news/__init__.py exports.

Two failure modes this file exists to catch:

  1. __init__.py imports a symbol that doesn't exist yet (e.g. fetch_async
     added to the exports before api.py defines it). Without this file, the
     only symptom is a collection error in every *other* test module, which
     makes git-bisect point at "the wrong file".

  2. __version__ in __init__.py drifts from pyproject.toml's
     project.version — a quiet mismatch that only surfaces when
     pip install . metadata disagrees with open_news.__version__.
"""

import tomllib
from pathlib import Path

import pytest

import open_news

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------------
# __all__ integrity
# ----------------------------------------------------------------------

def test_every_export_resolves():
    """Every name in __all__ must be an attribute of the package.

    This is the test that would have caught the current PR: fetch_async
    is in __all__ but api.py doesn't define it, so getattr raises."""
    missing = [n for n in open_news.__all__ if not hasattr(open_news, n)]
    assert not missing, (
        f"__all__ lists names that open_news does not define: {missing}. "
        f"Either implement them or remove them from __all__."
    )


def test_no_duplicate_exports():
    dupes = [n for n in set(open_news.__all__) if open_news.__all__.count(n) > 1]
    assert not dupes, f"__all__ contains duplicate entries: {dupes}"


# ----------------------------------------------------------------------
# Version consistency
# ----------------------------------------------------------------------

def test_version_matches_pyproject():
    pyproject = _REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml not present")
    with pyproject.open("rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert open_news.__version__ == declared, (
        f"open_news.__version__={open_news.__version__!r} disagrees with "
        f"pyproject.toml project.version={declared!r}; both must match"
    )


# ----------------------------------------------------------------------
# Stable sync API — must always be present
# ----------------------------------------------------------------------

REQUIRED_SYNC_EXPORTS = (
    "fetch", "search", "stream_fetch", "stream_search",
    "get_article", "discover_and_get", "search_site",
    "batch_summarize", "search_and_summarize",
    "summarize_text", "summarize_with_keywords",
    "dedupe_articles", "cluster_articles", "rank_articles",
    "filter_articles",
    "to_markdown", "to_json",
)


@pytest.mark.parametrize("name", REQUIRED_SYNC_EXPORTS)
def test_required_sync_export_present(name):
    assert hasattr(open_news, name), (
        f"open_news.{name} is missing; this name is part of the stable "
        f"sync API and existing scripts depend on it"
    )


# ----------------------------------------------------------------------
# Optional async API — present-or-absent, never half-broken
# ----------------------------------------------------------------------

OPTIONAL_ASYNC_EXPORTS = (
    "fetch_async", "search_async",
    "get_article_async",
    "batch_summarize_async", "search_and_summarize_async",
)


@pytest.mark.parametrize("name", OPTIONAL_ASYNC_EXPORTS)
def test_async_export_fully_wired_or_absent(name):
    """If the async name appears in __all__, it must be callable. If it
    doesn't appear, that's fine — the async migration hasn't landed yet.
    What is *not* allowed is 'present in __all__ but broken on import'."""
    if name not in open_news.__all__:
        pytest.skip(f"{name} not yet in __all__; async API not yet landed")
    fn = getattr(open_news, name)
    assert callable(fn), (
        f"open_news.{name} is in __all__ but is not callable "
        f"(got {type(fn).__name__})"
    )