from open_news.processing.domain_filter import filter_by_domain

def test_whitelist_subdomain_match():
    articles = [{"url": "https://edition.cnn.com/story"}]
    result = filter_by_domain(articles, whitelist=["cnn.com"])
    assert len(result) == 1

def test_whitelist_no_match():
    articles = [{"url": "https://bbc.com/story"}]
    result = filter_by_domain(articles, whitelist=["cnn.com"])
    assert len(result) == 0

def test_blacklist_subdomain_match():
    articles = [{"url": "https://edition.cnn.com/story"}]
    result = filter_by_domain(articles, blacklist=["cnn.com"])
    assert len(result) == 0

def test_blacklist_does_not_match_similar():
    articles = [{"url": "https://notcnn.com/story"}]
    result = filter_by_domain(articles, blacklist=["cnn.com"])
    assert len(result) == 1  # Should not block