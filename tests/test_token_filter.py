from open_news.processing.token_filter import filter_articles, matches_query

def test_matches_query_word_boundary():
    article = {"title": "AI advances in 2026", "description": "Lots of data"}
    # "AI" should match
    assert matches_query(article, "AI", "any", ["title"]) is True
    # "A" should NOT match (word boundary)
    assert matches_query(article, "A", "any", ["title"]) is False

def test_filter_articles_exact_phrase():
    articles = [{"title": "The quick brown fox", "description": ""}]
    filtered = filter_articles(articles, query="quick brown", query_mode="exact_phrase", search_in=["title"])
    assert len(filtered) == 1
    
    filtered = filter_articles(articles, query="quick red", query_mode="exact_phrase", search_in=["title"])
    assert len(filtered) == 0

def test_filter_articles_exclude_terms():
    articles = [{"title": "Apple releases new iPhone", "description": ""}]
    filtered = filter_articles(articles, exclude_terms=["Samsung"], search_in=["title"])
    assert len(filtered) == 1  # Not excluded
    
    filtered = filter_articles(articles, exclude_terms=["iPhone"], search_in=["title"])
    assert len(filtered) == 0  # Excluded