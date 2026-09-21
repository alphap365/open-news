"""Tests for open_news.processing.cluster.cluster_articles."""

from open_news.processing.cluster import cluster_articles


def _art(title, url, source="Example", published=None, text=""):
    return {
        "title": title,
        "url": url,
        "source": source,
        "published": published or "",
        "description": text,
        "text": text,
    }


# ----------------------------------------------------------------------
# Empty / trivial inputs
# ----------------------------------------------------------------------

def test_cluster_empty_input_returns_empty_list():
    assert cluster_articles([]) == []


def test_cluster_single_article_returns_one_cluster():
    result = cluster_articles([_art("Only story", "https://a.com/1")], dedupe=False)
    assert len(result) == 1
    assert result[0]["size"] == 1


# ----------------------------------------------------------------------
# Basic clustering
# ----------------------------------------------------------------------

def test_cluster_identical_titles_grouped():
    articles = [
        _art("Earthquake hits Japan", "https://a.com/1"),
        _art("Earthquake hits Japan", "https://b.com/2"),
        _art("Sports update: football", "https://c.com/3"),
    ]
    clusters = cluster_articles(articles, dedupe=False)
    assert len(clusters) == 2
    assert sorted(c["size"] for c in clusters) == [1, 2]


def test_cluster_similar_titles_grouped():
    articles = [
        _art("AI takes over the world", "https://a.com/1"),
        _art("AI takes over world", "https://b.com/2"),
        _art("Unrelated politics story", "https://c.com/3"),
    ]
    clusters = cluster_articles(articles, threshold=0.75, dedupe=False)
    assert len(clusters) == 2


def test_cluster_threshold_high_splits_more():
    articles = [
        _art("Alpha story", "https://a.com/1"),
        _art("Alpha story something else", "https://b.com/2"),
    ]
    strict = cluster_articles(articles, threshold=0.95, dedupe=False)
    loose = cluster_articles(articles, threshold=0.5, dedupe=False)
    assert len(strict) >= len(loose)


# ----------------------------------------------------------------------
# Filtering knobs
# ----------------------------------------------------------------------

def test_cluster_drop_singletons():
    articles = [
        _art("Same story", "https://a.com/1"),
        _art("Same story", "https://b.com/2"),
        _art("Lonely story", "https://c.com/3"),
    ]
    clusters = cluster_articles(articles, drop_singletons=True, dedupe=False)
    assert len(clusters) == 1
    assert clusters[0]["size"] == 2


def test_cluster_min_cluster_size():
    articles = [
        _art("Same story", "https://a.com/1"),
        _art("Same story", "https://b.com/2"),
        _art("Lonely story", "https://c.com/3"),
    ]
    clusters = cluster_articles(articles, min_cluster_size=2, dedupe=False)
    assert len(clusters) == 1
    assert clusters[0]["size"] == 2


def test_cluster_topic_filter_applied():
    articles = [
        _art("AI in medicine", "https://a.com/1", source="A"),
        _art("Sports update", "https://b.com/2", source="B"),
        _art("AI in physics", "https://c.com/3", source="C"),
    ]
    clusters = cluster_articles(articles, topic="AI", dedupe=False)
    titles = {c["label"] for c in clusters}
    assert "Sports update" not in titles


# ----------------------------------------------------------------------
# Shape / output contract
# ----------------------------------------------------------------------

def test_cluster_ids_are_sequential():
    articles = [
        _art("A", "https://a.com/1"),
        _art("B", "https://b.com/2"),
    ]
    clusters = cluster_articles(articles, dedupe=False)
    assert [c["id"] for c in clusters] == list(range(len(clusters)))


def test_cluster_shape_has_required_keys():
    articles = [
        _art("Same", "https://a.com/1", source="Alpha", published="2026-01-02"),
        _art("Same", "https://b.com/2", source="Beta", published="2026-01-01"),
    ]
    clusters = cluster_articles(articles, dedupe=False)
    c = clusters[0]
    for key in ("id", "label", "size", "score", "sources",
                "first_seen", "last_seen", "representative", "articles"):
        assert key in c, f"missing key {key!r}"
    assert c["size"] == 2
    assert set(c["sources"]) == {"Alpha", "Beta"}
    assert c["first_seen"] is not None
    assert c["last_seen"] is not None
    assert isinstance(c["articles"], list)


def test_cluster_representative_is_a_member():
    articles = [
        _art("Same", "https://a.com/1"),
        _art("Same", "https://b.com/2"),
    ]
    clusters = cluster_articles(articles, dedupe=False)
    rep = clusters[0]["representative"]
    assert rep in clusters[0]["articles"]


# ----------------------------------------------------------------------
# Sorting
# ----------------------------------------------------------------------

def test_cluster_sort_by_size_puts_largest_first():
    articles = [
        _art("Big story", "https://a.com/1"),
        _art("Big story", "https://b.com/2"),
        _art("Big story", "https://c.com/3"),
        _art("Small story", "https://d.com/4"),
    ]
    clusters = cluster_articles(articles, sort_by="size", dedupe=False)
    assert clusters[0]["size"] == 3


# ----------------------------------------------------------------------
# Rank integration
# ----------------------------------------------------------------------

def test_cluster_rank_query_marks_scores():
    articles = [
        _art("OpenAI announces GPT-5", "https://a.com/1"),
        _art("Local weather report", "https://b.com/2"),
    ]
    clusters = cluster_articles(
        articles, rank_query="OpenAI GPT", rank_method="tfidf", dedupe=False,
    )
    for c in clusters:
        for a in c["articles"]:
            assert "_rank_score" in a
            assert isinstance(a["_rank_score"], float)