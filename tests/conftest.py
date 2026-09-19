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
import http.server
import threading


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

@pytest.fixture
def local_article_server():
    """Serve a small static site on loopback so tests that fetch real
    articles can do so without leaving the machine.

    Motivation: GitHub Actions runners sit on AWS IP ranges that
    Wikipedia (and many other sites) block with 403 regardless of the
    User-Agent header. A live external URL therefore makes any
    "did we extract text?" assertion flaky for reasons unrelated to
    open_news. A loopback fixture removes that variable entirely.

    Routes:
        /                 — homepage with links to the two articles
        /article1.html    — full article page (title + og:site_name + body)
        /article2.html    — second article, shorter body
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
            "<p>The third paragraph is included for good measure and to "
            "push the total text length above the thresholds that "
            "extractors commonly use to distinguish an article from a "
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
            "tests. It has one meaningful paragraph, which is enough to "
            "satisfy shape assertions without duplicating the first "
            "article's content.</p>"
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