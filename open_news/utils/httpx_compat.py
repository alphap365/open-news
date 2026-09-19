"""Version-agnostic httpx.Client construction.

httpx renamed the proxy parameter twice:

  * <= 0.25   : ``proxies=`` (a dict of scheme -> URL)
  * 0.26-0.27 : both, with ``proxies=`` deprecated
  * >= 0.28   : only ``proxy=`` (single URL string)

Termux occasionally resolves an older httpx than the project's pin
suggests. This shim probes the installed httpx once at import time and
exposes a single ``make_client`` factory that works on every version.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, Optional

import httpx


def _supports_modern_proxy() -> bool:
    try:
        params = inspect.signature(httpx.Client.__init__).parameters
    except (TypeError, ValueError):
        return True
    return "proxy" in params


_PROXY_KWARG: Optional[str] = "proxy" if _supports_modern_proxy() else "proxies"


def make_client(
    *,
    proxy: Optional[str] = None,
    timeout: float = 20.0,
    follow_redirects: bool = True,
    headers: Optional[Dict[str, str]] = None,
    verify: Any = True,
) -> httpx.Client:
    """Build an httpx.Client that works on every httpx >= 0.20."""
    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": follow_redirects,
    }
    if headers is not None:
        kwargs["headers"] = headers
    if verify is not True:
        kwargs["verify"] = verify

    if not proxy:
        return httpx.Client(**kwargs)

    if _PROXY_KWARG == "proxy":
        kwargs["proxy"] = proxy
    else:
        kwargs["proxies"] = {"http://": proxy, "https://": proxy}
    return httpx.Client(**kwargs)