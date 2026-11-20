"""Body-keyword pipeline tests against a local multi-page site.

Regression coverage for the body-search truncation bug: the pipeline used
to enrich a single ``max_results * 3`` window, so a run of early
non-matches truncated the result set and later hits were never fetched.
Failed fetches also annotated the caller's dicts in place.

These tests serve a multi-page site on loopback (no external network) and
cover: hits beyond the first window, failed fetches (reason preserved,
loop not blocked, input untouched), deduped source attribution surviving
enrichment, early-stop once the quota is met, and task cancellation.
"""

import asyncio
import copy
import http.server
import threading

import pytest

from open_news.processing.pipeline import (
    _filter_by_body_async,
    run_pipeline,
    run_pipeline_async,
)

# Body text long enough for the heuristic extractor to commit to it —
# modelled on the conftest local_article_server pages.
_FILLER = (
    "This paragraph exists so the extractor has enough candidate text to "
    "score the article body against the surrounding boilerplate blocks."
)


def _page(body_sentence, site_name="Local Fixture"):
    return (
        "<!doctype html><html><head>"
        f"<title>{body_sentence[:40]}</title>"
        f'<meta property="og:site_name" content="{site_name}">'
        "</head><body><article>"
        f"<h1>{body_sentence[:40]}</h1>"
        f"<p>{_FILLER}</p>"
        f"<p>{body_sentence}</p>"
        f"<p>{_FILLER}</p>"
        "</article></body></html>"
    )


@pytest.fixture
def local_news_site():
    """Factory fixture: serve a dict of pages on a threaded loopback server.

    Page spec values:
        str                  — served as 200 text/html
        {"status": int}      — served with that status and no body
        {"html": str, "delay": seconds} — slow 200 response

    Returns (base_url, requests) where ``requests`` records every path
    the pipeline actually fetched, so tests can assert how far the
    batch loop walked the candidate list.
    """
    servers = []

    def _make(pages):
        requests = []

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?", 1)[0]
                requests.append(path)
                spec = pages.get(path)
                if spec is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if isinstance(spec, dict):
                    status = spec.get("status", 200)
                    if status != 200:
                        self.send_response(status)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    delay = spec.get("delay", 0)
                    if delay:
                        import time

                        time.sleep(delay)
                    body = spec["html"].encode("utf-8")
                else:
                    body = spec.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args, **kwargs):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_address[1]}", requests

    yield _make

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _candidates(base, count, source="Local Fixture"):
    return [
        {
            "title": f"Candidate {i}",
            "url": f"{base}/article{i}.html",
            "source": source,
            "published": "2026-01-01T00:00:00Z",
        }
        for i in range(count)
    ]


# ----------------------------------------------------------------------
# Hits beyond the first enrichment window
# ----------------------------------------------------------------------


def test_body_hits_beyond_first_window_are_filled(local_news_site):
    """max_results=2 -> the old code fetched only candidates 0-5. The
    keyword lives in the bodies of candidates 8 and 9, so the old window
    truncated to zero results; batch-wise refill must reach them."""
    pages = {
        f"/article{i}.html": _page(f"Candidate {i} reports on local weather.")
        for i in range(10)
    }
    pages["/article8.html"] = _page("A rare xylophone concert drew crowds.")
    pages["/article9.html"] = _page("Another xylophone recital follows.")
    base, _ = local_news_site(pages)

    stories = run_pipeline(
        _candidates(base, 10),
        max_results=2,
        query="xylophone",
        search_in=["body"],
    )

    urls = {s["url"] for s in stories}
    assert f"{base}/article8.html" in urls
    assert f"{base}/article9.html" in urls


def test_body_search_stops_once_quota_is_met(local_news_site):
    """Once max_results body matches accumulate, later candidates are
    never fetched — batching must not degenerate into crawl-everything."""
    pages = {
        f"/article{i}.html": _page(f"Candidate {i} mentions the xylophone.")
        for i in range(10)
    }
    base, requests = local_news_site(pages)

    stories = run_pipeline(
        _candidates(base, 10),
        max_results=2,
        query="xylophone",
        search_in=["body"],
    )

    assert stories, "expected body matches from the first batch"
    # First window is max_results * 3 = 6 candidates; the quota is met
    # inside it, so candidates 6-9 must remain untouched.
    assert len(requests) == 6
    assert all(f"/article{i}.html" not in requests for i in range(6, 10))


# ----------------------------------------------------------------------
# Failed fetches: reason preserved, loop not blocked, input untouched
# ----------------------------------------------------------------------


def test_failed_fetches_keep_reason_and_dont_block(local_news_site):
    """The head of the candidate list fails (404 + unreachable host);
    the matches sit behind them. Failures must keep their reason without
    filling the match quota or stopping the batch loop."""
    pages = {
        # 0-2 fail: 404 for the first two, nothing listening on the third.
        "/article0.html": {"status": 404},
        "/article1.html": {"status": 500},
        # 3-5 fetch fine but lack the keyword.
        **{
            f"/article{i}.html": _page(f"Candidate {i} covers city hall.")
            for i in range(3, 6)
        },
        # 6-7 are the real hits, beyond the failed head.
        "/article6.html": _page("A rare xylophone concert drew crowds."),
        "/article7.html": _page("Another xylophone recital follows."),
    }
    base, _ = local_news_site(pages)
    candidates = _candidates(base, 8)
    # Unreachable port: exercises the fetch_error exception path.
    candidates[2]["url"] = "http://127.0.0.1:1/article2.html"

    matched = asyncio.run(
        _filter_by_body_async(
            candidates,
            2,
            query="xylophone",
            query_mode="any",
            exclude_terms=None,
            search_in=["body"],
        )
    )

    by_url = {a["url"]: a for a in matched}
    # The hits behind the failures were reached.
    assert f"{base}/article6.html" in by_url
    assert f"{base}/article7.html" in by_url
    # Failed items keep their marker and reason.
    for url in (
        f"{base}/article0.html",
        f"{base}/article1.html",
        "http://127.0.0.1:1/article2.html",
    ):
        assert by_url[url]["_full_content"] is False
        assert by_url[url]["_full_content_reason"]


def test_caller_input_objects_are_not_mutated(local_news_site):
    """Neither the list nor the article dicts the caller passed in may
    change — failures included (the old code annotated them in place)."""
    pages = {
        "/article0.html": {"status": 404},
        "/article1.html": _page("A rare xylophone concert drew crowds."),
        "/article2.html": _page("Candidate 2 covers city hall."),
    }
    base, _ = local_news_site(pages)
    candidates = _candidates(base, 3)
    snapshot = copy.deepcopy(candidates)

    stories = run_pipeline(
        candidates,
        max_results=2,
        query="xylophone",
        search_in=["body"],
        full_content=True,
    )

    assert stories, "expected the xylophone hit to survive the pipeline"
    assert candidates == snapshot
    assert all("_full_content" not in c for c in candidates)


# ----------------------------------------------------------------------
# Deduped source attribution survives enrichment
# ----------------------------------------------------------------------


def test_deduped_sources_survive_body_enrichment(local_news_site):
    """Two records for one URL merge into a single candidate whose
    ``sources`` lists both outlets. Enrichment must not let the fetched
    page's own attribution (og:site_name / netloc) clobber that."""
    pages = {
        "/article0.html": _page("A rare xylophone concert drew crowds."),
    }
    base, _ = local_news_site(pages)
    url = f"{base}/article0.html"
    candidates = [
        {
            "title": "Concert draws crowds",
            "url": url,
            "source": "Alpha News",
            "published": "2026-01-01T00:00:00Z",
        },
        {
            "title": "Concert draws crowds",
            "url": url,
            "source": "Beta News",
            "published": "2026-01-01T00:00:00Z",
        },
    ]

    stories = run_pipeline(
        candidates,
        max_results=1,
        query="xylophone",
        search_in=["body"],
    )

    assert len(stories) == 1
    story = stories[0]
    assert "Alpha News" in story["sources"]
    assert "Beta News" in story["sources"]
    # The representative's own source field is not replaced by the
    # fetched page's og:site_name ("Local Fixture") or the netloc.
    assert story["source"] in ("Alpha News", "Beta News")


# ----------------------------------------------------------------------
# Cancellation
# ----------------------------------------------------------------------


def test_body_search_cancellation_propagates(local_news_site):
    """Cancelling the pipeline mid-enrichment raises CancelledError
    promptly instead of hanging on the in-flight fetches."""
    pages = {
        f"/article{i}.html": {
            "html": _page(f"Candidate {i} mentions the xylophone."),
            "delay": 5,
        }
        for i in range(4)
    }
    base, _ = local_news_site(pages)
    candidates = _candidates(base, 4)

    async def main():
        task = asyncio.create_task(
            run_pipeline_async(
                candidates,
                2,
                query="xylophone",
                search_in=["body"],
            )
        )
        await asyncio.sleep(0.3)  # let the first batch get in flight
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Outer timeout guards against a hang if cancellation is swallowed.
    asyncio.run(asyncio.wait_for(main(), timeout=10))
