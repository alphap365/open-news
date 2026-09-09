import pytest
from unittest.mock import patch
from open_news.cli import main

def test_cli_fetch_parse(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "fetch", "--category", "tech", "--limit", "2"])
    mock_fetch = mocker.patch("open_news.cli.fetch", return_value=[{"title": "Tech Story"}])
    
    main()
    captured = capsys.readouterr()
    
    mock_fetch.assert_called_once_with(category="tech", location=None, max_results=2, language=None, full_content=False, sort_by="date")
    assert "Tech Story" in captured.out

def test_cli_extract(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "extract", "http://test.com", "--js"])
    mock_get = mocker.patch("open_news.cli.get_article", return_value={"title": "Extracted"})
    
    main()
    mock_get.assert_called_once_with("http://test.com", timeout=15, js=True)