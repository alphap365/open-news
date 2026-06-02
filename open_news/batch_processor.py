"""Batch article extraction and summarization with concurrent processing."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def fetch_and_summarize_batch(
    urls: List[str],
    include_full_text: bool = False,
    sentence_count: int = 3,
    max_workers: int = 5,
    timeout: int = 30
) -> List[Dict]:
    """
    Fetch and summarize multiple articles concurrently.
    
    **Args:**
    - `urls` (List[str]): Article URLs to process
    - `include_full_text` (bool): Include full article text in results (default: False)
    - `sentence_count` (int): Sentences per summary (default: 3)
    - `max_workers` (int): Concurrent threads (default: 5, adjust based on CPU/network)
    - `timeout` (int): Timeout per article in seconds (default: 30)
    
    **Returns:**
    List of dicts with:
    - `url` (str): Original URL
    - `status` (str): "success", "failed", or "timeout"
    - `title` (str): Article title (if extracted)
    - `summary` (str): Summarized content
    - `text` (str): Full text (only if include_full_text=True)
    - `error` (str): Error message if status is "failed"
    
    **Example:**
    ```python
    from open_news import fetch_and_summarize_batch
    
    urls = [
        "https://example.com/article1",
        "https://example.com/article2",
    ]
    
    results = fetch_and_summarize_batch(urls, sentence_count=2)
    for result in results:
        if result["status"] == "success":
            print(f"📰 {result['title']}")
            print(f"   Summary: {result['summary'][:150]}...")
        else:
            print(f"❌ {result['url']}: {result['error']}")
    ```
    """
    from .get_article import fetch_article
    from .batch_summarizer import summarize_text_simple
    
    results = []
    
    def process_article(url: str) -> Dict:
        """Process a single article: fetch, extract, summarize."""
        try:
            logger.info(f"Processing: {url}")
            
            # Fetch article (includes caching if available)
            article_data = fetch_article(url)
            
            if not article_data.get("text"):
                return {
                    "url": url,
                    "status": "failed",
                    "title": "",
                    "summary": "Could not extract article content",
                    "error": "Extraction pipeline returned empty content"
                }
            
            title = article_data.get("title", "")
            text = article_data.get("text", "")
            
            # Summarize
            summary = summarize_text_simple(text, sentence_count)
            
            result = {
                "url": url,
                "status": "success",
                "title": title,
                "summary": summary,
            }
            
            if include_full_text:
                result["text"] = text
            
            logger.info(f"✓ Successfully processed: {url}")
            return result
            
        except TimeoutError:
            return {
                "url": url,
                "status": "timeout",
                "title": "",
                "summary": "",
                "error": f"Processing exceeded {timeout}s timeout"
            }
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return {
                "url": url,
                "status": "failed",
                "title": "",
                "summary": "",
                "error": str(e)
            }
    
    # Process articles concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_url = {
            executor.submit(process_article, url): url 
            for url in urls
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_url, timeout=timeout):
            result = future.result()
            results.append(result)
    
    # Log summary
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count
    logger.info(f"Batch complete: {success_count} success, {failed_count} failed out of {len(urls)}")
    
    return results


def fetch_and_summarize_search_results(
    query: str,
    limit: int = 10,
    sentence_count: int = 3,
    **kwargs
) -> List[Dict]:
    """
    Search Google News + fetch + summarize all results in one go.
    
    **Args:**
    - `query` (str): Search term
    - `limit` (int): Max results (default: 10)
    - `sentence_count` (int): Sentences per summary
    - `**kwargs`: Passed to fetch_and_summarize_batch (max_workers, timeout, etc.)
    
    **Example:**
    ```python
    results = fetch_and_summarize_search_results(
        "climate change", 
        limit=5,
        sentence_count=2,
        max_workers=3
    )
    ```
    """
    from .main import search_news
    
    logger.info(f"Searching for '{query}'...")
    articles = search_news(query, limit=limit)
    
    if not articles:
        logger.warning(f"No articles found for '{query}'")
        return []
    
    urls = [art["url"] for art in articles]
    batch_results = fetch_and_summarize_batch(
        urls,
        sentence_count=sentence_count,
        **kwargs
    )
    
    # Merge search metadata with batch results
    url_to_search = {art["url"]: art for art in articles}
    merged = []
    
    for batch_result in batch_results:
        url = batch_result["url"]
        search_data = url_to_search.get(url, {})
        
        merged_result = {
            **search_data,  # url, title (from search), source, published, description
            **batch_result  # overrides with full extracted title, summary, status
        }
        merged.append(merged_result)
    
    return merged
