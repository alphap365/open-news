import asyncio
import logging
from typing import Awaitable, Dict, List

from ..fetch.article import _get_article_async
from .dedupe import dedupe_articles
from .summarizer import summarize_text

logger = logging.getLogger(__name__)


async def _batch_summarize_impl(
    urls: List[str],
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_concurrency: int = 5,
    timeout_per_article: int = 30,
    js: bool = False,
    dedupe: bool = True,
) -> List[Dict]:
    if dedupe and urls:
        deduped = dedupe_articles([{"url": u, "title": ""} for u in urls])
        urls = [a["url"] for a in deduped]

    sem = asyncio.Semaphore(max_concurrency)

    async def process(url: str) -> Dict:
        async with sem:
            try:
                logger.info("Processing: %s", url)
                article = await _get_article_async(
                    url,
                    timeout=timeout_per_article,
                    js=js,
                )
                if not article.get("text"):
                    return {
                        "url": url,
                        "status": "failed",
                        "title": "",
                        "summary": "Could not extract article content",
                        "error": "Empty text",
                    }
                summary = summarize_text(article["text"], sentence_count)
                result = {
                    "url": url,
                    "status": "success",
                    "title": article.get("title", ""),
                    "summary": summary,
                }
                if include_full_text:
                    result["text"] = article.get("text", "")
                if include_images_videos:
                    result["images"] = article.get("images", [])
                    result["videos"] = article.get("videos", [])
                    result["top_image"] = article.get("top_image")
                return result
            except Exception as e:
                logger.error("Error processing %s: %s", url, e)
                return {
                    "url": url,
                    "status": "failed",
                    "title": "",
                    "summary": "",
                    "error": str(e),
                }

    results = await asyncio.gather(*(process(u) for u in urls))
    success = sum(1 for r in results if r["status"] == "success")
    logger.info("Batch done: %d/%d successful", success, len(urls))
    return list(results)


def batch_summarize(
    urls: List[str],
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_workers: int = 5,
    timeout_per_article: int = 30,
    js: bool = False,
    dedupe: bool = True,
    async_: bool = False,
) -> List[Dict] | Awaitable[List[Dict]]:
    """Summarize URLs; await the result when async_ is True."""
    coroutine = _batch_summarize_impl(
        urls,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_workers,
        timeout_per_article=timeout_per_article,
        js=js,
        dedupe=dedupe,
    )
    return coroutine if async_ else asyncio.run(coroutine)


async def _search_and_summarize_impl(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_concurrency: int = 5,
    js: bool = False,
) -> List[Dict]:
    from ..api import _search_async  # deferred: avoid circular import

    articles = await _search_async(query=query, max_results=limit)
    if not articles:
        logger.warning("No articles found for %r", query)
        return []

    urls = [art["url"] for art in articles]
    batch_results = await _batch_summarize_impl(
        urls,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_concurrency,
        js=js,
    )

    url_to_search = {art["url"]: art for art in articles}
    return [{**url_to_search.get(br["url"], {}), **br} for br in batch_results]


def search_and_summarize(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_workers: int = 5,
    js: bool = False,
    async_: bool = False,
) -> List[Dict] | Awaitable[List[Dict]]:
    """Search for articles and summarize them; await when async_ is True."""
    coroutine = _search_and_summarize_impl(
        query,
        limit=limit,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_workers,
        js=js,
    )
    return coroutine if async_ else asyncio.run(coroutine)


# Legacy aliases
fetch_and_summarize_batch = batch_summarize
fetch_and_summarize_search_results = search_and_summarize
