import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from lxml.html import fromstring, HtmlElement

from ..core.extractor import ArticleExtractor
from ..processing.dedupe import normalize_url
from ..utils.user_agents import get_user_agent

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# URL classification — cheap, pre-fetch filtering
# ----------------------------------------------------------------------

# Paths that are structurally never a single article: listings, account
# pages, static assets, feeds we already have a dedicated parser for.
NON_ARTICLE_PATH = re.compile(
    r"(?:^/(?:tag|tags|category|categories|author|authors|search|login|"
    r"signin|signup|register|subscribe|account|cart|checkout|about|contact|"
    r"privacy|terms|sitemap|rss|feed)(?:/|$))"
    r"|(?:/page/\d+/?$)"
    r"|\.(?:jpg|jpeg|png|gif|svg|webp|css|js|ico|pdf|zip|mp4|mp3|xml|json)(?:\?.*)?$",
    re.I,
)

# Positive signal: date-stamped path or a long, hyphenated slug — both
# strong indicators of an individual article URL across most CMSs.
ARTICLE_PATH_HINT = re.compile(
    r"/\d{4}/\d{1,2}/\d{1,2}/"      # /2026/08/01/
    r"|/\d{4}-\d{2}-\d{2}-"          # /2026-08-01-slug
    r"|-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+"   # 4+ hyphenated words
    r"|/\d{5,}(?:/|$|-)",            # long numeric CMS id
    re.I,
)

NON_HTML_SCHEMES = {"mailto", "tel", "javascript", "ftp"}


def _prefilter(url: str) -> bool:
    """Cheap rejection before ever issuing a request."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if NON_ARTICLE_PATH.search(parsed.path):
        return False
    return True


def _looks_like_article(url: str) -> bool:
    """Positive pre-fetch hint used only to prioritize the frontier queue,
    never to hard-exclude — final say always belongs to the extractor."""
    return bool(ARTICLE_PATH_HINT.search(urlparse(url).path))


# ----------------------------------------------------------------------
# robots.txt cache
# ----------------------------------------------------------------------

class RobotsCache:
    def __init__(self, client: httpx.AsyncClient, user_agent: str):
        self._client = client
        self._ua = user_agent
        self._parsers: Dict[str, RobotFileParser] = {}
        self._lock = asyncio.Lock()

    async def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        async with self._lock:
            rp = self._parsers.get(origin)
            if rp is None:
                rp = await self._fetch(origin)
                self._parsers[origin] = rp
        if rp is None:
            return True  # no robots.txt or unreachable -> default allow
        return rp.can_fetch(self._ua, url)

    async def _fetch(self, origin: str) -> Optional[RobotFileParser]:
        try:
            resp = await self._client.get(f"{origin}/robots.txt", timeout=8)
            if resp.status_code >= 400:
                return None
            rp = RobotFileParser()
            rp.parse(resp.text.splitlines())
            return rp
        except Exception:
            return None


# ----------------------------------------------------------------------
# Crawl result
# ----------------------------------------------------------------------

@dataclass
class CrawlStats:
    pages_fetched: int = 0
    articles_found: int = 0
    robots_blocked: int = 0
    errors: int = 0


# ----------------------------------------------------------------------
# Default (non-JS) async crawler
# ----------------------------------------------------------------------

class AsyncCrawler:
    def __init__(
        self,
        max_pages: int = 40,
        max_depth: int = 2,
        concurrency: int = 10,
        min_text_length: int = 200,
        same_domain_only: bool = True,
        obey_robots: bool = True,
        timeout: int = 10,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.concurrency = concurrency
        self.min_text_length = min_text_length
        self.same_domain_only = same_domain_only
        self.obey_robots = obey_robots
        self.timeout = timeout
        self.extractor = ArticleExtractor()

    async def crawl(self, start_url: str) -> List[Dict]:
        stats = CrawlStats()
        domain = urlparse(start_url).netloc
        seen_norm: Set[str] = set()
        articles: List[Dict] = []
        sem = asyncio.Semaphore(self.concurrency)
        headers = {"User-Agent": get_user_agent()}

        async with httpx.AsyncClient(follow_redirects=True, headers=headers, timeout=self.timeout) as client:
            robots = RobotsCache(client, headers["User-Agent"]) if self.obey_robots else None

            # frontier holds (url, depth); a simple list-based BFS is plenty
            # at these page counts — no need for a priority heap.
            frontier = [(start_url, 0)]
            seen_norm.add(normalize_url(start_url))

            while frontier and stats.pages_fetched < self.max_pages:
                batch = frontier[: self.concurrency]
                frontier = frontier[self.concurrency:]

                results = await asyncio.gather(
                    *[self._fetch_one(client, sem, robots, url, depth, stats) for url, depth in batch],
                    return_exceptions=True,
                )

                for r in results:
                    if isinstance(r, Exception) or r is None:
                        continue
                    article, links, depth = r
                    if article is not None:
                        articles.append(article)
                    if depth < self.max_depth:
                        for link in links:
                            if self.same_domain_only and urlparse(link).netloc != domain:
                                continue
                            key = normalize_url(link)
                            if key in seen_norm:
                                continue
                            seen_norm.add(key)
                            frontier.append((link, depth + 1))
                        # prioritize article-shaped URLs so we hit real
                        # content before exhausting max_pages on nav/hubs
                        frontier.sort(key=lambda item: not _looks_like_article(item[0]))

        logger.info(
            f"Crawl of {start_url}: fetched={stats.pages_fetched} "
            f"articles={len(articles)} robots_blocked={stats.robots_blocked} errors={stats.errors}"
        )
        return articles

    async def _fetch_one(self, client, sem, robots, url, depth, stats):
        if not _prefilter(url):
            return None
        if robots is not None and not await robots.allowed(url):
            stats.robots_blocked += 1
            return None

        async with sem:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if "text/html" not in resp.headers.get("content-type", ""):
                    return None
                html = resp.text
            except Exception as e:
                stats.errors += 1
                logger.debug(f"Fetch failed {url}: {e}")
                return None

        stats.pages_fetched += 1
        links = self._extract_links(html, url)
        article = None
        try:
            extracted = self.extractor.extract(html, url=url)
            if len(extracted.get("text", "")) >= self.min_text_length:
                extracted["url"] = url
                article = extracted
        except Exception as e:
            logger.debug(f"Extraction failed {url}: {e}")

        return article, links, depth

    def _extract_links(self, html: str, base_url: str) -> List[str]:
        try:
            doc = fromstring(html)
        except Exception:
            return []
        links = []
        for href in doc.xpath("//a/@href"):
            href = href.strip()
            if not href or href.startswith("#"):
                continue
            scheme = urlparse(href).scheme
            if scheme and scheme in NON_HTML_SCHEMES:
                continue
            links.append(urljoin(base_url, href))
        return links


# ----------------------------------------------------------------------
# JS-mode crawler — sequential, single shared browser
# ----------------------------------------------------------------------

class JSCrawler:
    """
    Same frontier/classification/dedupe logic as AsyncCrawler, but driven by
    a single persistent Playwright browser instead of many concurrent HTTP
    requests. Genuinely different shape: sequential page loads (a browser
    context is not free to fan out N-wide the way httpx connections are),
    smaller default page budget, no asyncio concurrency at all.
    """

    def __init__(
        self,
        max_pages: int = 15,
        max_depth: int = 1,
        min_text_length: int = 200,
        same_domain_only: bool = True,
        obey_robots: bool = True,
        timeout: int = 15,
    ):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.min_text_length = min_text_length
        self.same_domain_only = same_domain_only
        self.obey_robots = obey_robots
        self.timeout = timeout
        self.extractor = ArticleExtractor()

    def crawl(self, start_url: str) -> List[Dict]:
        from ..core.renderer import PersistentRenderer
        import httpx as _httpx

        domain = urlparse(start_url).netloc
        user_agent = get_user_agent()
        stats = CrawlStats()
        seen_norm: Set[str] = {normalize_url(start_url)}
        frontier = [(start_url, 0)]
        articles: List[Dict] = []
        robots_parsers: Dict[str, Optional[RobotFileParser]] = {}

        def robots_allowed(url: str) -> bool:
            if not self.obey_robots:
                return True
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
            if origin not in robots_parsers:
                try:
                    resp = _httpx.get(f"{origin}/robots.txt", timeout=8, headers={"User-Agent": user_agent})
                    if resp.status_code >= 400:
                        robots_parsers[origin] = None
                    else:
                        rp = RobotFileParser()
                        rp.parse(resp.text.splitlines())
                        robots_parsers[origin] = rp
                except Exception:
                    robots_parsers[origin] = None
            rp = robots_parsers[origin]
            return rp is None or rp.can_fetch(user_agent, url)

        with PersistentRenderer(timeout=self.timeout, user_agent=user_agent) as renderer:
            while frontier and stats.pages_fetched < self.max_pages:
                frontier.sort(key=lambda item: not _looks_like_article(item[0]))
                url, depth = frontier.pop(0)

                if not _prefilter(url) or not robots_allowed(url):
                    stats.robots_blocked += 1
                    continue

                try:
                    html = renderer.render(url)
                except Exception as e:
                    stats.errors += 1
                    logger.debug(f"JS render failed {url}: {e}")
                    continue

                stats.pages_fetched += 1

                try:
                    doc = fromstring(html)
                    links = [urljoin(url, h.strip()) for h in doc.xpath("//a/@href") if h.strip() and not h.startswith("#")]
                except Exception:
                    links = []

                try:
                    extracted = self.extractor.extract(html, url=url)
                    if len(extracted.get("text", "")) >= self.min_text_length:
                        extracted["url"] = url
                        articles.append(extracted)
                except Exception as e:
                    logger.debug(f"Extraction failed {url}: {e}")

                if depth < self.max_depth:
                    for link in links:
                        if self.same_domain_only and urlparse(link).netloc != domain:
                            continue
                        key = normalize_url(link)
                        if key in seen_norm:
                            continue
                        seen_norm.add(key)
                        frontier.append((link, depth + 1))

        logger.info(
            f"JS crawl of {start_url}: fetched={stats.pages_fetched} "
            f"articles={len(articles)} robots_blocked={stats.robots_blocked} errors={stats.errors}"
        )
        return articles


# ----------------------------------------------------------------------
# Public sync entrypoint
# ----------------------------------------------------------------------

def crawl_site(
    start_url: str,
    max_pages: Optional[int] = None,
    max_depth: Optional[int] = None,
    js: bool = False,
    concurrency: int = 10,
    min_text_length: int = 200,
    same_domain_only: bool = True,
    obey_robots: bool = True,
) -> List[Dict]:
    """
    Crawl any news-provider URL (homepage, section page, whatever) and
    return extracted articles. This is the compulsory backbone of
    api.discover_and_get() — RSS discovery is tried first as a shortcut,
    but this crawler is what runs regardless of whether a feed exists.

    js=False (default): fast async path, many pages in flight at once.
        max_pages/max_depth default to 40/2 when not explicitly given.
    js=True: sequential path backed by one persistent headless browser —
        a different strategy, not just a slower version of the same loop.
        max_pages/max_depth default to a much smaller 15/1 budget when
        not explicitly given. Passing either explicitly always wins,
        regardless of js mode (no more guessing "was this overridden?"
        from a magic-number match).
    """
    if js:
        crawler = JSCrawler(
            max_pages=max_pages if max_pages is not None else 15,
            max_depth=max_depth if max_depth is not None else 1,
            min_text_length=min_text_length,
            same_domain_only=same_domain_only,
            obey_robots=obey_robots,
        )
        return crawler.crawl(start_url)

    crawler = AsyncCrawler(
        max_pages=max_pages if max_pages is not None else 40,
        max_depth=max_depth if max_depth is not None else 2,
        concurrency=concurrency,
        min_text_length=min_text_length,
        same_domain_only=same_domain_only,
        obey_robots=obey_robots,
    )
    return asyncio.run(crawler.crawl(start_url))