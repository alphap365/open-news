from open_news import tui


def test_live_refresh_uses_fetch_stream(monkeypatch, capsys):
    prompts = iter(["tech", "", "3", "5"])
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
