"""Tests for open_news.feeds.yahoonews_engine.

No live network: HTTP is mocked, HTML is fed via fixture.
"""

from typing import Any, Dict
from urllib.parse import quote_plus

import httpx
import pytest

from open_news.config import FetchConfig
from open_news.feeds import yahoonews_engine


# ----------------------------------------------------------------------
# Fake HTTP client
# ----------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=self,  # type: ignore[arg-type]
            )


class _FakeClient:
    def __init__(self, response):
        self._response = response
        self.last_url = None
        self.last_kwargs = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, **kwargs):
        self.last_url = url
        self.last_kwargs = kwargs
        return self._response


def _patch_http(monkeypatch, text="", status_code=200):
    response = _FakeResponse(text=text, status_code=status_code)
    client_holder: Dict[str, Any] = {}

    def fake_make(**kwargs):
        c = _FakeClient(response)
        client_holder["client"] = c
        return c

    monkeypatch.setattr(yahoonews_engine, "make_client", fake_make)
    return client_holder


# ----------------------------------------------------------------------
# Query construction
# ----------------------------------------------------------------------

class TestQueryBuilding:

    def test_category_only(self):
        q = yahoonews_engine._query_for(FetchConfig(category="tech", max_results=1))
        assert "technology" in q.lower()

    def test_category_and_location(self):
        q = yahoonews_engine._query_for(
            FetchConfig(category="general", location="in", max_results=1),
        )
        assert "India" in q

    def test_wt_wt_treated_as_absent(self):
        q = yahoonews_engine._query_for(
            FetchConfig(category="general", location="wt-wt", max_results=1),
        )
        assert "WT" not in q


# ----------------------------------------------------------------------
# URL unwrapping (Yahoo redirect form)
# ----------------------------------------------------------------------

class TestURLUnwrapping:

    def test_unwraps_ru_segment(self):
        wrapped = (
            "https://news.search.yahoo.com/redirect"
            "/RU=" + quote_plus("https://real.example.com/story")
            + "/RK=2/RS=abc"
        )
        assert yahoonews_engine._unwrap_yahoo_url(wrapped) == "https://real.example.com/story"

    def test_passthrough_when_not_wrapped(self):
        direct = "https://real.example.com/story"
        assert yahoonews_engine._unwrap_yahoo_url(direct) == direct

    def test_handles_empty(self):
        assert yahoonews_engine._unwrap_yahoo_url("") == ""

    def test_strips_query_params_after_rk(self):
        wrapped = (
            "https://news.search.yahoo.com/redirect"
            "/RU=" + quote_plus("https://real.example.com/story")
            + "/RK=2/RS=abc?utm_source=yahoo"
        )
        assert yahoonews_engine._unwrap_yahoo_url(wrapped) == "https://real.example.com/story"


# ----------------------------------------------------------------------
# Relative date parsing
# ----------------------------------------------------------------------

class TestRelativeDate:

    def test_hours_ago(self):
        result = yahoonews_engine._parse_relative_date("2 hours ago")
        assert "T" in result
        assert result.endswith("+00:00") or result.endswith("Z")

    def test_days_ago(self):
        result = yahoonews_engine._parse_relative_date("3 days ago")
        assert "T" in result

    def test_minutes_ago(self):
        result = yahoonews_engine._parse_relative_date("15 minutes ago")
        assert "T" in result

    def test_weeks_and_months(self):
        for s in ("1 week ago", "2 months ago", "1 year ago"):
            assert "T" in yahoonews_engine._parse_relative_date(s)

    def test_unparseable_returned_as_is(self):
        assert yahoonews_engine._parse_relative_date("sometime") == "sometime"

    def test_empty_returns_empty(self):
        assert yahoonews_engine._parse_relative_date("") == ""


# ----------------------------------------------------------------------
# HTML parsing
# ----------------------------------------------------------------------

# Yahoo wraps every link, so the fixture must too.
_RU = quote_plus("https://thehindu.com/news/123")
_RU2 = quote_plus("https://economictimes.indiatimes.com/markets/456")

_YAHOO_HTML_FIXTURE = f"""
<html><body>
  <div id="web">
    <ol>
      <li>
        <h4><a href="https://news.search.yahoo.com/redirect/RU={_RU}/RK=2/RS=abc">Monsoon session ends</a></h4>
        <p>Parliament passes three key bills.</p>
        <span class="time">2 hours ago</span>
        <span class="source">The Hindu ·  via Yahoo</span>
      </li>
      <li>
        <h4><a href="https://news.search.yahoo.com/redirect/RU={_RU2}/RK=2/RS=def">Sensex jumps 400 points</a></h4>
        <p>IT stocks rally on strong earnings.</p>
        <span class="time">30 minutes ago</span>
        <span class="source">Economic Times ·  via Yahoo</span>
      </li>
    </ol>
  </div>
</body></html>
"""


class TestHTMLParsing:

    def test_extracts_title_url_source(self):
        results = yahoonews_engine._parse_yahoo_html(_YAHOO_HTML_FIXTURE, limit=10)
        assert len(results) == 2
        assert results[0]["title"] == "Monsoon session ends"
        assert results[0]["url"] == "https://thehindu.com/news/123"
        assert results[0]["source"] == "The Hindu"

    def test_url_is_unwrapped(self):
        results = yahoonews_engine._parse_yahoo_html(_YAHOO_HTML_FIXTURE, limit=10)
        for r in results:
            assert "/RU=" not in r["url"], f"URL not unwrapped: {r['url']!r}"
            assert r["url"].startswith("https://")

    def test_source_suffix_stripped(self):
        results = yahoonews_engine._parse_yahoo_html(_YAHOO_HTML_FIXTURE, limit=10)
        for r in results:
            assert "via Yahoo" not in r["source"]

    def test_dates_are_iso(self):
        results = yahoonews_engine._parse_yahoo_html(_YAHOO_HTML_FIXTURE, limit=10)
        for r in results:
            assert "T" in r["published"]

    def test_respects_limit(self):
        results = yahoonews_engine._parse_yahoo_html(_YAHOO_HTML_FIXTURE, limit=1)
        assert len(results) == 1

    def test_drops_hub_urls(self):
        ru_hub = quote_plus("https://apnews.com/hub/technology")
        ru_real = quote_plus("https://apnews.com/article/xyz")
        html = f"""
        <html><body><div id="web"><ol>
          <li><h4><a href="https://news.search.yahoo.com/redirect/RU={ru_hub}/RK=2/RS=a">Hub</a></h4></li>
          <li><h4><a href="https://news.search.yahoo.com/redirect/RU={ru_real}/RK=2/RS=b">Article</a></h4></li>
        </ol></div></body></html>
        """
        results = yahoonews_engine._parse_yahoo_html(html, limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Article"

    def test_drops_bare_domain_urls(self):
        ru_home = quote_plus("https://example.com/")
        ru_art = quote_plus("https://example.com/article/1")
        html = f"""
        <html><body><div id="web"><ol>
          <li><h4><a href="https://news.search.yahoo.com/redirect/RU={ru_home}/RK=2/RS=a">Home</a></h4></li>
          <li><h4><a href="https://news.search.yahoo.com/redirect/RU={ru_art}/RK=2/RS=b">Art</a></h4></li>
        </ol></div></body></html>
        """
        results = yahoonews_engine._parse_yahoo_html(html, limit=10)
        assert len(results) == 1
        assert results[0]["title"] == "Art"

    def test_empty_html(self):
        assert yahoonews_engine._parse_yahoo_html("", limit=10) == []

    def test_garbage_html(self):
        assert yahoonews_engine._parse_yahoo_html("not html", limit=10) == []


# ----------------------------------------------------------------------
# fetch_raw
# ----------------------------------------------------------------------

class TestFetchRaw:

    def test_skip_env_returns_empty(self, monkeypatch):
        monkeypatch.setenv("OPEN_NEWS_SKIP_YAHOO_NEWS", "1")
        holder = _patch_http(monkeypatch, text="")
        result = yahoonews_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert result == []
        assert "client" not in holder  # HTTP never attempted

    def test_successful_fetch(self, monkeypatch):
        _patch_http(monkeypatch, text=_YAHOO_HTML_FIXTURE)
        result = yahoonews_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert len(result) == 2
        assert result[0]["title"] == "Monsoon session ends"

    def test_http_failure_returns_empty(self, monkeypatch):
        _patch_http(monkeypatch, text="", status_code=500)
        result = yahoonews_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert result == []

    def test_time_limit_forwarded(self, monkeypatch):
        holder = _patch_http(monkeypatch, text=_YAHOO_HTML_FIXTURE)
        yahoonews_engine.fetch_raw(
            FetchConfig(category="general", time_limit="w", max_results=5),
        )
        assert holder["client"].last_kwargs["params"]["btf"] == "w"