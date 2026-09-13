from open_news import tui


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
    """v1.0.2: menu 10's [b] keyword branch drives stream_search(), the
    previous gap where only category/location fetch could be watched live."""
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