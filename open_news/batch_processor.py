"""Batch article extraction and summarization with concurrent processing."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

from .get_article import get_article
from .batch_summarizer import summarize_text

logger = logging.getLogger(__name__)


def batch_summarize(
    urls: List[str],
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_workers: int = 5,
    timeout_per_article: int = 30
) -> List[Dict]:
    """
    Fetch and summarize multiple articles concurrently.

    Args:
        urls: List of article URLs.
        sentence_count: Sentences per summary.
        include_full_text: Include full article text in result.
        include_images_videos: Include images and videos in result.
        max_workers: Number of concurrent threads.
        timeout_per_article: Timeout per article in seconds.

    Returns:
        List of dicts with keys: url, status, title, summary, (optional text, images, videos).
    """
    results = []

    def process(url: str) -> Dict:
        try:
            logger.info(f"Processing: {url}")
            article = get_article(url, timeout=timeout_per_article)
            if not article.get("text"):
                return {
                    "url": url,
                    "status": "failed",
                    "title": "",
                    "summary": "Could not extract article content",
                    "error": "Empty text"
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
            logger.error(f"Error processing {url}: {e}")
            return {
                "url": url,
                "status": "failed",
                "title": "",
                "summary": "",
                "error": str(e)
            }

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(process, url): url for url in urls}
        for future in as_completed(future_to_url):
            results.append(future.result())

    success = sum(1 for r in results if r["status"] == "success")
    logger.info(f"Batch done: {success}/{len(urls)} successful")
    return results


def search_and_summarize(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    include_full_text: bool = False,
    include_images_videos: bool = False,
    max_workers: int = 5
) -> List[Dict]:
    """
    Search Google News, fetch articles, and summarize them.

    Args:
        query: Search term.
        limit: Maximum number of articles.
        sentence_count: Sentences per summary.
        include_full_text: Include full text.
        include_images_videos: Include images/videos.
        max_workers: Concurrent threads.

    Returns:
        List of enriched article dicts with search metadata + summary.
    """
    from .main import search  # avoid circular import

    articles = search(query, limit=limit)
    if not articles:
        logger.warning(f"No articles found for '{query}'")
        return []

    urls = [art["url"] for art in articles]
    batch_results = batch_summarize(
        urls,
        sentence_count=sentence_count,
        include_full_text=include_full_text,
        include_images_videos=include_images_videos,
        max_workers=max_workers
    )

    # Merge search metadata
    url_to_search = {art["url"]: art for art in articles}
    merged = []
    for br in batch_results:
        search_data = url_to_search.get(br["url"], {})
        merged.append({**search_data, **br})
    return merged


# Legacy aliases
fetch_and_summarize_batch = batch_summarize
fetch_and_summarize_search_results = search_and_summarize