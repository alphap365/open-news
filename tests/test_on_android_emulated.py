"""
tests/test_on_android_emulated.py

End-to-end smoke test that exercises the fetch() chain as if running
on Termux/Android — the primp-based ddgs tier is skipped by
duckduckgo_engine._is_termux(), and every other tier runs its normal
path (Google News → Bing → Yahoo → DDG HTML).

Emulation env vars are set by the ``_emulate_android`` fixture in
``conftest.py`` for any test marked ``android_emulated`` (see
``pytestmark`` below), and restored afterwards. No module-level
environment mutation here — it would leak into other test files.

Run:
    pytest tests/test_on_android_emulated.py -v
    pytest tests/test_on_android_emulated.py -v -m network
    pytest tests/test_on_android_emulated.py -v -m "not network"
"""

import os  # FIX: was missing, TestEmulationSetup uses os.environ
import socket
import threading
from typing import Any, Dict, List, cast

import pytest

from open_news import (
    batch_summarize,
    dedupe_articles,
    discover_and_get,
    fetch,
    get_article,
    search,
    search_and_summarize,
    search_site,
    stream_search,
    summarize_text,
    summarize_with_keywords,
)
from open_news.config import FetchConfig
from open_news.feeds import duckduckgo_engine

# Applies the conftest ``_emulate_android`` fixture to every test here.
pytestmark = pytest.mark.android_emulated


# ----------------------------------------------------------------------
# Network probing
# ----------------------------------------------------------------------

def _has_network(host="news.google.com", port=443, timeout=3.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_HAS_NETWORK = _has_network()
needs_network = pytest.mark.skipif(
    not _HAS_NETWORK,
    reason="No TCP reachability to news.google.com:443",
)


# ----------------------------------------------------------------------
# Shape helpers
# ----------------------------------------------------------------------

_REQUIRED = ("title", "url")
_OPTIONAL = ("source", "published", "description")


def _assert_article_shape(a, *, where=""):
    assert isinstance(a, dict), f"{where}: not a dict"
    for f in _REQUIRED:
        assert f in a, f"{where}: missing {f!r}"
        assert isinstance(a[f], str), f"{where}: {f!r} must be str"
    for f in _OPTIONAL:
        if f in a and a[f] is not None:
            assert isinstance(a[f], str), f"{where}: {f!r} must be str|None"


def _assert_article_list(items, *, where=""):
    assert isinstance(items, list), f"{where}: not a list"
    for i, a in enumerate(items):
        _assert_article_shape(a, where=f"{where}[{i}]")
    return items


def _call_or_skip(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}".lower()
        for needle in ("api key", "openai", "anthropic", "sumy",
                       "not installed", "extra"):
            if needle in msg:
                pytest.skip(f"Backend unavailable: {e}")
        raise


def _next_or_timeout(gen, timeout=45.0):
    box = {"v": None, "e": None, "done": False}

    def _worker():
        try:
            box["v"] = next(gen)
        except BaseException as e:  # noqa: BLE001
            box["e"] = e
        finally:
            box["done"] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)
    if not box["done"]:
        raise TimeoutError(f"no yield within {timeout}s")
    if isinstance(box["e"], StopIteration):
        raise StopIteration()
    if box["e"] is not None:
        raise box["e"]
    return box["v"]


# ======================================================================
# 1. Emulation setup sanity
# ======================================================================

class TestEmulationSetup:
    """The emulation only matters if the process truly believes it's on
    Termux and every escape hatch is in its default (off) state."""

    def test_termux_env_var_visible(self):
        assert os.environ.get("TERMUX_VERSION")

    def test_engine_detects_termux(self):
        assert duckduckgo_engine._is_termux() is True

    def test_try_ddgs_on_termux_not_set(self):
        assert duckduckgo_engine._try_ddgs_on_termux() is False

    def test_skip_ddgs_not_set(self):
        assert duckduckgo_engine._skip_ddgs() is False


# ======================================================================
# 2. Chain routing (all tiers mocked, no network)
# ======================================================================

class TestChainRouting:
    """The orchestrator must never reach the primp-based ddgs tier on
    Termux, and must try Google News → Bing → Yahoo → DDG HTML in order."""

    def test_termux_skips_ddgs_and_reaches_google(self, monkeypatch):
        calls = {"ddgs": 0, "google": 0}

        def spy_ddgs(config):
            calls["ddgs"] += 1
            return []

        def fake_google(config):
            calls["google"] += 1
            return [{
                "title": "Emulated article", "url": "https://example.com/a",
                "source": "example.com", "published": "",
                "description": "", "_tier": "google",
            }]

        monkeypatch.setattr(duckduckgo_engine, "_try_ddgs", spy_ddgs)
        monkeypatch.setattr(
            duckduckgo_engine.googlenews_engine, "fetch_raw", fake_google,
        )

        result = duckduckgo_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert calls["ddgs"] == 0, "ddgs must not be reached on Termux"
        assert calls["google"] == 1, "Google News tier must run"
        assert result[0]["title"] == "Emulated article"

    def test_chain_falls_through_in_order(self, monkeypatch):
        order = []

        monkeypatch.setattr(
            duckduckgo_engine.googlenews_engine, "fetch_raw",
            lambda c: order.append("google") or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine.bingnews_engine, "fetch_raw",
            lambda c: order.append("bing") or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine.yahoonews_engine, "fetch_raw",
            lambda c: order.append("yahoo") or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine, "_fetch_via_ddg_html",
            lambda c: order.append("ddg_html") or [
                {"title": "last", "url": "https://x.example/1",
                 "source": "x.example", "published": "", "description": ""},
            ],
        )

        result = duckduckgo_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert order == ["google", "bing", "yahoo", "ddg_html"]
        assert result[0]["title"] == "last"

    def test_first_non_empty_tier_wins(self, monkeypatch):
        order = []

        monkeypatch.setattr(
            duckduckgo_engine.googlenews_engine, "fetch_raw",
            lambda c: order.append("google") or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine.bingnews_engine, "fetch_raw",
            lambda c: order.append("bing") or [
                {"title": "bing", "url": "https://b.example/1",
                 "source": "b.example", "published": "", "description": ""},
            ],
        )
        monkeypatch.setattr(
            duckduckgo_engine.yahoonews_engine, "fetch_raw",
            lambda c: order.append("yahoo") or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine, "_fetch_via_ddg_html",
            lambda c: order.append("ddg_html") or [],
        )

        result = duckduckgo_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert order == ["google", "bing"]
        assert result[0]["title"] == "bing"


# ======================================================================
# 3. Pure helpers
# ======================================================================

class TestPureHelpers:

    def test_region_param(self):
        assert duckduckgo_engine._region_param(None) == "wt-wt"
        assert duckduckgo_engine._region_param("in") == "in-en"
        assert duckduckgo_engine._region_param("us-en") == "us-en"

    def test_decode_uddg(self):
        assert duckduckgo_engine._decode_uddg(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.example%2F1"
        ) == "https://x.example/1"

    def test_parse_ddg_html(self):
        html = (
            '<html><body>'
            '<div class="result results_links">'
            '<h2 class="result__title">'
            '<a class="result__a" href="https://a.example/1">First</a>'
            '</h2>'
            '<a class="result__snippet">Snippet</a>'
            '</div>'
            '</body></html>'
        )
        results = duckduckgo_engine._parse_ddg_html(html, limit=10)
        assert len(results) == 1
        _assert_article_shape(results[0], where="parsed-ddg-html")

    def test_is_hub_url_bare_domain(self):
        from open_news.fetch.url_resolver import is_hub_url
        assert is_hub_url("https://example.com") is True
        assert is_hub_url("https://example.com/") is True
        assert is_hub_url("https://example.com/article/1") is False

    def test_is_hub_url_pattern(self):
        from open_news.fetch.url_resolver import is_hub_url
        assert is_hub_url("https://apnews.com/hub/technology") is True
        assert is_hub_url("https://apnews.com/article/xyz") is False


# ======================================================================
# 4. Dedupe
# ======================================================================

class TestDedupe:

    def test_collapses_tracking_variants(self):
        articles = [
            {"url": "https://a.com/story", "title": "A"},
            {"url": "https://a.com/story?utm_source=x", "title": "B"},
            {"url": "https://b.com/story", "title": "C"},
        ]
        assert len(dedupe_articles(articles, fuzzy=False)) == 2

    def test_drops_empty_urls(self):
        articles = [
            {"url": "", "title": "no url"},
            {"url": "https://a.com/x", "title": "has url"},
        ]
        result = dedupe_articles(articles, fuzzy=False)
        assert len(result) == 1
        assert result[0]["title"] == "has url"

    def test_fuzzy_title(self):
        articles = [
            {"url": "https://a.com/1", "title": "AI takes over the world"},
            {"url": "https://b.com/2", "title": "AI takes over world"},
            {"url": "https://c.com/3", "title": "Sports update"},
        ]
        assert len(dedupe_articles(articles, fuzzy=True)) == 2


# ======================================================================
# 5. Article extraction via loopback fixture
# ======================================================================

class TestArticleExtractionLocal:
    """get_article is verified against a locally-served page so this
    suite is deterministic even on CI runners whose IP is 403'd by
    Wikipedia and similar sites."""

    def test_extracts_text(self, local_article_server):
        url = f"{local_article_server}/article1.html"
        article = _call_or_skip(get_article, url, timeout=10)
        assert isinstance(article, dict)
        assert article.get("text"), (
            f"empty text; keys={list(article)} value={article!r}"
        )
        assert article["url"] == url

    def test_missing_page_returns_empty(self, local_article_server):
        article = get_article(f"{local_article_server}/does-not-exist", timeout=5)
        assert isinstance(article, dict)
        assert article.get("text") == ""


# ======================================================================
# 6. Public API smoke tests (live network)
# ======================================================================

@needs_network
@pytest.mark.network
class TestPublicAPISmoke:

    def test_fetch_tech(self):
        articles = _call_or_skip(fetch, category="tech", max_results=5)
        _assert_article_list(articles, where="fetch(tech)")

    def test_fetch_with_location(self):
        articles = _call_or_skip(
            fetch, category="general", location="in", max_results=5,
        )
        _assert_article_list(articles, where="fetch(general, in)")

    def test_fetch_articles_are_not_homepages(self):
        from open_news.fetch.url_resolver import is_hub_url
        articles = cast(List[Dict[str, Any]], _call_or_skip(
            fetch, category="tech", max_results=5,
        ))
        for a in articles:
            assert not is_hub_url(a["url"]), (
                f"homepage/hub leaked through: {a['url']!r}"
            )

    def test_search(self):
        articles = _call_or_skip(search, "climate change", max_results=5)
        _assert_article_list(articles, where="search")

    def test_search_site(self):
        articles = _call_or_skip(search_site, "budget", "reuters.com", limit=3)
        _assert_article_list(articles, where="search_site")

    def test_discover_and_get(self):
        articles = _call_or_skip(
            discover_and_get, "https://example.com/", limit=3,
        )
        _assert_article_list(articles, where="discover_and_get")


# ======================================================================
# 7. Streaming
# ======================================================================

class TestStreaming:

    def test_returns_iterator_without_network(self):
        stream = stream_search("news", refresh_interval=5, max_results=1)
        try:
            assert hasattr(stream, "__iter__") and hasattr(stream, "__next__")
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()

    @needs_network
    @pytest.mark.network
    def test_yields_first_batch(self):
        stream = stream_search("news", refresh_interval=5, max_results=3)
        try:
            try:
                batch = _next_or_timeout(stream, timeout=60.0)
            except StopIteration:
                pytest.skip("Stream closed without yielding")
            _assert_article_list(batch, where="stream_search")
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()


# ======================================================================
# 8. Summarization
# ======================================================================

class TestSummarization:
    SAMPLE = (
        "Scientists announced a breakthrough in fusion energy this week, "
        "achieving a net-positive reaction for the first time. The experiment, "
        "conducted at a national laboratory, produced more energy than was "
        "required to start the reaction. Researchers cautioned that scaling "
        "the result to commercial power plants remains years away."
    )

    def test_summarize_text(self):
        out = _call_or_skip(summarize_text, self.SAMPLE)
        assert isinstance(out, str) and out

    def test_summarize_text_respects_sentence_count(self):
        one = summarize_text(self.SAMPLE, 1)
        two = summarize_text(self.SAMPLE, 2)
        assert one.count(". ") + 1 <= two.count(". ") + 1

    def test_summarize_with_keywords_shape(self):
        out = _call_or_skip(summarize_with_keywords, self.SAMPLE)
        assert isinstance(out, dict)
        for k in ("summary", "keywords", "coverage"):
            assert k in out
        assert isinstance(out["summary"], str)
        assert isinstance(out["keywords"], list)
        assert 0.0 <= float(out["coverage"]) <= 1.0

    def test_summarize_with_keywords_top_words_limit(self):
        out = summarize_with_keywords(self.SAMPLE, top_words=2)
        assert len(out["keywords"]) <= 2

    @needs_network
    @pytest.mark.network
    def test_batch_summarize(self):
        out = _call_or_skip(batch_summarize, ["https://example.com/"])
        assert isinstance(out, list) and out
        for e in out:
            assert isinstance(e, dict)
            assert "url" in e and "status" in e

    @needs_network
    @pytest.mark.network
    def test_search_and_summarize(self):
        out = _call_or_skip(
            search_and_summarize, "python programming language", limit=2,
        )
        assert isinstance(out, list)
        for e in out:
            assert isinstance(e, dict)
            assert "url" in e


# ======================================================================
# 9. Cross-API shape consistency
# ======================================================================

@pytest.fixture(scope="module")
def _api_samples() -> Dict[str, List[Dict[str, Any]]]:
    if not _HAS_NETWORK:
        pytest.skip("No route to news.google.com:443")
    return {
        "fetch": cast(
            List[Dict[str, Any]],
            _call_or_skip(fetch, category="tech", max_results=3),
        ),
        "search": cast(
            List[Dict[str, Any]],
            _call_or_skip(search, "technology", max_results=3),
        ),
    }


@needs_network
@pytest.mark.network
class TestCrossAPIShapeConsistency:

    def test_all_paths_share_required_fields(self, _api_samples):
        for name, articles in _api_samples.items():
            _assert_article_list(articles, where=name)

    def test_urls_are_absolute(self, _api_samples):
        for name, articles in _api_samples.items():
            for a in articles:
                assert a["url"].startswith(("http://", "https://")), (
                    f"{name}: URL not absolute: {a['url']!r}"
                )

    def test_no_hub_urls_leak(self, _api_samples):
        from open_news.fetch.url_resolver import is_hub_url
        for name, articles in _api_samples.items():
            for a in articles:
                assert not is_hub_url(a["url"]), (
                    f"{name}: hub URL slipped through: {a['url']!r}"
                )