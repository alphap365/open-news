"""Pipeline integration tests using mock enrichment (no network)."""

from open_news.processing import pipeline
from open_news.processing.pipeline import run_pipeline


def test_run_pipeline_full_flow(mocker):
    raw_articles = [
        {
            "title": "Tech news",
            "url": "https://tech.com/1",
            "published": "2026-01-02",
            "description": "AI",
        },
        {
            "title": "Sports news",
            "url": "https://sports.com/1",
            "published": "2026-01-01",
            "description": "Football",
        },
        {
            "title": "Tech news duplicate",
            "url": "https://tech.com/2",
            "published": "2026-01-02",
            "description": "AI again",
        },
    ]
    mocker.patch(
        "open_news.processing.pipeline._enrich_full_content",
        return_value=raw_articles,
    )

    result = run_pipeline(
        raw_articles,
        max_results=2,
        language="en",
        query="tech",
        query_mode="any",
        sort_by="date",
        full_content=False,
    )
    assert len(result) <= 2


def _patch_enrich(mocker):
    """Patch whichever enrichment implementation the pipeline actually
    calls. The async migration left both names in the module, but
    run_pipeline_async dispatches through _enrich_full_content_async;
    run_pipeline (sync, legacy) uses _enrich_full_content."""
    if hasattr(pipeline, "_enrich_full_content_async"):

        async def fake_enrich(articles, js=False):
            return articles

        return mocker.patch(
            "open_news.processing.pipeline._enrich_full_content_async",
            side_effect=fake_enrich,
        )
    return mocker.patch(
        "open_news.processing.pipeline._enrich_full_content",
        side_effect=lambda articles, js=False: articles,
    )


def test_pipeline_slices_before_enrich(mocker):
    """The pipeline must slice to max_results *before* enrichment, so it
    never crawls articles that will be discarded."""
    raw = [{"url": f"https://a.com/{i}"} for i in range(10)]
    mock_enrich = _patch_enrich(mocker)

    run_pipeline(raw, max_results=3, full_content=True)

    assert mock_enrich.called, (
        "enrichment function was not called — the pipeline likely skipped "
        "the full_content step, or the mock target does not match the "
        "call path."
    )
    called_articles = mock_enrich.call_args[0][0]
    assert len(called_articles) == 3, (
        f"expected 3 articles passed to enrichment, got "
        f"{len(called_articles)}; the pipeline is slicing AFTER enrichment."
    )
