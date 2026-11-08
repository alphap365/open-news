import asyncio
import logging
from typing import Dict, List, cast

from ..fetch.article import get_article_async
from .dedupe import dedupe_articles
from .summarizer import summarize_text

logger = logging.getLogger(__name__)


async def batch_summarize_async(
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
                article = await get_article_async(
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
) -> List[Dict]:
    """Sync wrapper — `max_workers` maps to async concurrency limit."""
    return asyncio.run(
        batch_summarize_async(
            urls,
            sentence_count=sentence_count,
            include_full_text=include_full_text,
            include_images_videos=include_images_videos,
            max_concurrency=max_workers,
            timeout_per_article=timeout_per_article,
            js=js,
            dedupe=dedupe,
        )
    )


async def search_and_summarize_async(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_concurrency: int = 5,
    js: bool = False,
    dedupe: bool = True,
) -> List[Dict]:
    from ..api import search  # deferred: avoid circular import

    articles = cast(List[Dict], search(query, max_results=limit))
    if not articles:
        logger.warning("No articles found for %r", query)
        return []

    # BUG FIX: the previous code ran search() a second time here and never
    # deduped. We now dedupe the list we already have.
    if dedupe:
        articles = dedupe_articles(articles, fuzzy=True)

    urls = [art["url"] for art in articles]
    batch_results = await batch_summarize_async(
        urls,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_concurrency=max_concurrency,
        js=js,
        dedupe=False,  # already deduped above
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
    dedupe: bool = True,
) -> List[Dict]:
    return asyncio.run(
        search_and_summarize_async(
            query,
            limit=limit,
            sentence_count=sentence_count,
            include_full_text=include_full_text,
            include_images_videos=include_images_videos,
            max_concurrency=max_workers,
            js=js,
            dedupe=dedupe,
        )
    )


# Legacy aliases
fetch_and_summarize_batch = batch_summarize
fetch_and_summarize_search_results = search_and_summarize
