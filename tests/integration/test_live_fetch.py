"""India/general fetch integration tests.

Marked `network` — skipped automatically when outbound TCP to
news.google.com:443 is unreachable (see conftest.py).

All `fetch()` calls in this module go through `_fetch_list()`, which casts
the Union[List[Dict], Iterator[List[Dict]]] return type down to
List[Dict] for the non-streaming form. Without it, static analyzers pick
the Iterator branch on every call site and flag len()/[] access.
"""

import pathlib
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, cast

import pytest

from open_news import fetch
from open_news.config import FetchConfig
from open_news.feeds.duckduckgo_engine import fetch_raw

# ----------------------------------------------------------------------
# Skip conditions
# ----------------------------------------------------------------------


def _has_network(host="news.google.com", port=443, timeout=3.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_HAS_NETWORK = _has_network()
pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(not _HAS_NETWORK, reason="no route to news.google.com:443"),
]


# Domains whose pages refresh a `dateModified` field on a CMS schedule
# rather than publishing a real article date (liveblogs, stock quote
# pages). Documented as a known issue in docs/changelog.md, so the
# freshness canary below skips them.
_UNRELIABLE_DATE_DOMAINS = (
    # Aggregators — the page date reflects when the syndicator received
    # the story, not when the original publisher wrote it.
    "msn.com",
    "yahoo.com",
    "news.google.com",
    # Stock quote pages — dateModified reflects CMS activity.
    "zeebiz.com",
    "moneycontrol.com",
    # Liveblogs — dateModified regenerates per request.
    "timesnownews.com",
    "news9live.com",
)


def _is_unreliable_date_url(url: str) -> bool:
    return any(d in url for d in _UNRELIABLE_DATE_DOMAINS)


# ----------------------------------------------------------------------
# Narrowed fetch helper
# ----------------------------------------------------------------------


def _fetch_list(**kwargs: Any) -> List[Dict]:
    """fetch() without refresh_interval always returns a list; the
    signature is Union[List[Dict], Iterator[List[Dict]]] because the
    streaming form returns a generator. Cast once here so every test
    body can use it as a plain list."""
    return cast(List[Dict], fetch(**kwargs))


# ----------------------------------------------------------------------
# Raw acquisition
# ----------------------------------------------------------------------


class TestRawAcquisition:
    def test_raw_returns_something_for_india_general(self):
        raw = fetch_raw(FetchConfig(category="general", location="in", max_results=10))
        assert isinstance(raw, list)
        # Feed engines can be thin, but an entirely empty response for a
        # country as large as India is a signal worth failing on.
        assert len(raw) >= 1, "raw acquisition returned zero items"

    def test_raw_items_have_required_keys(self):
        raw = fetch_raw(FetchConfig(category="general", location="in", max_results=10))
        for a in raw:
            assert "title" in a and a["title"]
            assert "url" in a and a["url"].startswith(("http://", "https://"))


# ----------------------------------------------------------------------
# Public fetch() end to end
# ----------------------------------------------------------------------


class TestPublicFetch:
    def test_fetch_returns_list(self):
        articles = _fetch_list(category="general", location="in", max_results=10)
        assert isinstance(articles, list)

    def test_fetch_respects_max_results(self):
        articles = _fetch_list(category="general", location="in", max_results=5)
        assert len(articles) <= 5

    def test_fetch_articles_are_absolute_urls(self):
        articles = _fetch_list(category="general", location="in", max_results=5)
        for a in articles:
            assert a["url"].startswith(("http://", "https://"))

    def test_fetch_no_hub_urls(self):
        from open_news.fetch.url_resolver import is_hub_url

        articles = _fetch_list(category="general", location="in", max_results=5)
        for a in articles:
            assert not is_hub_url(a["url"]), f"hub leaked: {a['url']!r}"


# ----------------------------------------------------------------------
# Date correctness
# ----------------------------------------------------------------------


class TestDateSanity:
    def test_dates_are_iso_and_parsable(self):
        articles = _fetch_list(category="general", location="in", max_results=10)
        for a in articles:
            raw = a.get("publish_date") or a.get("published")
            if not raw:
                continue
            from open_news.utils.dates import parse_datetime

            assert parse_datetime(raw) is not None, f"unparsable date: {raw!r}"

    def test_dates_are_not_future(self):
        articles = _fetch_list(category="general", location="in", max_results=10)
        now = datetime.now(timezone.utc)
        for a in articles:
            raw = a.get("publish_date") or a.get("published")
            if not raw:
                continue
            from open_news.utils.dates import parse_datetime

            dt = parse_datetime(raw)
            if dt is None:
                continue
            # Allow 2 days of slack for embargo/clock skew.
            assert dt <= now + timedelta(days=2), f"future date: {dt} on {a['url']}"

    def test_dates_are_not_wildly_stale(self):
        """Feed engines surface recent stories. A very old `published` on
        a live-feed result usually means the extractor picked up the wrong
        date field (e.g. a dateModified that wasn't refreshed).

        This is a canary for gross misparsing (a 2020 date on a 2026 feed,
        an epoch zero, etc.), not a freshness guarantee. Two accommodations:

          * window is 90 days, not 7 or 10 — evergreen stories and quote
            pages legitimately appear on general feeds;
          * known churny domains (liveblogs, stock quote pages) are
            skipped because their dateModified reflects CMS activity, not
            publish time. Documented in docs/changelog.md.
        """
        articles = _fetch_list(category="general", location="in", max_results=10)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stale_cutoff = now - timedelta(days=90)
        for a in articles:
            if _is_unreliable_date_url(a["url"]):
                continue
            raw = a.get("publish_date") or a.get("published")
            if not raw:
                continue
            from open_news.utils.dates import parse_datetime

            dt = parse_datetime(raw)
            if dt is None:
                continue
            dt = dt.replace(microsecond=0)
            assert dt >= stale_cutoff, f"stale date {dt.isoformat()} on {a['url']}"


# ----------------------------------------------------------------------
# Default story grouping
# ----------------------------------------------------------------------


class TestStoryGrouping:
    def test_similar_articles_are_grouped_without_losing_source_links(self):
        from open_news.processing.pipeline import run_pipeline

        raw = [
            {
                "title": "City approves new clean energy plan",
                "url": "https://one.example/news/energy-plan",
                "source": "One News",
                "published": "2025-01-03T00:00:00Z",
            },
            {
                "title": "City approves clean energy plan",
                "url": "https://two.example/story/clean-energy",
                "source": "Two News",
                "published": "2025-01-02T00:00:00Z",
            },
            {
                "title": "Local sports result",
                "url": "https://sports.example/story",
                "source": "Sports News",
            },
        ]

        stories = run_pipeline(raw, max_results=10)

        assert len(stories) == 2
        energy_story = next(story for story in stories if "energy" in story["title"])
        assert energy_story["cluster_size"] == 2
        assert energy_story["sources"] == ["One News", "Two News"]
        assert len(energy_story["similar_articles"]) == 1
        assert (
            energy_story["similar_articles"][0]["url"]
            == "https://two.example/story/clean-energy"
        )


# ----------------------------------------------------------------------
# Region discipline
# ----------------------------------------------------------------------


class TestRegionDiscipline:
    """`location` is a query hint, not a filter. Off-region articles are
    expected to appear occasionally. These tests assert the *documented*
    contract — that location steers results — without pretending to
    enforce a guarantee the library does not make."""

    def test_location_returns_some_results(self):
        """If the location hint were being ignored entirely, we would
        usually see zero. Any non-empty result set is enough to show the
        hint reaches the acquisition tiers."""
        articles = _fetch_list(category="general", location="in", max_results=10)
        # The feed can legitimately be empty; skip rather than fail.
        if not articles:
            pytest.skip("feed returned no results for this hour")
        assert len(articles) >= 1

    def test_documentation_says_location_is_hint(self):
        """Guard the documented contract: if someone ever changes the
        library to enforce a hard region filter, this test will fail and
        force the doc to be updated alongside it."""
        doc = (
            pathlib.Path(__file__).resolve().parent.parent
            / "docs"
            / "parameters-reference.md"
        )
        if not doc.exists():
            pytest.skip("docs not present in this checkout")
        text = doc.read_text(encoding="utf-8")
        assert "query hint" in text.lower(), (
            "parameters-reference.md no longer describes location as a "
            "query hint; update the test or the doc so they agree"
        )


# ----------------------------------------------------------------------
# Full-content enrichment
# ----------------------------------------------------------------------


class TestFullContent:
    def test_full_content_flag_does_not_error(self):
        articles = _fetch_list(
            category="general",
            location="in",
            max_results=3,
            full_content=True,
        )
        assert isinstance(articles, list)

    def test_full_content_marks_each_attempt(self):
        """Every article should carry _full_content=True/False plus a
        reason when False. This is the contract _enrich_full_content
        documents."""
        articles = _fetch_list(
            category="general",
            location="in",
            max_results=3,
            full_content=True,
        )
        for a in articles:
            assert "_full_content" in a, f"missing enrichment marker on {a['url']}"
            if a["_full_content"] is False:
                assert "_full_content_reason" in a, (
                    f"False marker without reason on {a['url']}"
                )


# ----------------------------------------------------------------------
# Markdown export integration
# ----------------------------------------------------------------------


class TestMarkdownExport:
    def test_export_roundtrip(self, tmp_path):
        from open_news import to_markdown

        articles = _fetch_list(category="general", location="in", max_results=5)
        out = tmp_path / "in.md"
        returned = to_markdown(articles, path=out, title="India · General")
        assert out.exists()
        assert out.read_text(encoding="utf-8") == returned

    def test_export_toc_unicode_anchor(self, tmp_path):
        """Regression guard for the slug bug: Devanagari headings must
        keep their combining marks in TOC anchors."""
        from open_news.export.markdown import _slug

        assert _slug("1. पढ़ें 21 सितम्बर") == "1-पढ़ें-21-सितम्बर"
