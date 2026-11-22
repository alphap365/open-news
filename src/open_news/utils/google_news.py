"""Resolve Google News article redirects.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from typing import Any, Optional
from urllib.parse import quote, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from .httpx_compat import make_client
from .user_agents import get_user_agent

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_HOST = "news.google.com"
_BATCHEXECUTE_ENDPOINT = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_URL_PATTERN = re.compile(r"https?://[^\s\x00-\x1f\"'<>\\]+")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


def _extract_article_token(source_url: str) -> Optional[str]:
    try:
        parsed = urlparse(source_url)
    except ValueError:
        return None
    if (parsed.hostname or "").lower().rstrip(".") != _GOOGLE_NEWS_HOST:
        return None

    segments = parsed.path.rstrip("/").split("/")
    if len(segments) < 2 or segments[-2] not in {"articles", "read"}:
        return None
    token = unquote(segments[-1])
    return token or None


def _is_external_destination_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and parsed.hostname.lower().rstrip(".") != _GOOGLE_NEWS_HOST
    )


def _decode_embedded_destination(token: str) -> Optional[str]:
    padded_token = token + "=" * (-len(token) % 4)
    try:
        raw = base64.b64decode(padded_token, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        return None

    decoded = raw.decode("utf-8", errors="ignore")
    for match in _URL_PATTERN.finditer(decoded):
        candidate = match.group().rstrip(_TRAILING_URL_PUNCTUATION)
        if _is_external_destination_url(candidate):
            return candidate
    return None


def _fetch_decode_parameters(
    client: httpx.Client, article_token: str
) -> Optional[tuple[str, str]]:
    encoded_token = quote(article_token, safe="-_")
    for path in ("articles", "rss/articles"):
        article_url = f"https://{_GOOGLE_NEWS_HOST}/{path}/{encoded_token}"
        try:
            response = client.get(article_url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("Google News decoding-parameter request failed: %s", exc)
            continue

        element = BeautifulSoup(response.text, "html.parser").select_one(
            "c-wiz > div[jscontroller]"
        )
        if element is None:
            continue
        signature = element.get("data-n-a-sg")
        timestamp = element.get("data-n-a-ts")
        if isinstance(signature, str) and signature and isinstance(timestamp, str):
            if timestamp.isdigit():
                return signature, timestamp
    return None


def _find_destination_url(value: Any) -> Optional[str]:
    if isinstance(value, str):
        try:
            nested = json.loads(value)
        except json.JSONDecodeError:
            nested = None
        if nested is not None:
            result = _find_destination_url(nested)
            if result:
                return result
        for match in _URL_PATTERN.finditer(value):
            candidate = match.group().rstrip(_TRAILING_URL_PUNCTUATION)
            if _is_external_destination_url(candidate):
                return candidate
    elif isinstance(value, (list, tuple)):
        for item in value:
            result = _find_destination_url(item)
            if result:
                return result
    elif isinstance(value, dict):
        for item in value.values():
            result = _find_destination_url(item)
            if result:
                return result
    return None


def _parse_batchexecute_destination(response_text: str) -> Optional[str]:
    text = response_text.lstrip()
    if text.startswith(")]}'"):
        text = text[4:]

    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "[":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        destination_url = _find_destination_url(payload)
        if destination_url:
            return destination_url
    return None


def resolve_google_news_url(source_url: str) -> Optional[str]:
    """Return an article's destination URL, or ``None`` if it cannot resolve."""
    article_token = _extract_article_token(source_url)
    if article_token is None:
        return None

    embedded_destination = _decode_embedded_destination(article_token)
    if embedded_destination:
        return embedded_destination

    try:
        with make_client(
            timeout=10.0,
            follow_redirects=False,
            headers={"User-Agent": get_user_agent()},
        ) as client:
            decode_parameters = _fetch_decode_parameters(client, article_token)
            if decode_parameters is None:
                return None
            signature, timestamp = decode_parameters
            batchexecute_request = [
                "garturlreq",
                [
                    [
                        "X",
                        "X",
                        ["X", "X"],
                        None,
                        None,
                        1,
                        1,
                        "US:en",
                        None,
                        1,
                        None,
                        None,
                        None,
                        None,
                        None,
                        0,
                        1,
                    ],
                    "X",
                    "X",
                    1,
                    [1, 1, 1],
                    1,
                    1,
                    None,
                    0,
                    0,
                    None,
                    0,
                ],
                article_token,
                int(timestamp),
                signature,
            ]
            batchexecute_payload = [
                "Fbv4je",
                json.dumps(batchexecute_request, separators=(",", ":")),
            ]
            response = client.post(
                _BATCHEXECUTE_ENDPOINT,
                data={
                    "f.req": json.dumps(
                        [[batchexecute_payload]], separators=(",", ":")
                    )
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("Google News article decode request failed: %s", exc)
        return None

    return _parse_batchexecute_destination(response.text)


def resolve_google_news_redirect(source_url: str) -> Optional[str]:
    """Backward-compatible alias for :func:`resolve_google_news_url`."""
    return resolve_google_news_url(source_url)
