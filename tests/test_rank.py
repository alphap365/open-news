"""Tests for open_news.processing.rank.rank_articles."""

import pytest

from open_news.processing import rank as rank_mod
from open_news.processing.rank import (
    _score_basic,
    _score_tfidf,
    rank_articles,
)


# ----------------------------------------------------------------------
# Trivial inputs
# ----------------------------------------------------------------------

def test_rank_empty_list_returns_empty():
    assert rank_articles([]) == []


def test_rank_no_query_preserves_order():
    articles = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    result = rank_articles(articles, query=None)
    assert [a["title"] for a in result] == ["A", "B", "C"]
    for a in result:
        assert a["_rank_score"] == 0.0


def test_rank_blank_query_preserves_order():
    articles = [{"title": "A"}, {"title": "B"}]
    result = rank_articles(articles, query="   ")
    assert [a["title"] for a in result] == ["A", "B"]


# ----------------------------------------------------------------------
# Basic scoring
# ----------------------------------------------------------------------

def test_rank_basic_more_matches_first():
    articles = [
        {"title": "AI AI AI news", "description": ""},
        {"title": "AI single mention", "description": ""},
        {"title": "Unrelated", "description": ""},
    ]
    result = rank_articles(articles, query="AI", method="basic", search_in=["title"])
    assert result[0]["title"] == "AI AI AI news"
    assert result[-1]["title"] == "Unrelated"


def test_rank_score_is_numeric():
    articles = [{"title": "Alpha"}, {"title": "Beta"}]
    result = rank_articles(articles, query="Alpha", method="basic")
    for a in result:
        assert isinstance(a["_rank_score"], float)


# ----------------------------------------------------------------------
# TF-IDF scoring
# ----------------------------------------------------------------------

def test_rank_tfidf_prefers_document_with_matching_term():
    articles = [
        {"title": "climate change news"},
        {"title": "climate politics today"},
    ]
    result = rank_articles(articles, query="change", method="tfidf", search_in=["title"])
    assert result[0]["title"] == "climate change news"


# ----------------------------------------------------------------------
# Method selection / fallback
# ----------------------------------------------------------------------

def test_rank_unknown_method_falls_back_to_auto(monkeypatch):
    monkeypatch.setattr(rank_mod, "_score_bm25", lambda t, q: None)
    articles = [{"title": "X"}]
    result = rank_articles(articles, query="X", method="nonsense")
    assert len(result) == 1
    assert "_rank_score" in result[0]


def test_rank_auto_falls_back_when_bm25_unavailable(monkeypatch):
    """Simulate bm25s not importable — auto must fall back to tfidf."""
    monkeypatch.setattr(rank_mod, "_score_bm25", lambda t, q: None)
    articles = [{"title": "Story A"}, {"title": "Story B"}]
    result = rank_articles(articles, query="Story", method="auto")
    assert len(result) == 2
    for a in result:
        assert "_rank_score" in a


def test_rank_explicit_bm25_falls_back_when_unavailable(monkeypatch):
    monkeypatch.setattr(rank_mod, "_score_bm25", lambda t, q: None)
    articles = [{"title": "X"}]
    result = rank_articles(articles, query="X", method="bm25")
    # Must not raise; falls back to tfidf internally.
    assert len(result) == 1


# ----------------------------------------------------------------------
# search_in / top_k
# ----------------------------------------------------------------------

def test_rank_search_in_narrows_fields():
    articles = [
        {"title": "unrelated title", "text": "needle here"},
        {"title": "needle in title", "text": ""},
    ]
    only_text = rank_articles(articles, query="needle", method="basic", search_in=["text"])
    assert only_text[0]["title"] == "unrelated title"

    only_title = rank_articles(articles, query="needle", method="basic", search_in=["title"])
    assert only_title[0]["title"] == "needle in title"


def test_rank_top_k_limits_results():
    articles = [{"title": f"S{i}"} for i in range(10)]
    result = rank_articles(articles, query="S", top_k=3)
    assert len(result) == 3


# ----------------------------------------------------------------------
# Internal scorer unit tests
# ----------------------------------------------------------------------

def test_score_basic_empty_query_tokens():
    assert _score_basic(["a b c"], []) == [0.0]


def test_score_tfidf_empty_corpus():
    assert _score_tfidf([], ["x"]) == []