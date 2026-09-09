import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_playwright_available = None


def is_available() -> bool:
    global _playwright_available
    if _playwright_available is None:
        try:
            import playwright  # noqa: F401
            _playwright_available = True
        except ImportError:
            _playwright_available = False
    return _playwright_available


def render_html(url: str, timeout: int = 15, wait_until: str = "networkidle",
                 user_agent: Optional[str] = None) -> str:
    """
    Render a single JS-heavy page and return the final HTML.
    Launches and tears down a browser per call — fine for one-off use
    (get_article(js=True)) but too slow for crawling many pages; use
    PersistentRenderer for that.

    Raises RuntimeError if playwright isn't installed.
    """
    if not is_available():
        raise RuntimeError(
            "JS rendering requires the 'js' extra. Install with: pip install open-news-api[js]"
        )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=user_agent) if user_agent else browser.new_context()
            page = context.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until=wait_until)
            html = page.content()
            return html
        finally:
            browser.close()


class PersistentRenderer:
    """
    A single Chromium instance reused across many page loads — the crawler's
    JS backend. Launching a browser costs ~500ms-1s; paying that once per
    crawl instead of once per URL is what keeps JS-mode crawling usable.
    This is a fundamentally different execution model from render_html():
    sequential page loads sharing one process, not a per-call spin-up.

    Usage:
        with PersistentRenderer(user_agent=ua) as r:
            for url in urls:
                html = r.render(url)
    """

    def __init__(self, timeout: int = 15, wait_until: str = "networkidle",
                 user_agent: Optional[str] = None, block_resources: bool = True):
        if not is_available():
            raise RuntimeError(
                "JS rendering requires the 'js' extra. Install with: pip install open-news-api[js]"
            )
        self.timeout = timeout
        self.wait_until = wait_until
        self.user_agent = user_agent
        self.block_resources = block_resources
        self._pw = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "PersistentRenderer":
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._context = (self._browser.new_context(user_agent=self.user_agent)
                          if self.user_agent else self._browser.new_context())
        if self.block_resources:
            # Images/fonts/media never affect extracted article text — skipping
            # them cuts page-load time substantially without changing output.
            self._context.route(
                re.compile(r"\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4|mp3)(\?.*)?$"),
                lambda route: route.abort(),
            )
        return self

    def render(self, url: str) -> str:
        page = self._context.new_page()
        try:
            page.goto(url, timeout=self.timeout * 1000, wait_until=self.wait_until)
            return page.content()
        finally:
            page.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()