from open_news.processing.language_guard import filter_by_language

def test_filter_by_language_keep(mocker):
    # Mock detect to return "en"
    mocker.patch("open_news.processing.language_guard.detect", return_value="en")
    articles = [{"title": "Hello world", "description": "Test"}]
    result = filter_by_language(articles, language="en")
    assert len(result) == 1

def test_filter_by_language_drop(mocker):
    mocker.patch("open_news.processing.language_guard.detect", return_value="fr")
    articles = [{"title": "Bonjour", "description": "Test"}]
    result = filter_by_language(articles, language="en")
    assert len(result) == 0

def test_filter_by_language_keep_undetectable(mocker):
    mocker.patch("open_news.processing.language_guard.detect", return_value=None)
    articles = [{"title": "X", "description": "Y"}]  # Too short
    result = filter_by_language(articles, language="en")
    assert len(result) == 1  # Keep if undetectable