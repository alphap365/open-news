from open_news.processing.token_filter import (
    filter_articles,
    matches_query,
    matches_topic,
)


# ----------------------------------------------------------------------
# Query matching (existing)
# ----------------------------------------------------------------------

def test_matches_query_word_boundary():
    article = {"title": "AI advances in 2026", "description": "Lots of data"}
    assert matches_query(article, "AI", "any", ["title"]) is True
    assert matches_query(article, "A", "any", ["title"]) is False


def test_filter_articles_exact_phrase():
    articles = [{"title": "The quick brown fox", "description": ""}]
    filtered = filter_articles(
        articles, query="quick brown", query_mode="exact_phrase", search_in=["title"],
    )
    assert len(filtered) == 1

    filtered = filter_articles(
        articles, query="quick red", query_mode="exact_phrase", search_in=["title"],
    )
    assert len(filtered) == 0


def test_filter_articles_exclude_terms():
    articles = [{"title": "Apple releases new iPhone", "description": ""}]
    assert len(filter_articles(articles, exclude_terms=["Samsung"], search_in=["title"])) == 1
    assert len(filter_articles(articles, exclude_terms=["iPhone"], search_in=["title"])) == 0


# ----------------------------------------------------------------------
# Topic matching (v1.0.5)
# ----------------------------------------------------------------------

def test_matches_topic_across_all_fields():
    a = {
        "title": "Quarterly results",
        "description": "Strong earnings",
        "text": "Body text",
        "category": "Business",
        "keywords": ["finance", "markets"],
    }
    assert matches_topic(a, "finance") is True
    assert matches_topic(a, "Business") is True
    assert matches_topic(a, "earnings") is True
    assert matches_topic(a, "sports") is False


def test_matches_topic_comma_separated_string():
    a = {"title": "AI advances in medicine", "description": ""}
    assert matches_topic(a, "AI, medicine", topic_mode="any") is True
    assert matches_topic(a, "AI, medicine", topic_mode="all") is True
    assert matches_topic(a, "AI, physics", topic_mode="all") is False
    assert matches_topic(a, "AI, physics", topic_mode="any") is True


def test_matches_topic_list_input():
    a = {"title": "AI advances", "description": ""}
    assert matches_topic(a, ["AI", "medicine"], topic_mode="any") is True
    assert matches_topic(a, ["AI", "medicine"], topic_mode="all") is False


def test_matches_topic_exact_phrase():
    a = {"title": "AI advances in medicine", "description": ""}
    assert matches_topic(a, "AI advances", topic_mode="exact_phrase") is True
    assert matches_topic(a, "advances AI", topic_mode="exact_phrase") is False


def test_matches_topic_empty_passes_through():
    a = {"title": "Anything"}
    assert matches_topic(a, None) is True
    assert matches_topic(a, "") is True
    assert matches_topic(a, []) is True


def test_matches_topic_keywords_string_form():
    a = {"title": "X", "keywords": "alpha, beta, gamma"}
    assert matches_topic(a, "beta") is True


def test_filter_articles_topic_only():
    articles = [
        {"title": "Story about X", "description": "tech news"},
        {"title": "Story about Y", "description": "sports news"},
    ]
    filtered = filter_articles(articles, topic="tech")
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Story about X"


def test_filter_articles_query_and_topic_are_anded():
    articles = [
        {"title": "AI advances in medicine", "description": ""},
        {"title": "AI advances in physics", "description": ""},
    ]
    filtered = filter_articles(articles, query="AI", query_mode="any", topic="medicine")
    assert len(filtered) == 1
    assert "medicine" in filtered[0]["title"]


def test_filter_articles_no_topic_unchanged():
    articles = [{"title": "Anything", "description": ""}]
    assert filter_articles(articles, query=None, topic=None) == articles