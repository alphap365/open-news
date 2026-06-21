"""Optional JS rendering backend using Playwright. Only imported when js=True is requested."""

import logging
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
    Render a JS-heavy page and return the final HTML.

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