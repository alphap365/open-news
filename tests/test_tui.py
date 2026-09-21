from open_news import tui


# ----------------------------------------------------------------------
# Streaming (existing)
# ----------------------------------------------------------------------

def test_live_refresh_uses_fetch_stream(monkeypatch, capsys):
    prompts = iter(["a", "tech", "", "3", "5"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    def fake_fetch(**kwargs):
        assert kwargs == {
            "category": "tech",
            "location": None,
            "max_results": 3,
            "refresh_interval": 5,
            "language": None,
        }

        def stream():
            yield [{"title": "Fresh story", "url": "https://example.com/story"}]
            raise KeyboardInterrupt

        return stream()

    monkeypatch.setattr(tui, "fetch", fake_fetch)
    app = tui.OpenNewsTUI()
    app._watch_news()

    assert app.articles == [{"title": "Fresh story", "url": "https://example.com/story"}]
    assert "Fresh story" in capsys.readouterr().out


def test_live_refresh_uses_stream_search(monkeypatch, capsys):
    prompts = iter(["b", "budget 2026", "3", "5"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    def fake_stream_search(query, **kwargs):
        assert query == "budget 2026"
        assert kwargs["refresh_interval"] == 5
        assert kwargs["max_results"] == 3

        def stream():
            yield [{"title": "Budget passed", "url": "https://example.com/budget"}]
            raise KeyboardInterrupt

        return stream()

    monkeypatch.setattr(tui, "stream_search", fake_stream_search)
    app = tui.OpenNewsTUI()
    app._watch_news()

    assert app.articles == [{"title": "Budget passed", "url": "https://example.com/budget"}]
    assert "Budget passed" in capsys.readouterr().out


# ----------------------------------------------------------------------
# v1.0.5 — clear
# ----------------------------------------------------------------------

def test_clear_loaded_removes_articles_and_clusters():
    app = tui.OpenNewsTUI()
    app.articles = [{"title": "A"}]
    app.clusters = [{"id": 0}]
    app._clear_loaded()
    assert app.articles == []
    assert app.clusters == []


def test_replace_articles_clears_stale_clusters():
    app = tui.OpenNewsTUI()
    app.clusters = [{"id": 0}]
    app._replace_articles([{"title": "New"}], "Fetched")
    assert app.clusters == []


# ----------------------------------------------------------------------
# v1.0.5 — cluster
# ----------------------------------------------------------------------

def test_cluster_loaded_groups_similar_titles(monkeypatch, capsys):
    app = tui.OpenNewsTUI()
    app.articles = [
        {"title": "Same story", "url": "https://a.com/1"},
        {"title": "Same story", "url": "https://b.com/2"},
        {"title": "Other story", "url": "https://c.com/3"},
    ]
    # prompts: threshold, drop-singletons, sort-by, rank query
    prompts = iter(["", "n", "score", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    app._cluster_loaded()

    assert app.clusters
    assert any(c["size"] == 2 for c in app.clusters)
    assert "Clustered" in capsys.readouterr().out


def test_cluster_loaded_needs_two_articles(capsys):
    app = tui.OpenNewsTUI()
    app.articles = [{"title": "Only one"}]
    app._cluster_loaded()
    assert "at least 2" in capsys.readouterr().out


def test_cluster_loaded_with_rank_query(monkeypatch, capsys):
    app = tui.OpenNewsTUI()
    app.articles = [
        {"title": "AI story one", "url": "https://a.com/1", "text": "AI"},
        {"title": "AI story two", "url": "https://b.com/2", "text": "AI"},
    ]
    # prompts: threshold, drop, sort, rank query
    prompts = iter(["", "n", "score", "AI"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    app._cluster_loaded()

    for c in app.clusters:
        for a in c["articles"]:
            assert "_rank_score" in a


# ----------------------------------------------------------------------
# v1.0.5 — export
# ----------------------------------------------------------------------

def test_export_loaded_nothing(capsys):
    app = tui.OpenNewsTUI()
    app._export_loaded()
    assert "Nothing to export" in capsys.readouterr().out


def test_export_loaded_articles_markdown(monkeypatch, tmp_path):
    app = tui.OpenNewsTUI()
    app.articles = [{"title": "Story A", "url": "https://a.com/1"}]
    out_path = tmp_path / "out.md"
    # prompts: format (a=md), path, title, include-all
    prompts = iter(["a", str(out_path), "", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    app._export_loaded()
    assert out_path.exists()
    assert "Story A" in out_path.read_text()


def test_export_loaded_clusters_json(monkeypatch, tmp_path):
    import json

    app = tui.OpenNewsTUI()
    app.articles = [{"title": "Story", "url": "https://a.com"}]
    app.clusters = [{
        "id": 0, "label": "Story", "size": 1, "sources": [],
        "score": 0.0, "representative": app.articles[0],
        "articles": app.articles,
    }]
    out_path = tmp_path / "out.json"
    # prompts: what (b=clusters), format (b=json), path
    prompts = iter(["b", "b", str(out_path)])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    app._export_loaded()
    data = json.loads(out_path.read_text())
    assert data["kind"] == "clusters"


def test_export_loaded_articles_only_skips_what_prompt(monkeypatch, tmp_path):
    """When only articles are loaded, 'export what' is not asked."""
    app = tui.OpenNewsTUI()
    app.articles = [{"title": "Solo", "url": "https://a.com/1"}]
    out_path = tmp_path / "out.md"
    # prompts: format, path, title, include-all (4, not 5)
    prompts = iter(["a", str(out_path), "", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))
    app._export_loaded()
    assert out_path.exists()