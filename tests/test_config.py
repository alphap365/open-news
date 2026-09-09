import pytest
from open_news.config import FetchConfig, SearchConfig

def test_fetch_config_valid():
    cfg = FetchConfig(category="tech", max_results=10)
    assert cfg.category == "tech"

def test_fetch_config_invalid_category():
    with pytest.raises(ValueError):
        FetchConfig(category="invalid_cat")

def test_fetch_config_invalid_time_limit():
    with pytest.raises(ValueError):
        FetchConfig(time_limit="x")

def test_search_config_valid():
    cfg = SearchConfig(query="climate", query_mode="all")
    assert cfg.query == "climate"

def test_search_config_empty_query():
    with pytest.raises(ValueError):
        SearchConfig(query="")