"""Tests for open_news.feeds.duckduckgo_engine.

Covers all three backends and the selection logic between them:
  - ddgs native path (unchanged from pre-rewrite behavior)
  - duckpy path (pure-Python/httpx, Termux-safe, tried before HTML scraper)
  - httpx scraper fallback path (last resort)
  - Termux detection that skips ddgs entirely (duckpy still runs there)
  - escape hatches (OPEN_NEWS_TRY_DDGS_ON_TERMUX, OPEN_NEWS_SKIP_DUCKPY,
    OPEN_NEWS_FORCE_DDG_FALLBACK)
"""

import sys
import types

import pytest

from open_news.config import FetchConfig
from open_news.feeds import duckduckgo_engine
from open_news.feeds.duckduckgo_engine import (
    _decode_uddg,
    _parse_ddg_html,
    _region_param,
    fetch_raw,
)


# ----------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------

def _install_fake_ddgs(monkeypatch, *, results=None, raises=None):
    """Install a fake ddgs module. Returns the dict that captures call kwargs."""
    calls = {}

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def news(self, **kwargs):
            calls.update(kwargs)
            if raises is not None:
                raise raises
            return results if results is not None else []

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    return calls


def _install_fake_duckpy(monkeypatch, *, results=None, raises=None):
    """Install a fake duckpy module. results is a list of (title, url, description)
    tuples; each becomes an object with those attributes, like duckpy's Result."""
    calls = {}

    class FakeResult:
        def __init__(self, title, url, description):
            self.title = title
            self.url = url
            self.description = description

    class FakeClient:
        def __init__(self, **kwargs):
            # Mirrors the real duckpy.Client signature (default_user_agents,
            # proxies, etc.) — _try_duckpy now calls
            # Client(default_user_agents=USER_AGENTS), so this must accept
            # and record arbitrary kwargs rather than rejecting them.
            calls["client_kwargs"] = kwargs

        def search(self, query, **kwargs):
            calls["query"] = query
            calls.update(kwargs)
            if raises is not None:
                raise raises
            return [FakeResult(*r) for r in (results or [])]

    monkeypatch.setitem(sys.modules, "duckpy", types.SimpleNamespace(Client=FakeClient))
    return calls


def _not_termux(monkeypatch):
    """Force the engine to think it's running on a normal platform, and
    clear the escape-hatch env vars so tests start from a clean state."""
    monkeypatch.setattr(duckduckgo_engine, "_is_termux", lambda: False)
    monkeypatch.delenv("OPEN_NEWS_TRY_DDGS_ON_TERMUX", raising=False)
    monkeypatch.delenv("OPEN_NEWS_SKIP_DUCKPY", raising=False)
    monkeypatch.delenv("OPEN_NEWS_FORCE_DDG_FALLBACK", raising=False)


def _make_html_results(*items):
    """Build a minimal DDG HTML page containing the given (title, href, snippet) tuples."""
    blocks = []
    for title, url, snippet in items:
        blocks.append(f'''
        <div class="result results_links">
          <div class="links_main">
            <h2 class="result__title">
              <a class="result__a" href="{url}">{title}</a>
            </h2>
            <a class="result__snippet">{snippet}</a>
          </div>
        </div>
        ''')
    return f"<html><body>{''.join(blocks)}</body></html>"


# ----------------------------------------------------------------------
# ddgs backend — preserved behavior
# ----------------------------------------------------------------------

def test_fetch_raw_uses_current_ddgs_query_parameter(monkeypatch):
    _not_termux(monkeypatch)
    calls = _install_fake_ddgs(monkeypatch, results=[{
        "title": "Technology update",
        "url": "https://example.com/story",
        "source": "Example",
        "date": "2026-09-09",
        "body": "A technology story",
    }])

    result = fetch_raw(FetchConfig(category="tech", location="in", max_results=1))

    assert result[0]["title"] == "Technology update"
    assert calls["query"] == "technology"
    assert calls["region"] == "in-en"
    assert "keywords" not in calls


def test_ddgs_result_shape_is_preserved(monkeypatch):
    """Native ddgs results must keep their full shape so downstream code
    (pipeline, dedupe, ranker) works unchanged."""
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[{
        "title": "One", "url": "https://a.example/1",
        "source": "A", "date": "2026-09-09", "body": "snippet",
    }])

    result = fetch_raw(FetchConfig(category="general", max_results=5))

    assert result[0] == {
        "title": "One",
        "url": "https://a.example/1",
        "source": "A",
        "published": "2026-09-09",
        "description": "snippet",
    }


def test_ddgs_entries_without_url_are_dropped(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[
        {"title": "Has URL", "url": "https://x.example/1", "source": "X", "date": "", "body": ""},
        {"title": "No URL", "url": "", "source": "X", "date": "", "body": ""},
    ])

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert len(result) == 1
    assert result[0]["title"] == "Has URL"


# ----------------------------------------------------------------------
# Fallback selection: ddgs -> duckpy -> HTML scraper
# ----------------------------------------------------------------------

def test_duckpy_runs_when_ddgs_returns_empty(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[])
    calls = _install_fake_duckpy(monkeypatch, results=[
        ("duckpy result", "https://d.example/1", "a description"),
    ])

    def fail_html(config):
        raise AssertionError("HTML scraper must not run when duckpy succeeds")
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fail_html)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "duckpy result"
    assert result[0]["source"] == "d.example"
    assert calls["query"] == "news"
    # duckpy is constructed with the full UA pool, not a single pre-picked string
    assert "default_user_agents" in calls["client_kwargs"]
    assert isinstance(calls["client_kwargs"]["default_user_agents"], list)
    assert len(calls["client_kwargs"]["default_user_agents"]) > 1


def test_duckpy_runs_when_ddgs_raises(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, raises=RuntimeError("boom"))
    _install_fake_duckpy(monkeypatch, results=[
        ("duckpy result", "https://d.example/1", ""),
    ])

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "duckpy result"


def test_duckpy_skipped_when_ddgs_succeeds(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[{
        "title": "native", "url": "https://n.example/1",
        "source": "N", "date": "", "body": "",
    }])

    def fail_duckpy(config):
        raise AssertionError("duckpy must not run when ddgs succeeds")
    monkeypatch.setattr(duckduckgo_engine, "_try_duckpy", fail_duckpy)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "native"


def test_html_fallback_runs_when_both_ddgs_and_duckpy_empty(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[])
    _install_fake_duckpy(monkeypatch, results=[])

    called = {"n": 0}
    def fake_fallback(config):
        called["n"] += 1
        return [{"title": "html-fallback", "url": "https://f.example/1",
                 "source": "f.example", "published": "", "description": ""}]
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_fallback)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert called["n"] == 1
    assert result[0]["title"] == "html-fallback"


def test_html_fallback_runs_when_duckpy_raises(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[])
    _install_fake_duckpy(monkeypatch, raises=RuntimeError("duckpy boom"))

    def fake_fallback(config):
        return [{"title": "html-fallback", "url": "https://f.example/1",
                 "source": "f.example", "published": "", "description": ""}]
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_fallback)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "html-fallback"


def test_duckpy_entries_without_url_are_dropped(monkeypatch):
    _not_termux(monkeypatch)
    _install_fake_ddgs(monkeypatch, results=[])
    _install_fake_duckpy(monkeypatch, results=[
        ("Has URL", "https://x.example/1", ""),
        ("No URL", "", ""),
    ])

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert len(result) == 1
    assert result[0]["title"] == "Has URL"


# ----------------------------------------------------------------------
# Termux skip logic
# ----------------------------------------------------------------------

def test_termux_skips_ddgs_but_still_tries_duckpy(monkeypatch):
    """On Termux, ddgs must not be attempted — primp panics with SIGABRT
    which cannot be caught, so the process would die before any fallback.
    duckpy has no such risk and should run as the primary Termux path."""
    monkeypatch.setattr(duckduckgo_engine, "_is_termux", lambda: True)
    monkeypatch.delenv("OPEN_NEWS_TRY_DDGS_ON_TERMUX", raising=False)
    monkeypatch.delenv("OPEN_NEWS_SKIP_DUCKPY", raising=False)
    monkeypatch.delenv("OPEN_NEWS_FORCE_DDG_FALLBACK", raising=False)

    _install_fake_ddgs(monkeypatch, results=[{
        "title": "should not run", "url": "https://nope.example/1",
        "source": "", "date": "", "body": "",
    }])
    _install_fake_duckpy(monkeypatch, results=[
        ("termux-duckpy", "https://t.example/1", ""),
    ])

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "termux-duckpy"


def test_termux_escape_hatch_allows_ddgs(monkeypatch):
    monkeypatch.setattr(duckduckgo_engine, "_is_termux", lambda: True)
    monkeypatch.setenv("OPEN_NEWS_TRY_DDGS_ON_TERMUX", "1")
    monkeypatch.delenv("OPEN_NEWS_SKIP_DUCKPY", raising=False)
    monkeypatch.delenv("OPEN_NEWS_FORCE_DDG_FALLBACK", raising=False)

    _install_fake_ddgs(monkeypatch, results=[{
        "title": "native on termux", "url": "https://n.example/1",
        "source": "N", "date": "", "body": "",
    }])

    def fail_duckpy(config):
        raise AssertionError("duckpy must not run when ddgs escape hatch succeeds")
    monkeypatch.setattr(duckduckgo_engine, "_try_duckpy", fail_duckpy)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "native on termux"


def test_termux_html_fallback_when_duckpy_also_empty(monkeypatch):
    """On Termux, if duckpy also comes up empty, we still reach the manual
    HTML scraper as the final tier."""
    monkeypatch.setattr(duckduckgo_engine, "_is_termux", lambda: True)
    monkeypatch.delenv("OPEN_NEWS_TRY_DDGS_ON_TERMUX", raising=False)
    monkeypatch.delenv("OPEN_NEWS_SKIP_DUCKPY", raising=False)
    monkeypatch.delenv("OPEN_NEWS_FORCE_DDG_FALLBACK", raising=False)

    _install_fake_duckpy(monkeypatch, results=[])

    def fake_fallback(config):
        return [{"title": "termux-html-fallback", "url": "https://t.example/1",
                 "source": "t.example", "published": "", "description": ""}]
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_fallback)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "termux-html-fallback"


# ----------------------------------------------------------------------
# Escape hatches
# ----------------------------------------------------------------------

def test_skip_duckpy_env_var_goes_straight_to_html(monkeypatch):
    _not_termux(monkeypatch)
    monkeypatch.setenv("OPEN_NEWS_SKIP_DUCKPY", "1")
    _install_fake_ddgs(monkeypatch, results=[])

    def fail_duckpy(config):
        raise AssertionError("duckpy must not run when OPEN_NEWS_SKIP_DUCKPY is set")
    monkeypatch.setattr(duckduckgo_engine, "_try_duckpy", fail_duckpy)

    def fake_fallback(config):
        return [{"title": "skip-duckpy-fallback", "url": "https://f.example/1",
                 "source": "f.example", "published": "", "description": ""}]
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_fallback)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "skip-duckpy-fallback"


def test_force_fallback_env_var_skips_ddgs_and_duckpy_everywhere(monkeypatch):
    _not_termux(monkeypatch)
    monkeypatch.setenv("OPEN_NEWS_FORCE_DDG_FALLBACK", "1")

    def fail_ddgs(config):
        raise AssertionError("ddgs must not run when OPEN_NEWS_FORCE_DDG_FALLBACK is set")
    monkeypatch.setattr(duckduckgo_engine, "_try_ddgs", fail_ddgs)

    def fail_duckpy(config):
        raise AssertionError("duckpy must not run when OPEN_NEWS_FORCE_DDG_FALLBACK is set")
    monkeypatch.setattr(duckduckgo_engine, "_try_duckpy", fail_duckpy)

    def fake_fallback(config):
        return [{"title": "forced-fallback", "url": "https://f.example/1",
                 "source": "f.example", "published": "", "description": ""}]
    monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_fallback)

    result = fetch_raw(FetchConfig(category="general", max_results=5))
    assert result[0]["title"] == "forced-fallback"


# ----------------------------------------------------------------------
# HTML scraper — parsing (unchanged)
# ----------------------------------------------------------------------

def test_parse_ddg_html_extracts_results():
    html = _make_html_results(
        ("First story", "https://a.example/1", "First snippet"),
        ("Second story", "//duckduckgo.com/l/?uddg=https%3A%2F%2Fb.example%2F2",
         "Second snippet"),
    )
    results = _parse_ddg_html(html, limit=10)

    assert len(results) == 2
    assert results[0]["title"] == "First story"
    assert results[0]["url"] == "https://a.example/1"
    assert results[0]["source"] == "a.example"
    assert results[0]["description"] == "First snippet"
    # Protocol-relative DDG redirect is decoded to the direct URL
    assert results[1]["url"] == "https://b.example/2"


def test_parse_ddg_html_respects_limit():
    html = _make_html_results(
        *[(f"Story {i}", f"https://a.example/{i}", "") for i in range(10)]
    )
    results = _parse_ddg_html(html, limit=3)
    assert len(results) == 3


def test_parse_ddg_html_handles_malformed_input():
    assert _parse_ddg_html("not html at all", limit=5) == []


def test_parse_ddg_html_skips_blocks_without_title_link():
    html = '<html><body><div class="result">no anchor here</div></body></html>'
    assert _parse_ddg_html(html, limit=5) == []


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def test_decode_uddg_handles_protocol_relative_redirect():
    assert _decode_uddg(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.example%2F1"
    ) == "https://x.example/1"


def test_decode_uddg_returns_direct_url_unchanged():
    assert _decode_uddg("https://plain.example/1") == "https://plain.example/1"


def test_decode_uddg_handles_empty():
    assert _decode_uddg("") == ""


def test_region_param_normalization():
    assert _region_param(None) == "wt-wt"
    assert _region_param("wt-wt") == "wt-wt"
    assert _region_param("us") == "us-en"
    assert _region_param("in") == "in-en"
    assert _region_param("us-en") == "us-en"