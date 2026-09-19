"""Shared pytest configuration for the open-news test suite.

Contains:

* ``pytest_configure`` — registers the custom marks used across the
  suite. This hook must live at pytest's plugin-loading layer (i.e. in
  ``conftest.py``), not inside a ``test_*.py`` module: pytest fires
  ``pytest_configure`` during startup, before test modules are imported,
  so a hook defined inside a test file is registered too late to have
  any effect and the ``PytestUnknownMarkWarning`` you're trying to
  silence will keep appearing.

* ``sample_article_dict`` / ``sample_articles_list`` — small fixtures
  used by the dedupe and pipeline tests.
"""

import pytest


def pytest_configure(config):
    """Register custom marks used by the test suite.

    Doing this here (rather than in ``pyproject.toml``) keeps the
    definitions co-located with the code that actually uses them and
    makes ``-m network`` / ``-m 'not network'`` filtering work even if
    the config file is missing or overridden.
    """
    config.addinivalue_line(
        "markers",
        "android_emulated: exercises the engine as if running on Termux/Android "
        "(primp disabled, ddgs and duckpy skipped).",
    )
    config.addinivalue_line(
        "markers",
        "network: requires outbound TCP to html.duckduckgo.com:443 and "
        "similar; auto-skipped when offline.",
    )


@pytest.fixture
def sample_article_dict():
    return {
        "title": "Breaking News: AI takes over",
        "url": "https://example.com/story/2026/01/01/ai",
        "source": "Example News",
        "published": "2026-01-01T12:00:00",
        "description": "A detailed story about AI taking over the world.",
        "text": "This is the full body text. " * 50,
    }


@pytest.fixture
def sample_articles_list(sample_article_dict):
    return [
        {**sample_article_dict, "title": "AI takes over the world", "url": "https://a.com/1"},
        {**sample_article_dict, "title": "AI takes over the world update", "url": "https://b.com/2"},
        {**sample_article_dict, "title": "Different story", "url": "https://c.com/3"},
    ]