"""Shared pytest configuration.

Contains:

* ``pytest_configure`` — registers the custom markers used across the
  suite. This hook must live at pytest's plugin-loading layer
  (i.e. ``conftest.py``), not inside a ``test_*.py`` module: pytest
  fires ``pytest_configure`` during startup, before test modules are
  imported, so a hook defined in a test file registers too late.

* ``_emulate_android`` — autouse fixture that sets the Termux emulation
  env vars for any test marked ``android_emulated``, and restores them
  afterwards. Replaces the previous module-level ``os.environ.setdefault``
  block in the emulated test file, which leaked TERMUX_VERSION into every
  test in the same pytest session.

* ``local_article_server`` — loopback HTTP server used by tests that
  fetch a real URL, so they never depend on any external site being
  reachable (GitHub Actions runners get 403'd by Wikipedia and many
  others regardless of User-Agent).

* ``sample_article_dict`` / ``sample_articles_list`` — small fixtures
  used by dedupe / pipeline tests.
"""

import http.server
import threading

import pytest


# ----------------------------------------------------------------------
# Marker registration
# ----------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "android_emulated: exercises the fetch() chain as if running on "
        "Termux/Android — ddgs tier skipped, all other tiers active.",
    )
    config.addinivalue_line(
        "markers",
        "network: requires outbound TCP to news.google.com:443 and similar; "
        "auto-skipped when offline.",
    )
    config.addinivalue_line(
        "markers",
        "native: requires the real 'ddgs' package (pip install ddgs); "
        "skipped automatically when it is not importable.",
    )


# ----------------------------------------------------------------------
# Android / Termux emulation
# ----------------------------------------------------------------------

# Every env var the engines consult. The fixture below restores any
# pre-existing values after the test, so a stray TERMUX_VERSION in the
# developer's shell doesn't leak out and a test file's own env changes
# don't leak into the next file.

_ANDROID_EMULATION_ENV = {
    # Presence of this triggers duckduckgo_engine._is_termux() -> True.
    "TERMUX_VERSION": "0.118.0",
}

# Escape hatches that must be *unset* for the natural chain order to
# apply. If a developer's shell has these exported, we clear them for
# the duration of the emulated test.
_ANDROID_EMULATION_CLEAR = (
    "OPEN_NEWS_TRY_DDGS_ON_TERMUX",
    "OPEN_NEWS_SKIP_DDGS",
    "OPEN_NEWS_SKIP_GOOGLE_NEWS",
    "OPEN_NEWS_SKIP_BING_NEWS",
    "OPEN_NEWS_SKIP_YAHOO_NEWS",
    "OPEN_NEWS_SKIP_DDG_HTML",
)


@pytest.fixture(autouse=True)
def _emulate_android(request, monkeypatch):
    """Set (and restore) the Termux emulation env vars for tests marked
    ``android_emulated``. Non-emulated tests are unaffected.

    Using monkeypatch means each test starts from a clean slate and the
    environment is exactly what it was before the test when it ends —
    no cross-file pollution, no surprise for the next test in the
    session.
    """
    if not request.node.get_closest_marker("android_emulated"):
        return

    for k, v in _ANDROID_EMULATION_ENV.items():
        monkeypatch.setenv(k, v)
    for k in _ANDROID_EMULATION_CLEAR:
        monkeypatch.delenv(k, raising=False)


# ----------------------------------------------------------------------
# Loopback article fixture
# ----------------------------------------------------------------------

@pytest.fixture
def local_article_server():
    """Serve a small static site on loopback.

    Motivation: get_article's contract is "extract text from a URL". Any
    test that pins an external URL is really testing the runner's IP
    reputation, not the library. This fixture makes those tests
    deterministic and offline-capable.

    Routes:
        /                 — homepage with links to two articles
        /article1.html    — full article (title + og:site_name + body)
        /article2.html    — shorter second article
        anything else     — 404, so RSS auto-discovery falls through to
                            the crawler path in discover_and_get()
    """
    pages = {
        "/": (
            "<!doctype html><html><head><title>Local Fixture Index</title></head>"
            "<body><h1>Index</h1>"
            '<a href="/article1.html">First local article</a>'
            '<a href="/article2.html">Second local article</a>'
            "</body></html>"
        ).encode("utf-8"),
        "/article1.html": (
            "<!doctype html><html><head>"
            "<title>Local Fixture Article One</title>"
            '<meta property="og:site_name" content="Local Fixture">'
            '<meta name="author" content="Fixture Author">'
            "</head><body><article>"
            "<h1>Local Fixture Article One</h1>"
            "<p>This is the first paragraph of the locally served article. "
            "It contains enough words for a readability-style extractor to "
            "recognise it as real body text rather than navigation or "
            "boilerplate.</p>"
            "<p>This is the second paragraph. It exists so the extractor "
            "has more than one candidate and can score them against each "
            "other, which is what most article-extraction algorithms want "
            "before they commit to a body.</p>"
            "<p>The third paragraph pushes the total text length above the "
            "thresholds extractors use to distinguish an article from a "
            "listing page or an error page.</p>"
            "</article></body></html>"
        ).encode("utf-8"),
        "/article2.html": (
            "<!doctype html><html><head>"
            "<title>Local Fixture Article Two</title>"
            '<meta property="og:site_name" content="Local Fixture">'
            "</head><body><article>"
            "<h1>Local Fixture Article Two</h1>"
            "<p>A shorter second article used for batch and multi-article "
            "tests. One meaningful paragraph is enough to satisfy shape "
            "assertions without duplicating the first article's content.</p>"
            "</article></body></html>"
        ).encode("utf-8"),
    }

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            body = pages.get(path)
            if body is None:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args, **kwargs):
            pass  # silence the default stderr chatter

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


# ----------------------------------------------------------------------
# Sample data fixtures
# ----------------------------------------------------------------------

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
        {**sample_article_dict, "title": "AI takes over the world",
         "url": "https://a.com/1"},
        {**sample_article_dict, "title": "AI takes over the world update",
         "url": "https://b.com/2"},
        {**sample_article_dict, "title": "Different story",
         "url": "https://c.com/3"},
    ]


# ----------------------------------------------------------------------
# Native (ddgs) availability probe
# ----------------------------------------------------------------------

def pytest_collection_modifyitems(config, items):
    """Skip tests marked ``native`` when ddgs isn't importable.

    Doing this at collection time rather than via a fixture keeps the
    skip visible up front (pytest prints "s" for these in -v output)
    instead of erroring inside a test body.
    """
    try:
        import ddgs  # noqa: F401
        has_ddgs = True
    except ImportError:
        try:
            import duckduckgo_search  # noqa: F401
            has_ddgs = True
        except ImportError:
            has_ddgs = False

    if has_ddgs:
        return

    skip_native = pytest.mark.skip(reason="ddgs not installed")
    for item in items:
        if item.get_closest_marker("native"):
            item.add_marker(skip_native)