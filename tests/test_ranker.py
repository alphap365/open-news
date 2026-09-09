from datetime import datetime
from open_news.processing.ranker import sort_articles

def test_sort_by_date():
    articles = [
        {"published": "2026-01-02"},
        {"published": "2026-01-01"},
        {"published": "2026-01-03"},
    ]
    sorted_articles = sort_articles(articles, sort_by="date")
    assert sorted_articles[0]["published"] == "2026-01-03"

def test_sort_by_date_handles_mixed_timezone_values():
    articles = [
        {"published": "2026-01-02T10:00:00+00:00", "url": "aware"},
        {"published": "2026-01-03", "url": "naive"},
    ]

    sorted_articles = sort_articles(articles, sort_by="date")

    assert sorted_articles[0]["url"] == "naive"

def test_sort_by_popularity_clusters():
    articles = [
        {"title": "Story about X", "url": "a"},
        {"title": "Story about X - update", "url": "b"},
        {"title": "Story about X (live)", "url": "c"},
        {"title": "Unique story Y", "url": "d"},
    ]
    sorted_articles = sort_articles(articles, sort_by="popularity")
    # The first three should be grouped at the top
    assert sorted_articles[0]["url"] in ["a", "b", "c"]
    assert sorted_articles[1]["url"] in ["a", "b", "c"]
    assert sorted_articles[2]["url"] in ["a", "b", "c"]
    assert sorted_articles[3]["url"] == "d"

def test_sort_by_relevance_preserves_order():
    articles = [{"title": "A"}, {"title": "B"}]
    assert sort_articles(articles, sort_by="relevance") == articles