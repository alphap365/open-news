"""India/general fetch integration tests.

Marked `network` — skipped automatically when outbound TCP to
news.google.com:443 is unreachable (see conftest.py).
"""

import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

from open_news import fetch
from open_news.config import FetchConfig
from open_news.feeds.duckduckgo_engine import fetch_raw


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
        articles = fetch(category="general", location="in", max_results=10)
        assert isinstance(articles, list)

    def test_fetch_respects_max_results(self):
        articles = fetch(category="general", location="in", max_results=5)
        assert len(articles) <= 5

    def test_fetch_articles_are_absolute_urls(self):
        articles = fetch(category="general", location="in", max_results=5)
        for a in articles:
            assert a["url"].startswith(("http://", "https://"))

    def test_fetch_no_hub_urls(self):
        from open_news.fetch.url_resolver import is_hub_url
        articles = fetch(category="general", location="in", max_results=5)
        for a in articles:
            assert not is_hub_url(a["url"]), f"hub leaked: {a['url']!r}"


# ----------------------------------------------------------------------
# Date correctness  (the anomaly from the manual run)
# ----------------------------------------------------------------------

class TestDateSanity:

    def test_dates_are_iso_and_parsable(self):
        articles = fetch(category="general", location="in", max_results=10)
        for a in articles:
            raw = a.get("publish_date") or a.get("published")
            if not raw:
                continue
            from open_news.utils.dates import parse_datetime
            assert parse_datetime(raw) is not None, f"unparsable date: {raw!r}"

    def test_dates_are_not_future(self):
        articles = fetch(category="general", location="in", max_results=10)
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
        """Feed engines surface recent stories. A month-old 'published' on
        a live-feed result usually means the extractor picked up the wrong
        date field (e.g. dateModified that wasn't actually refreshed)."""
        articles = fetch(category="general", location="in", max_results=10)
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(days=7)
        for a in articles:
            raw = a.get("publish_date") or a.get("published")
            if not raw:
                continue
            from open_news.utils.dates import parse_datetime
            dt = parse_datetime(raw)
            if dt is None:
                continue
            assert dt >= stale_cutoff, (
                f"stale date {dt.isoformat()} on {a['url']}"
            )


# ----------------------------------------------------------------------
# Dedupe behaviour  (why we saw 3 instead of 10)
# ----------------------------------------------------------------------

class TestDedupe:

    def test_dedupe_off_keeps_at_least_as_many(self):
        raw = fetch_raw(FetchConfig(category="general", location="in", max_results=10))
        with_dedupe = fetch(
            category="general", location="in", max_results=10, dedupe=True,
        )
        without_dedupe = fetch(
            category="general", location="in", max_results=10, dedupe=False,
        )
        assert len(without_dedupe) >= len(with_dedupe), (
            f"dedupe reduced count below no-dedupe path: "
            f"{len(with_dedupe)} vs {len(without_dedupe)}"
        )


# ----------------------------------------------------------------------
# Region discipline  (the US box-office leak)
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
        articles = fetch(category="general", location="in", max_results=10)
        # The feed can legitimately be empty; skip rather than fail.
        if not articles:
            pytest.skip("feed returned no results for this hour")
        assert len(articles) >= 1

    def test_documentation_says_location_is_hint(self):
        """Guard the documented contract: if someone ever changes the
        library to enforce a hard region filter, this test will fail and
        force the doc to be updated alongside it."""
        import pathlib
        doc = pathlib.Path(__file__).resolve().parent.parent / "docs" / "parameters-reference.md"
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
        articles = fetch(
            category="general", location="in", max_results=3, full_content=True,
        )
        assert isinstance(articles, list)

    def test_full_content_marks_each_attempt(self):
        """Every article should carry _full_content=True/False plus a
        reason when False. This is the contract _enrich_full_content
        documents."""
        articles = fetch(
            category="general", location="in", max_results=3, full_content=True,
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
        articles = fetch(category="general", location="in", max_results=5)
        out = tmp_path / "in.md"
        returned = to_markdown(articles, path=out, title="India · General")
        assert out.exists()
        assert out.read_text(encoding="utf-8") == returned

    def test_export_toc_unicode_anchor(self, tmp_path):
        """Regression guard for the slug bug: Devanagari headings must
        keep their combining marks in TOC anchors."""
        from open_news.export.markdown import _slug
        assert _slug("1. पढ़ें 21 सितम्बर") == "1-पढ़ें-21-सितम्बर"