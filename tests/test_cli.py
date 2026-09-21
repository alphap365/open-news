import json

import pytest

from open_news.cli import main


# ----------------------------------------------------------------------
# Existing behavior (unchanged)
# ----------------------------------------------------------------------

def test_cli_fetch_parse(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "fetch", "--category", "tech", "--limit", "2"])
    mock_fetch = mocker.patch("open_news.cli.fetch", return_value=[{"title": "Tech Story"}])

    main()
    captured = capsys.readouterr()

    mock_fetch.assert_called_once_with(
        category="tech",
        location=None,
        max_results=2,
        language=None,
        sort_by="date",
        time_limit="d",
        full_content=False,
        js=False,
        whitelist=None,
        blacklist=None,
        dedupe=True,
    )
    assert "Tech Story" in captured.out


def test_cli_extract(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "extract", "http://test.com", "--js"])
    mock_get = mocker.patch("open_news.cli.get_article", return_value={"title": "Extracted"})

    main()
    mock_get.assert_called_once_with("http://test.com", timeout=15, js=True)


# ----------------------------------------------------------------------
# v1.0.5 — topic filtering
# ----------------------------------------------------------------------

def test_cli_fetch_with_topic_filters(mocker, capsys):
    mocker.patch("sys.argv", [
        "open-news", "fetch", "--category", "tech", "--limit", "5",
        "--topic", "AI",
    ])
    mocker.patch("open_news.cli.fetch", return_value=[
        {"title": "AI breakthrough", "url": "https://a.com/1"},
        {"title": "Sports update", "url": "https://b.com/2"},
    ])
    main()
    out = capsys.readouterr().out
    assert "AI breakthrough" in out
    assert "Sports update" not in out


def test_cli_search_with_topic_all_mode(mocker, capsys):
    mocker.patch("sys.argv", [
        "open-news", "search", "climate",
        "--topic", "policy,climate", "--topic-mode", "all",
    ])
    mocker.patch("open_news.cli.search", return_value=[
        {"title": "EU climate policy shift", "url": "https://a.com/1"},
        {"title": "European weather report", "url": "https://b.com/2"},
    ])
    main()
    out = capsys.readouterr().out
    assert "EU climate policy shift" in out
    assert "European weather report" not in out

# ----------------------------------------------------------------------
# v1.0.5 — rank
# ----------------------------------------------------------------------

def test_cli_fetch_with_rank_query_reorders(mocker, capsys):
    mocker.patch("sys.argv", [
        "open-news", "fetch", "--category", "tech", "--limit", "5",
        "--rank-query", "AI", "--rank-method", "basic",
    ])
    mocker.patch("open_news.cli.fetch", return_value=[
        {"title": "Unrelated story", "url": "https://a.com/1"},
        {"title": "AI story AI AI", "url": "https://b.com/2"},
    ])
    main()
    out = capsys.readouterr().out
    assert out.index("AI story AI AI") < out.index("Unrelated story")


# ----------------------------------------------------------------------
# v1.0.5 — exports
# ----------------------------------------------------------------------

def test_cli_search_with_export_md(mocker, tmp_path):
    out_path = tmp_path / "out.md"
    mocker.patch("sys.argv", [
        "open-news", "search", "climate",
        "--export-md", str(out_path),
    ])
    mocker.patch("open_news.cli.search", return_value=[
        {"title": "Climate news", "url": "https://a.com/1"},
    ])
    main()
    assert out_path.exists()
    assert "Climate news" in out_path.read_text()


def test_cli_search_with_export_json(mocker, tmp_path):
    out_path = tmp_path / "out.json"
    mocker.patch("sys.argv", [
        "open-news", "search", "climate",
        "--export-json", str(out_path),
    ])
    mocker.patch("open_news.cli.search", return_value=[
        {"title": "Climate news", "url": "https://a.com/1"},
    ])
    main()
    data = json.loads(out_path.read_text())
    assert data["count"] == 1
    assert data["articles"][0]["title"] == "Climate news"


def test_cli_export_with_custom_title(mocker, tmp_path):
    out_path = tmp_path / "out.md"
    mocker.patch("sys.argv", [
        "open-news", "fetch",
        "--export-md", str(out_path),
        "--export-title", "My Custom Doc",
    ])
    mocker.patch("open_news.cli.fetch", return_value=[
        {"title": "Story", "url": "https://a.com/1"},
    ])
    main()
    assert "# My Custom Doc" in out_path.read_text()


# ----------------------------------------------------------------------
# v1.0.5 — cluster command
# ----------------------------------------------------------------------

def test_cli_cluster_uses_query(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "cluster", "--query", "AI", "--limit", "5"])
    mock_search = mocker.patch("open_news.cli.search", return_value=[
        {"title": "AI story", "url": "https://a.com/1"},
    ])
    mock_cluster = mocker.patch("open_news.cli.cluster_articles", return_value=[
        {"id": 0, "label": "AI story", "size": 1,
         "sources": ["a.com"], "representative": {"title": "AI story"},
         "articles": []},
    ])
    main()
    assert mock_search.called
    assert mock_cluster.called
    out = capsys.readouterr().out
    assert "AI story" in out


def test_cli_cluster_uses_category(mocker, capsys):
    mocker.patch("sys.argv", ["open-news", "cluster", "--category", "tech"])
    mock_fetch = mocker.patch("open_news.cli.fetch", return_value=[])
    mocker.patch("open_news.cli.cluster_articles", return_value=[])
    main()
    assert mock_fetch.called


def test_cli_cluster_requires_source(mocker):
    mocker.patch("sys.argv", ["open-news", "cluster"])
    with pytest.raises(SystemExit):
        main()


# ----------------------------------------------------------------------
# v1.0.5 — export command (re-export a saved JSON file)
# ----------------------------------------------------------------------

def test_cli_export_writes_markdown(mocker, tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps([{"title": "Story A", "url": "https://a.com/1"}]))
    out = tmp_path / "out.md"
    mocker.patch("sys.argv", ["open-news", "export", str(src), "--md", str(out)])
    main()
    assert out.exists()
    assert "Story A" in out.read_text()


def test_cli_export_unwraps_envelope(mocker, tmp_path):
    src = tmp_path / "in.json"
    src.write_text(json.dumps({
        "articles": [{"title": "Story A", "url": "https://a.com/1"}],
        "count": 1, "kind": "articles", "schema_version": "1.0",
    }))
    out = tmp_path / "out.json"
    mocker.patch("sys.argv", ["open-news", "export", str(src), "--json", str(out)])
    main()
    data = json.loads(out.read_text())
    assert data["count"] == 1
    assert data["articles"][0]["title"] == "Story A"


def test_cli_export_requires_output(mocker, tmp_path):
    src = tmp_path / "in.json"
    src.write_text("[]")
    mocker.patch("sys.argv", ["open-news", "export", str(src)])
    with pytest.raises(SystemExit):
        main()