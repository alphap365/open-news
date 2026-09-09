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