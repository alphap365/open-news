"""Tests for open_news.feeds.bingnews_engine.

No live network: HTTP is mocked via a fake make_client, and the parsers
are fed fixture HTML / XML directly.
"""

from typing import Any, Dict, Optional

import httpx
import pytest

from open_news.config import FetchConfig
from open_news.feeds import bingnews_engine


# ----------------------------------------------------------------------
# Fake HTTP client
# ----------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.content = text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=None,  # type: ignore[arg-type]
                response=self,  # type: ignore[arg-type]
            )


class _FakeClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, *args, **kwargs):
        return self._response

    def post(self, *args, **kwargs):
        return self._response


def _patch_http(monkeypatch, text="", status_code=200):
    """Patch bingnews_engine.make_client so every request returns a fake
    response with the given body. Returns a dict that records the last
    call's URL and kwargs."""
    calls: Dict[str, Any] = {"url": None, "kwargs": None}

    response = _FakeResponse(text=text, status_code=status_code)

    def fake_make(**kwargs):
        return _FakeClient(response)

    def fake_get(self, url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return response

    _FakeClient.get = fake_get  # type: ignore[assignment]
    monkeypatch.setattr(bingnews_engine, "make_client", fake_make)
    return calls


# ----------------------------------------------------------------------
# Query construction
# ----------------------------------------------------------------------

class TestQueryBuilding:

    def test_category_only(self):
        assert "technology" in bingnews_engine._query_for(
            FetchConfig(category="tech", max_results=1),
        ).lower()

    def test_category_and_location(self):
        q = bingnews_engine._query_for(
            FetchConfig(category="general", location="in", max_results=1),
        )
        assert "India" in q
        assert "breaking news" in q.lower()

    def test_unknown_location_passes_iso_code(self):
        q = bingnews_engine._query_for(
            FetchConfig(category="general", location="zw", max_results=1),
        )
        assert "ZW" in q

    def test_wt_wt_treated_as_absent(self):
        q = bingnews_engine._query_for(
            FetchConfig(category="general", location="wt-wt", max_results=1),
        )
        assert "WT" not in q

    def test_country_lang_parsing(self):
        assert bingnews_engine._country_lang("in-en") == ("in", "en")
        assert bingnews_engine._country_lang("us") == ("us", "en")
        assert bingnews_engine._country_lang(None) == ("us", "en")
        assert bingnews_engine._country_lang("wt-wt") == ("us", "en")


# ----------------------------------------------------------------------
# HTML tier — parsing
# ----------------------------------------------------------------------

_BING_HTML_FIXTURE = """
<html><body>
  <div class="newsitem"
       data-title="Monsoon session ends"
       data-author="The Hindu"
       url="https://thehindu.com/news/123">
    <span aria-label="2 days ago"></span>
    <div class="snippet">Parliament passes three key bills.</div>
  </div>
  <div class="newsitem"
       data-title="Sensex jumps 400 points"
       data-author=""
       url="https://economictimes.indiatimes.com/markets/456">
    <span aria-label="1 hour ago"></span>
    <div class="snippet">IT stocks rally on strong earnings.</div>
  </div>
</body></html>
"""


class TestHTMLParsing:

    def test_extracts_title_url_author(self):
        results = bingnews_engine._parse_html_results(_BING_HTML_FIXTURE, limit=10)
        assert len(results) == 2
        assert results[0]["title"] == "Monsoon session ends"
        assert results[0]["url"] == "https://thehindu.com/news/123"
        assert results[0]["source"] == "The Hindu"

    def test_relative_dates_normalized_to_iso(self):
        results = bingnews_engine._parse_html_results(_BING_HTML_FIXTURE, limit=10)
        # Both dates should be ISO-8601 with a timezone.
        for r in results:
            assert "T" in r["published"]
            assert "+" in r["published"] or "Z" in r["published"]

    def test_source_falls_back_to_domain(self):
        results = bingnews_engine._parse_html_results(_BING_HTML_FIXTURE, limit=10)
        # Second entry has no data-author.
        assert results[1]["source"] == "economictimes.indiatimes.com"

    def test_respects_limit(self):
        results = bingnews_engine._parse_html_results(_BING_HTML_FIXTURE, limit=1)
        assert len(results) == 1

    def test_empty_html_returns_empty_list(self):
        assert bingnews_engine._parse_html_results("", limit=10) == []

    def test_garbage_html_returns_empty_list(self):
        assert bingnews_engine._parse_html_results("not html", limit=10) == []

    def test_drops_hub_urls(self):
        html = """
        <html><body>
          <div class="newsitem"
               data-title="AP hub"
               data-author="AP"
               url="https://apnews.com/hub/technology"></div>
          <div class="newsitem"
               data-title="Real article"
               data-author="AP"
               url="https://apnews.com/article/xyz"></div>
        </body></html>
        """
        results = bingnews_engine._parse_html_results(html, limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Real article"

    def test_drops_homepage_urls(self):
        html = """
        <html><body>
          <div class="newsitem"
               data-title="Site front"
               data-author="Site"
               url="https://example.com/"></div>
          <div class="newsitem"
               data-title="Real"
               data-author="Site"
               url="https://example.com/article/1"></div>
        </body></html>
        """
        results = bingnews_engine._parse_html_results(html, limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Real"


# ----------------------------------------------------------------------
# RSS tier — parsing
# ----------------------------------------------------------------------

_BING_RSS_FIXTURE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Story One</title>
    <link>https://example.com/1</link>
    <pubDate>Fri, 19 Sep 2026 12:00:00 GMT</pubDate>
    <description>Body one</description>
    <Source>Example Outlet</Source>
  </item>
  <item>
    <title>Story Two</title>
    <link>https://example.com/2</link>
    <pubDate>Thu, 18 Sep 2026 08:00:00 GMT</pubDate>
    <description><![CDATA[<p>Body two</p>]]></description>
  </item>
</channel></rss>"""


class TestRSSParsing:

    def test_extracts_items(self):
        results = bingnews_engine._parse_rss_results(_BING_RSS_FIXTURE, limit=10)
        assert len(results) == 2
        assert results[0]["title"] == "Story One"
        assert results[0]["source"] == "Example Outlet"

    def test_dates_normalized_to_iso_utc(self):
        results = bingnews_engine._parse_rss_results(_BING_RSS_FIXTURE, limit=10)
        assert results[0]["published"].startswith("2026-09-19T12:00:00")
        assert "+00:00" in results[0]["published"] or results[0]["published"].endswith("Z")

    def test_description_html_stripped(self):
        results = bingnews_engine._parse_rss_results(_BING_RSS_FIXTURE, limit=10)
        assert "<p>" not in results[1]["description"]
        assert "Body two" in results[1]["description"]

    def test_source_falls_back_to_domain(self):
        results = bingnews_engine._parse_rss_results(_BING_RSS_FIXTURE, limit=10)
        assert results[1]["source"] == "example.com"

    def test_respects_limit(self):
        results = bingnews_engine._parse_rss_results(_BING_RSS_FIXTURE, limit=1)
        assert len(results) == 1

    def test_empty_xml_returns_empty_list(self):
        assert bingnews_engine._parse_rss_results("", limit=10) == []

    def test_garbage_returns_empty_list(self):
        assert bingnews_engine._parse_rss_results("not xml", limit=10) == []


# ----------------------------------------------------------------------
# fetch_raw orchestration
# ----------------------------------------------------------------------

class TestFetchOrchestration:

    def test_html_tier_wins_when_it_has_results(self, monkeypatch):
        monkeypatch.setattr(
            bingnews_engine, "_fetch_via_html",
            lambda c: [{"title": "html", "url": "https://h.example/1",
                        "source": "h", "published": "", "description": ""}],
        )
        called = {"rss": 0}

        def fake_rss(config):
            called["rss"] += 1
            return []
        monkeypatch.setattr(bingnews_engine, "_fetch_via_rss", fake_rss)

        result = bingnews_engine.fetch_raw(FetchConfig(category="general", max_results=5))
        assert result[0]["title"] == "html"
        assert called["rss"] == 0

    def test_rss_tier_runs_when_html_empty(self, monkeypatch):
        monkeypatch.setattr(bingnews_engine, "_fetch_via_html", lambda c: [])
        monkeypatch.setattr(
            bingnews_engine, "_fetch_via_rss",
            lambda c: [{"title": "rss", "url": "https://r.example/1",
                        "source": "r", "published": "", "description": ""}],
        )
        result = bingnews_engine.fetch_raw(FetchConfig(category="general", max_results=5))
        assert result[0]["title"] == "rss"

    def test_skip_env_returns_empty(self, monkeypatch):
        monkeypatch.setenv("OPEN_NEWS_SKIP_BING_NEWS", "1")

        def fail(config):
            raise AssertionError("Bing tier must not run when skipped")
        monkeypatch.setattr(bingnews_engine, "_fetch_via_html", fail)
        monkeypatch.setattr(bingnews_engine, "_fetch_via_rss", fail)

        assert bingnews_engine.fetch_raw(FetchConfig(category="general", max_results=5)) == []

    def test_html_failure_falls_through_to_rss(self, monkeypatch):
        # Simulate an HTTP 500 in the HTML tier.
        _patch_http(monkeypatch, text="", status_code=500)

        # Now patch RSS tier to succeed.
        monkeypatch.setattr(
            bingnews_engine, "_fetch_via_rss",
            lambda c: [{"title": "recovered", "url": "https://r.example/1",
                        "source": "r", "published": "", "description": ""}],
        )
        result = bingnews_engine.fetch_raw(FetchConfig(category="general", max_results=5))
        assert result[0]["title"] == "recovered"