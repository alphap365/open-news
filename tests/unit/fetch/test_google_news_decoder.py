import base64

import httpx

from open_news.fetch.url_resolver import resolve_url
from open_news.utils import google_news


def _google_url(token: str) -> str:
    return f"https://news.google.com/rss/articles/{token}?oc=5"


def test_decodes_destination_embedded_in_older_article_token(monkeypatch):
    destination = "https://example.com/news/story"
    payload = b"\x08\x13\x22" + bytes([len(destination)]) + destination.encode()
    token = base64.urlsafe_b64encode(payload).decode().rstrip("=")

    def unexpected_request(**kwargs):
        raise AssertionError("an embedded destination should not make a request")

    monkeypatch.setattr(google_news, "make_client", unexpected_request)

    assert resolve_url(_google_url(token)) == destination


def test_uses_google_decode_endpoint_when_token_has_no_embedded_url(monkeypatch):
    token = base64.urlsafe_b64encode(b"opaque-token").decode().rstrip("=")
    destination = "https://example.com/articles/current-story"
    response_text = (
        ")]}'\n\n"
        '[["wrb.fr","Fbv4je",'
        '"[\\"garturlres\\",\\"https://example.com/articles/current-story\\",1]",'
        "null,null,null,\"generic\"]]"
    )

    class FakeResponse:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse(
                '<c-wiz><div jscontroller="x" '
                'data-n-a-sg="signature" data-n-a-ts="12345"></div></c-wiz>'
            )

        def post(self, url, *, data, headers):
            assert url == google_news._BATCHEXECUTE_ENDPOINT
            assert "f.req" in data
            return FakeResponse(response_text)

    def fake_make_client(**kwargs):
        assert kwargs["headers"]["User-Agent"] == "Open-News test agent"
        return FakeClient()

    monkeypatch.setattr(
        google_news,
        "get_user_agent",
        lambda: "Open-News test agent",
    )
    monkeypatch.setattr(google_news, "make_client", fake_make_client)

    assert google_news.resolve_google_news_url(_google_url(token)) == destination


def test_falls_back_to_rss_page_after_http_failure(monkeypatch):
    token = base64.urlsafe_b64encode(b"opaque-token").decode().rstrip("=")
    requested_urls = []

    class FakeResponse:
        text = ""

        def raise_for_status(self):
            return None

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            requested_urls.append(url)
            if len(requested_urls) == 1:
                raise httpx.ConnectError("unavailable")
            return FakeResponse()

    monkeypatch.setattr(
        google_news,
        "make_client",
        lambda **kwargs: FakeClient(),
    )

    assert google_news.resolve_google_news_url(_google_url(token)) is None
    assert len(requested_urls) == 2
    assert "/rss/articles/" in requested_urls[1]


def test_invalid_or_non_google_news_urls_are_unchanged(monkeypatch):
    def unexpected_request(**kwargs):
        raise AssertionError("non-Google URLs must not make requests")

    monkeypatch.setattr(google_news, "make_client", unexpected_request)

    assert resolve_url("https://example.com/article") == "https://example.com/article"
    assert resolve_url("https://news.google.com.evil.example/article/token") == (
        "https://news.google.com.evil.example/article/token"
    )
