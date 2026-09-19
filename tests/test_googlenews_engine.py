"""Tests for open_news.feeds.googlenews_engine.

No live network: feedparser is monkeypatched to return a fake Feed, and
the URL construction is verified by capturing the argument to
``feedparser.parse``.
"""

from typing import Any, Dict, List

import pytest

from open_news.config import FetchConfig, SearchConfig
from open_news.feeds import googlenews_engine


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

class _FakeFeed:
    def __init__(self, entries):
        self.entries = entries


def _install_fake_feed(monkeypatch, entries):
    """Install a fake feedparser.parse that records the URL and returns
    a feed with the given entries."""
    calls = {"url": None}

    def fake_parse(url):
        calls["url"] = url
        return _FakeFeed(entries)

    monkeypatch.setattr(googlenews_engine.feedparser, "parse", fake_parse)
    return calls


def _entry(
    title: str = "Test Story",
    link: str = "https://news.google.com/rss/articles/abc",
    published: str = "2026-09-19T00:00:00+00:00",
    summary: str = "A test summary.",
    source_title: str = "Example Source",
):
    return {
        "title": title,
        "link": link,
        "published": published,
        "summary": summary,
        "source": {"title": source_title} if source_title else {},
    }


# ----------------------------------------------------------------------
# search_raw — query building
# ----------------------------------------------------------------------

class TestSearchRawQuery:

    def test_query_mode_any_leaves_query_alone(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(query="climate change", query_mode="any", max_results=1),
        )
        assert "q=climate+change" in calls["url"]
        assert "AND" not in calls["url"]

    def test_query_mode_all_adds_AND(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(query="climate change", query_mode="all", max_results=1),
        )
        assert "climate+AND+change" in calls["url"]

    def test_query_mode_exact_phrase_quotes(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(query="climate change", query_mode="exact_phrase", max_results=1),
        )
        # quote_plus turns `"` into %22
        assert "%22climate+change%22" in calls["url"]

    def test_exclude_terms_prefixed_with_minus(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(
                query="tech", exclude_terms=["crypto", "nft"], max_results=1,
            ),
        )
        assert "-crypto" in calls["url"]
        assert "-nft" in calls["url"]

    def test_time_limit_maps_to_when_operator(self, monkeypatch):
        for tl, expected in [("d", "1d"), ("w", "7d"), ("m", "30d")]:
            calls = _install_fake_feed(monkeypatch, [])
            googlenews_engine.search_raw(
                SearchConfig(query="tech", time_limit=tl, max_results=1),
            )
            assert f"when%3A{expected}" in calls["url"], (
                f"time_limit={tl!r} produced {calls['url']!r}, expected when:{expected}"
            )

    def test_custom_date_range_overrides_time_limit(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(
                query="tech", time_limit="d",
                start_date="2026-01-01", end_date="2026-06-30",
                max_results=1,
            ),
        )
        assert "after%3A2026-01-01" in calls["url"]
        assert "before%3A2026-06-30" in calls["url"]
        # time_limit must NOT have been applied
        assert "when%3A" not in calls["url"]

    def test_country_language_map_to_locale_params(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(query="tech", max_results=1),
            country="IN", language="hi",
        )
        assert "hl=hi-IN" in calls["url"]
        assert "gl=IN" in calls["url"]
        assert "ceid=IN%3Ahi" in calls["url"]

    def test_default_locale_is_us_en(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.search_raw(
            SearchConfig(query="tech", max_results=1),
        )
        assert "hl=en-US" in calls["url"]
        assert "gl=US" in calls["url"]


# ----------------------------------------------------------------------
# search_raw — normalization
# ----------------------------------------------------------------------

class TestSearchRawNormalization:

    def test_entries_normalize_to_canonical_shape(self, monkeypatch):
        _install_fake_feed(monkeypatch, [
            _entry(title="Story A", link="https://example.com/a"),
        ])
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert len(results) == 1
        a = results[0]
        assert a["title"] == "Story A"
        assert a["url"] == "https://example.com/a"
        assert a["source"] == "Example Source"
        assert a["published"] == "2026-09-19T00:00:00+00:00"
        assert a["description"] == "A test summary."
        assert a["_tier"] == "google"

    def test_source_falls_back_to_title_suffix(self, monkeypatch):
        _install_fake_feed(monkeypatch, [
            _entry(
                title="Headline - Some Outlet",
                link="https://example.com/a",
                source_title="",
            ),
        ])
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert results[0]["source"] == "Some Outlet"

    def test_source_falls_back_to_domain(self, monkeypatch):
        _install_fake_feed(monkeypatch, [
            _entry(
                title="Headline",
                link="https://www.example.com/a",
                source_title="",
            ),
        ])
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert results[0]["source"] == "Example"

    def test_entries_without_link_are_dropped(self, monkeypatch):
        _install_fake_feed(monkeypatch, [
            _entry(title="Has link", link="https://example.com/a"),
            _entry(title="No link", link=""),
        ])
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert len(results) == 1
        assert results[0]["title"] == "Has link"

    def test_empty_feed_returns_empty_list(self, monkeypatch):
        _install_fake_feed(monkeypatch, [])
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert results == []

    def test_google_news_links_get_resolved(self, monkeypatch):
        _install_fake_feed(monkeypatch, [
            _entry(link="https://news.google.com/rss/articles/redirect"),
        ])
        monkeypatch.setattr(
            googlenews_engine, "resolve_url",
            lambda u: "https://real.example.com/story",
        )
        results = googlenews_engine.search_raw(
            SearchConfig(query="x", max_results=5),
        )
        assert results[0]["url"] == "https://real.example.com/story"


# ----------------------------------------------------------------------
# fetch_raw — URL shape selection
# ----------------------------------------------------------------------

class TestFetchRawURLShape:

    def test_category_only_uses_topic_feed(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.fetch_raw(
            FetchConfig(category="tech", max_results=5),
        )
        assert "/rss/headlines/section/topic/TECHNOLOGY" in calls["url"]

    def test_category_only_maps_all_topics(self, monkeypatch):
        expected = {
            "business": "BUSINESS",
            "tech": "TECHNOLOGY",
            "sports": "SPORTS",
            "health": "HEALTH",
            "science": "SCIENCE",
            "entertainment": "ENTERTAINMENT",
        }
        for category, topic in expected.items():
            calls = _install_fake_feed(monkeypatch, [])
            googlenews_engine.fetch_raw(
                FetchConfig(category=category, max_results=1),
            )
            assert f"/topic/{topic}" in calls["url"], (
                f"category={category!r} should map to topic {topic!r}"
            )

    def test_location_only_uses_top_stories_with_country_locale(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.fetch_raw(
            FetchConfig(category="general", location="in", max_results=5),
        )
        assert calls["url"].startswith("https://news.google.com/rss?")
        assert "gl=IN" in calls["url"]
        assert "hl=en-IN" in calls["url"]
        assert "/geo/" not in calls["url"]

    def test_category_and_location_use_search_feed(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.fetch_raw(
            FetchConfig(category="tech", location="in", max_results=5),
        )
        # Tech + India → search feed with both words.
        assert "/rss/search?" in calls["url"]
        assert "India" in calls["url"].replace("+", " ").replace("%20", " ")
        assert "tech" in calls["url"].lower()

    def test_neither_uses_top_stories(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.fetch_raw(
            FetchConfig(category="general", max_results=5),
        )
        assert calls["url"].startswith("https://news.google.com/rss?")

    def test_wt_wt_location_treated_as_absent(self, monkeypatch):
        calls = _install_fake_feed(monkeypatch, [])
        googlenews_engine.fetch_raw(
            FetchConfig(category="general", location="wt-wt", max_results=5),
        )
        # Should fall back to top-stories, not the geo feed for WT.
        assert "/headlines/section/geo/" not in calls["url"]


# ----------------------------------------------------------------------
# Pure-Python RSS fallback
# ----------------------------------------------------------------------

class TestPureFallback:

    def test_opt_in_required(self, monkeypatch):
        monkeypatch.delenv("OPEN_NEWS_GNEWS_PURE_FALLBACK", raising=False)
        assert googlenews_engine._pure_fallback_enabled() is False

    def test_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv("OPEN_NEWS_GNEWS_PURE_FALLBACK", "1")
        assert googlenews_engine._pure_fallback_enabled() is True

    def test_parse_rss_extracts_items(self):
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Story One</title>
            <link>https://example.com/1</link>
            <pubDate>Fri, 19 Sep 2026 12:00:00 GMT</pubDate>
            <description>Body one</description>
            <source>Example Outlet</source>
          </item>
          <item>
            <title>Story Two</title>
            <link>https://example.com/2</link>
            <pubDate>Thu, 18 Sep 2026 08:00:00 GMT</pubDate>
            <description>Body two</description>
          </item>
        </channel></rss>"""
        items = googlenews_engine._parse_rss(xml, max_items=10)
        assert len(items) == 2
        assert items[0]["title"] == "Story One"
        assert items[0]["link"] == "https://example.com/1"
        assert items[0]["source"]["title"] == "Example Outlet"
        assert items[1]["source"] == {}

    def test_parse_rss_returns_empty_on_garbage(self):
        assert googlenews_engine._parse_rss("not xml at all", max_items=5) == []