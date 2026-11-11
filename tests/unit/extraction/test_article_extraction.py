from open_news.core.extractor import extract_article

MINIMAL_HTML = """
<html>
<head><title>Test Title</title></head>
<body>
    <article>
        <h1>Headline from H1</h1>
        <p>This is the first paragraph of the article. It should be enough text to pass the threshold.</p>
        <p>This is the second paragraph. The extractor should grab both.</p>
    </article>
</body>
</html>
"""


def test_extract_basic():
    result = extract_article(MINIMAL_HTML, url="http://test.com")
    assert result["title"] == "Headline from H1"  # Should prefer H1 over <title>
    assert len(result["text"]) > 50
    assert "first paragraph" in result["text"]


def test_extract_removes_junk():
    html_with_junk = """
    <html><body>
        <nav>Navigation</nav>
        <article><h1>Title</h1><p>Real content here.</p></article>
        <footer>Footer text</footer>
    </body></html>
    """
    result = extract_article(html_with_junk, url="http://test.com")
    assert "Navigation" not in result["text"]
    assert "Footer" not in result["text"]
    assert "Real content" in result["text"]


def test_json_ld_parsed_once_per_extraction(monkeypatch):
    """extract_article must not re-parse every JSON-LD script tag for
    source resolution after the strategy loop already parsed them."""
    from open_news.core.strategies import JsonLdStrategy

    original = JsonLdStrategy._parse
    parse_calls = {"n": 0}

    def counting_parse(self, doc):
        parse_calls["n"] += 1
        return original(self, doc)

    monkeypatch.setattr(JsonLdStrategy, "_parse", counting_parse)

    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "NewsArticle", "headline": "Test Headline",
     "description": "Test description"}
    </script>
    </head><body>
    <article>
      <h1>Test Headline</h1>
      <p>Body text that is long enough to pass the extractor threshold.
         This paragraph exists so a minimal extraction can succeed and we
         reach the resolve_source step where the second parse happens.</p>
    </article>
    </body></html>
    """
    extract_article(html, url="https://example.com/a")

    assert parse_calls["n"] <= 1, (
        f"JsonLdStrategy._parse called {parse_calls['n']} times; must be "
        f"at most 1. extract() re-parses JSON-LD for resolve_source "
        f"instead of reusing the result from the strategy loop."
    )
