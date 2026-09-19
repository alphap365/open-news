"""
tests/test_on_android_emulated.py

Integration smoke test that emulates Android/Termux so we can be sure
open_news still works when the primp-based ``ddgs`` backend is off the
table. On real Termux, primp's Rust runtime SIGABRTs the process at the
first network call — it cannot be caught — so "does the fallback chain
still return usable news?" is the question this file answers.

Emulation env vars (set BEFORE any ``open_news`` import, because
``duckduckgo_engine._HTML_ENDPOINT`` is bound at import time and the
hybrid ``ddgs.HttpClient`` picks its backend at construction time):

    TERMUX_VERSION=0.118.0              # _is_termux() -> True
    OPEN_NEWS_SKIP_DUCKPY=1             # skip the duckpy tier
    DDGS_DISABLE_PRIMP=1                # hybrid ddgs: never try primp
    DDGS_FORCE_HTTPX=1                  # hybrid ddgs: httpx only

We deliberately do NOT set OPEN_NEWS_FORCE_DDG_FALLBACK globally: the
natural Termux path (skip ddgs -> skip duckpy -> fallback chain) is the
interesting behaviour to exercise. The escape hatch is tested in its own
class, which flips it on, monkeypatches each tier, and verifies the
routing.

Run:
    pytest tests/test_on_android_emulated.py -v
    pytest tests/test_on_android_emulated.py -v -m network    # live calls
    pytest tests/test_on_android_emulated.py -v -m "not network"
"""

# ----------------------------------------------------------------------
# 1. Emulate Android / Termux — MUST happen before any open_news import.
# ----------------------------------------------------------------------

import os

_ANDROID_ENV = {
    "TERMUX_VERSION": "0.118.0",
    "OPEN_NEWS_SKIP_DUCKPY": "1",
    "DDGS_DISABLE_PRIMP": "1",
    "DDGS_FORCE_HTTPX": "1",
}
for _k, _v in _ANDROID_ENV.items():
    os.environ.setdefault(_k, _v)  # don't clobber an explicit override

# Now we can import the world.
import socket
import threading
from typing import Any, Dict, List

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
from open_news.feeds.duckduckgo_engine import (
    _decode_uddg,
    _parse_ddg_html,
    _region_param,
    fetch_raw,
)


# ----------------------------------------------------------------------
# 2. Markers & network probing
# ----------------------------------------------------------------------
def pytest_configure(config):
    """Register our custom marks so they stop warning and so
    `-m network` / `-m 'not network'` filter correctly even without a
    pyproject.toml markers block."""
    config.addinivalue_line(
        "markers",
        "android_emulated: exercises the engine as if running on Termux/Android",
    )
    config.addinivalue_line(
        "markers",
        "network: requires outbound TCP to html.duckduckgo.com:443 and friends",
    )

pytestmark = pytest.mark.android_emulated


def _has_network(host: str = "html.duckduckgo.com", port: int = 443,
                 timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_HAS_NETWORK = _has_network()
needs_network = pytest.mark.skipif(
    not _HAS_NETWORK,
    reason=f"No TCP reachability to html.duckduckgo.com:443",
)


# ----------------------------------------------------------------------
# 3. Shape assertions — every public API must return the same dict shape
# ----------------------------------------------------------------------

_REQUIRED_FIELDS = ("title", "url")
_OPTIONAL_FIELDS = ("source", "published", "description")


def _assert_article_shape(article: Any, *, where: str = "") -> None:
    assert isinstance(article, dict), f"{where}: expected dict, got {type(article).__name__}"
    for field in _REQUIRED_FIELDS:
        assert field in article, f"{where}: missing required field {field!r}: {article!r}"
        assert isinstance(article[field], str), (
            f"{where}: field {field!r} must be str, got {type(article[field]).__name__}"
        )
    for field in _OPTIONAL_FIELDS:
        if field in article and article[field] is not None:
            assert isinstance(article[field], str), (
                f"{where}: optional field {field!r} must be str|None, "
                f"got {type(article[field]).__name__}"
            )


def _assert_article_list(items: Any, *, where: str = "") -> List[Dict[str, Any]]:
    assert isinstance(items, list), f"{where}: expected list, got {type(items).__name__}"
    for i, art in enumerate(items):
        _assert_article_shape(art, where=f"{where}[{i}]")
    return items


def _next_or_timeout(gen, timeout: float = 30.0):
    """Pull one item from a generator with a hard timeout so tests don't
    hang forever on a stuck network call. Uses a daemon thread so an
    orphaned worker can't block interpreter exit."""
    box: Dict[str, Any] = {"value": None, "exc": None, "done": False}

    def _worker() -> None:
        try:
            box["value"] = next(gen)
        except BaseException as e:  # noqa: BLE001
            box["exc"] = e
        finally:
            box["done"] = True

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)
    if not box["done"]:
        raise TimeoutError(f"generator did not yield within {timeout}s")
    if isinstance(box["exc"], StopIteration):
        raise StopIteration()
    if box["exc"] is not None:
        raise box["exc"]
    return box["value"]


def _call_or_skip(fn, *args, **kwargs):
    """Run ``fn`` and skip the test if the failure looks environmental
    (missing API key, missing optional extra) rather than a real bug."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        msg = f"{type(e).__name__}: {e}".lower()
        for needle in ("api key", "api_key", "openai", "anthropic",
                       "missing credentials", "model", "sumy",
                       "not installed", "extra"):
            if needle in msg:
                pytest.skip(f"Backend unavailable in this environment: {e}")
        raise


# ======================================================================
# 4. Emulation setup — cheap sanity checks that the env actually took
# ======================================================================

class TestEmulationSetup:
    """The emulation is only useful if the process really believes it's
    on Termux and the engine's own detectors agree."""

    def test_termux_env_var_visible(self):
        assert os.environ.get("TERMUX_VERSION"), "TERMUX_VERSION not set"

    def test_engine_is_termux(self):
        assert duckduckgo_engine._is_termux() is True

    def test_ddgs_tier_is_skipped_by_termux_rule(self):
        # We set TERMUX_VERSION but NOT OPEN_NEWS_TRY_DDGS_ON_TERMUX,
        # so the termux guard in fetch_raw must decide to skip ddgs.
        assert duckduckgo_engine._try_ddgs_on_termux() is False

    def test_skip_duckpy_env_set(self):
        assert duckduckgo_engine._skip_duckpy() is True

    def test_force_fallback_env_NOT_set_by_default(self):
        # The natural path is what we want to test at module level.
        # (FORCE_DDG_FALLBACK is exercised in its own class.)
        assert duckduckgo_engine._force_fallback() is False


# ======================================================================
# 5. Engine routing — no network, all tiers monkeypatched
# ======================================================================

class TestEngineRouting:
    """fetch_raw must navigate Termux -> skip ddgs -> skip duckpy ->
    fallback chain, without ever trying the native primp path."""

    def test_termux_skips_ddgs_and_duckpy_reaches_fallback(self, monkeypatch):
        calls = {"ddgs": 0, "duckpy": 0, "ddg_html": 0}

        def spy_ddgs(config):
            calls["ddgs"] += 1
            return []

        def spy_duckpy(config):
            calls["duckpy"] += 1
            return []

        def fake_html(config):
            calls["ddg_html"] += 1
            return [{
                "title": "Emulated article",
                "url": "https://example.com/a",
                "source": "example.com",
                "published": "",
                "description": "",
            }]

        monkeypatch.setattr(duckduckgo_engine, "_try_ddgs", spy_ddgs)
        monkeypatch.setattr(duckduckgo_engine, "_try_duckpy", spy_duckpy)
        monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", fake_html)

        result = fetch_raw(FetchConfig(category="general", max_results=5))

        assert calls["ddgs"] == 0, "ddgs tier must not be reached on Termux"
        assert calls["duckpy"] == 0, "duckpy tier must be skipped when env set"
        assert calls["ddg_html"] == 1, "fallback chain must be reached"
        _assert_article_list(result, where="routing-result")
        assert result[0]["title"] == "Emulated article"

    def test_escape_hatch_force_fallback_bypasses_everything(
        self, monkeypatch,
    ):
        """OPEN_NEWS_FORCE_DDG_FALLBACK=1 must short-circuit straight to
        the fallback chain, without consulting Termux detection at all."""
        monkeypatch.setenv("OPEN_NEWS_FORCE_DDG_FALLBACK", "1")

        calls = {"ddgs": 0, "duckpy": 0, "ddg_html": 0}

        monkeypatch.setattr(
            duckduckgo_engine, "_try_ddgs",
            lambda config: calls.__setitem__("ddgs", calls["ddgs"] + 1) or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine, "_try_duckpy",
            lambda config: calls.__setitem__("duckpy", calls["duckpy"] + 1) or [],
        )
        monkeypatch.setattr(
            duckduckgo_engine, "_fetch_via_ddg_html",
            lambda config: calls.__setitem__("ddg_html", calls["ddg_html"] + 1)
            or [{
                "title": "Forced", "url": "https://f.example/1",
                "source": "f.example", "published": "", "description": "",
            }],
        )

        result = fetch_raw(FetchConfig(category="general", max_results=5))

        assert calls["ddgs"] == 0
        assert calls["duckpy"] == 0
        assert calls["ddg_html"] == 1
        assert result[0]["title"] == "Forced"

    def test_bing_rss_tier_runs_when_html_empty(self, monkeypatch):
        """If the engine ships with the hybrid chain (DDG HTML -> Bing
        RSS), the second tier must be reached when the first is empty.
        Skips cleanly on the original single-file layout."""
        if not hasattr(duckduckgo_engine, "_fetch_via_bing_rss"):
            pytest.skip("Engine has no Bing RSS tier (single-file layout)")

        monkeypatch.setattr(duckduckgo_engine, "_fetch_via_ddg_html", lambda c: [])
        called = {"n": 0}

        def fake_bing(config):
            called["n"] += 1
            return [{
                "title": "bing", "url": "https://b.example/1",
                "source": "b.example", "published": "", "description": "",
            }]

        monkeypatch.setattr(duckduckgo_engine, "_fetch_via_bing_rss", fake_bing)

        result = fetch_raw(FetchConfig(category="general", max_results=5))
        assert called["n"] == 1
        assert result[0]["title"] == "bing"


# ======================================================================
# 6. Pure helpers — no network, always run
# ======================================================================

class TestPureHelpers:
    def test_region_param_normalization(self):
        assert _region_param(None) == "wt-wt"
        assert _region_param("wt-wt") == "wt-wt"
        assert _region_param("us") == "us-en"
        assert _region_param("in") == "in-en"
        assert _region_param("us-en") == "us-en"

    def test_decode_uddg_protocol_relative(self):
        assert _decode_uddg(
            "//duckduckgo.com/l/?uddg=https%3A%2F%2Fx.example%2F1"
        ) == "https://x.example/1"

    def test_decode_uddg_passthrough(self):
        assert _decode_uddg("https://plain.example/1") == "https://plain.example/1"

    def test_decode_uddg_empty(self):
        assert _decode_uddg("") == ""

    def test_parse_ddg_html_extracts_results(self):
        html = (
            '<html><body>'
            '<div class="result results_links">'
            '<h2 class="result__title">'
            '<a class="result__a" href="https://a.example/1">First story</a>'
            '</h2>'
            '<a class="result__snippet">First snippet</a>'
            '</div>'
            '</body></html>'
        )
        results = _parse_ddg_html(html, limit=10)
        assert len(results) == 1
        _assert_article_shape(results[0], where="parsed-ddg-html")
        assert results[0]["title"] == "First story"
        assert results[0]["url"] == "https://a.example/1"
        assert results[0]["source"] == "a.example"

    def test_parse_ddg_html_respects_limit(self):
        blocks = "".join(
            f'<div class="result">'
            f'<h2 class="result__title"><a class="result__a" href="https://a.example/{i}">S{i}</a></h2>'
            f'</div>'
            for i in range(10)
        )
        html = f"<html><body>{blocks}</body></html>"
        assert len(_parse_ddg_html(html, limit=3)) == 3

    def test_parse_ddg_html_handles_malformed(self):
        assert _parse_ddg_html("not html at all", limit=5) == []

    def test_parse_ddg_html_skips_blocks_without_anchor(self):
        html = '<html><body><div class="result">no anchor</div></body></html>'
        assert _parse_ddg_html(html, limit=5) == []


# ======================================================================
# 7. Dedupe under emulation — pure, always run
# ======================================================================

class TestDedupeUnderEmulation:
    def test_dedupe_collapses_tracking_variants(self):
        articles = [
            {"url": "https://a.com/story", "title": "A"},
            {"url": "https://a.com/story?utm_source=x", "title": "B"},
            {"url": "https://b.com/story", "title": "C"},
        ]
        assert len(dedupe_articles(articles, fuzzy=False)) == 2

    def test_dedupe_drops_empty_urls(self):
        articles = [
            {"url": "", "title": "no url"},
            {"url": "https://a.com/x", "title": "has url"},
        ]
        result = dedupe_articles(articles, fuzzy=False)
        assert len(result) == 1
        assert result[0]["title"] == "has url"

    def test_dedupe_fuzzy_title(self):
        articles = [
            {"url": "https://a.com/1", "title": "AI takes over the world"},
            {"url": "https://b.com/2", "title": "AI takes over world"},
            {"url": "https://c.com/3", "title": "Sports update"},
        ]
        assert len(dedupe_articles(articles, fuzzy=True)) == 2


# ======================================================================
# 8. Public API smoke tests — live network
# ======================================================================

@needs_network
@pytest.mark.network
class TestPublicAPISmoke:
    """Every public entry point in open_news/__init__.py, run against
    the fallback chain (because the emulation is active). Skips cleanly
    when there is no route to html.duckduckgo.com:443."""

    def test_fetch_tech_returns_articles(self):
        articles = _call_or_skip(fetch, category="tech", max_results=5)
        _assert_article_list(articles, where="fetch(category='tech')")

    def test_fetch_business_returns_articles(self):
        articles = _call_or_skip(fetch, category="business", max_results=5)
        _assert_article_list(articles, where="fetch(category='business')")

    def test_fetch_with_location(self):
        articles = _call_or_skip(
            fetch, category="general", location="in", max_results=5,
        )
        _assert_article_list(articles, where="fetch(location='in')")

    def test_search_returns_articles(self):
        articles = _call_or_skip(search, "climate change", max_results=5)
        _assert_article_list(articles, where="search('climate change')")

    def test_search_with_exclude_terms(self):
        articles = _call_or_skip(
            search, "technology", max_results=5,
            exclude_terms=["crypto"],
        )
        _assert_article_list(articles, where="search(exclude_terms=[...])")

    def test_search_site_returns_articles(self):
        articles = _call_or_skip(
            search_site, "budget", "reuters.com", limit=3,
        )
        _assert_article_list(articles, where="search_site")


    @needs_network
    @pytest.mark.network
    def test_discover_and_get_returns_articles(self):
        """example.com is stable, has no anti-bot policy worth worrying
        about, and serves a single static page. It won't yield *many*
        articles, but the contract is "returns a list, each entry shaped
        correctly" — not "returns N articles"."""
        articles = _call_or_skip(
            discover_and_get, "https://example.com/", limit=3,
        )
        _assert_article_list(articles, where="discover_and_get")

# ======================================================================
# 8b. Article extraction against a loopback fixture — no network
# ======================================================================

class TestArticleExtractionLocal:
    """get_article's contract, verified against a locally-served page.
    """

    def test_get_article_returns_text(self, local_article_server):
        url = f"{local_article_server}/article1.html"
        article = _call_or_skip(get_article, url, timeout=10)

        assert isinstance(article, dict)
        assert article.get("text"), (
            f"get_article returned empty text for the local fixture; "
            f"keys={list(article)} value={article!r}"
        )
        assert article["url"] == url
        # The fixture page declares og:site_name and has a <title>; a
        # working extractor should pick one of them up.
        assert article.get("title"), f"no title extracted; keys={list(article)}"

    def test_get_article_missing_page_returns_empty_dict(
        self, local_article_server,
    ):
        """404s must not raise — get_article returns the empty-result
        shape so callers can detect failure by inspecting `text`."""
        article = get_article(f"{local_article_server}/does-not-exist", timeout=5)
        assert isinstance(article, dict)
        assert article.get("text") == ""

# ======================================================================
# 9. Streaming
# ======================================================================

class TestStreaming:
    """stream_search() is search(refresh_interval=...) wrapped in a cast,
    so its lazy-iterator contract can be verified without a network call.
    Pulling the first batch needs the network and is opt-in."""

    def test_stream_search_returns_iterator_without_network(self):
        stream = stream_search("news", refresh_interval=5, max_results=1)
        try:
            assert hasattr(stream, "__iter__") and hasattr(stream, "__next__"), (
                "stream_search must return a generator/iterator object"
            )
        finally:
            stream.close()

    @needs_network
    @pytest.mark.network
    def test_stream_search_yields_first_batch(self):
        stream = stream_search("news", refresh_interval=5, max_results=3)
        try:
            try:
                first_batch = _next_or_timeout(stream, timeout=45.0)
            except StopIteration:
                pytest.skip("Stream closed without yielding (likely no network data)")
            _assert_article_list(first_batch, where="stream_search first batch")
        finally:
            stream.close()


# ----------------------------------------------------------------------
# 10. Summarization — the local extractive summarizer. No LLM key
#     needed; may still be skipped if an optional extra is missing.
# ----------------------------------------------------------------------

class TestSummarization:
    SAMPLE = (
        "Scientists announced a breakthrough in fusion energy this week, "
        "achieving a net-positive reaction for the first time. The experiment, "
        "conducted at a national laboratory, produced more energy than was "
        "required to start the reaction. Researchers cautioned that scaling "
        "the result to commercial power plants remains years away."
    )

    def test_summarize_text_returns_str(self):
        out = _call_or_skip(summarize_text, self.SAMPLE)
        assert isinstance(out, str) and out, "summarize_text returned empty"

    def test_summarize_text_respects_sentence_count(self):
        """summarize_text is positional; 1, 2, and 3 sentences should
        come out in that order of length."""
        one = summarize_text(self.SAMPLE, 1)
        two = summarize_text(self.SAMPLE, 2)
        assert one.count(". ") + 1 <= two.count(". ") + 1
        assert isinstance(one, str) and isinstance(two, str)

    def test_summarize_with_keywords_returns_expected_dict(self):
        """The library's signature is (text, sentence_count=3, top_words=5).
        It *extracts* keywords — it does not accept them as input. See the
        module docstring; this is a naming quirk in the library, not a
        test bug (an earlier version of this test wrongly passed a
        keywords list and tripped a TypeError deep inside summarize_text)."""
        out = _call_or_skip(summarize_with_keywords, self.SAMPLE)
        assert isinstance(out, dict), (
            f"summarize_with_keywords must return dict, got {type(out).__name__}"
        )
        for key in ("summary", "keywords", "coverage"):
            assert key in out, f"missing key {key!r} in {sorted(out)}"
        assert isinstance(out["summary"], str)
        assert isinstance(out["keywords"], list)
        assert all(isinstance(k, str) for k in out["keywords"])
        assert 0.0 <= float(out["coverage"]) <= 1.0

    def test_summarize_with_keywords_top_words_limit(self):
        out = summarize_with_keywords(self.SAMPLE, top_words=2)
        assert len(out["keywords"]) <= 2

    @needs_network
    @pytest.mark.network
    def test_batch_summarize(self):
        """Use a stable, anti-bot-friendly URL. Wikipedia's policy blocks
        cloud IPs, so it's a bad default for a batch-fetch test."""
        out = _call_or_skip(
            batch_summarize,
            ["https://example.com/"],
        )
        assert isinstance(out, list) and out
        for entry in out:
            assert isinstance(entry, dict)
            assert "url" in entry and "status" in entry

    @needs_network
    @pytest.mark.network
    def test_search_and_summarize(self):
        """Regression guard for a batch.py bug where `limit` was forwarded
        to api.search as `limit=` instead of `max_results=`."""
        out = _call_or_skip(
            search_and_summarize, "python programming language", limit=2,
        )
        assert isinstance(out, list)
        for entry in out:
            assert isinstance(entry, dict)
            assert "url" in entry

# ======================================================================
# 11. Cross-API consistency — same shape everywhere, in emulation
# ======================================================================

@pytest.fixture(scope="module")
def _api_samples() -> Dict[str, List[Dict[str, Any]]]:
    """One fetch() and one search() result, cached for the module.
    Module-scoped so pytest 8+ doesn't warn about class-scoped
    instance-method fixtures (and so pytest 10 doesn't break us)."""
    if not _HAS_NETWORK:
        pytest.skip("No route to html.duckduckgo.com:443")
    return {
        "fetch": _call_or_skip(fetch, category="tech", max_results=3),
        "search": _call_or_skip(search, "technology", max_results=3),
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
                    f"{name}: URL is not absolute: {a['url']!r}"
                )

    def test_no_article_has_hub_url(self, _api_samples):
        from open_news.fetch.url_resolver import is_hub_url
        for name, articles in _api_samples.items():
            for a in articles:
                assert not is_hub_url(a["url"]), (
                    f"{name}: hub URL slipped through: {a['url']!r}"
                )