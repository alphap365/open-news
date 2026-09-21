"""Tests for open_news.export (to_markdown, to_json)."""

import json

from open_news.export import to_json, to_markdown


def _art(title="Story", url="https://example.com/1", **kw):
    return {"title": title, "url": url, **kw}


def _cluster(label="Story", size=2, **kw):
    members = [_art(label), _art(label, url="https://b.com/2")]
    return {
        "id": 0, "label": label, "size": size, "sources": ["A"],
        "score": 1.0, "first_seen": None, "last_seen": None,
        "representative": members[0], "articles": members,
        **kw,
    }


# ----------------------------------------------------------------------
# to_markdown
# ----------------------------------------------------------------------

def test_markdown_empty_returns_string():
    out = to_markdown([])
    assert isinstance(out, str)
    assert "News Export" in out


def test_markdown_contains_titles():
    items = [_art("Alpha story"), _art("Beta story")]
    out = to_markdown(items)
    assert "Alpha story" in out
    assert "Beta story" in out


def test_markdown_writes_to_path(tmp_path):
    out_path = tmp_path / "out.md"
    returned = to_markdown([_art("Hello world")], path=out_path)
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == returned


def test_markdown_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "deeper" / "out.md"
    to_markdown([_art("X")], path=out_path)
    assert out_path.exists()


def test_markdown_toc_when_multiple_items():
    items = [_art("First article"), _art("Second article")]
    out = to_markdown(items, include_toc=True)
    assert "Table of Contents" in out


def test_markdown_no_toc_when_disabled():
    items = [_art("First article"), _art("Second article")]
    out = to_markdown(items, include_toc=False)
    assert "Table of Contents" not in out


def test_markdown_includes_url_link():
    items = [_art("Story", url="https://example.com/a")]
    out = to_markdown(items)
    assert "[Read original](https://example.com/a)" in out


def test_markdown_truncates_long_text():
    items = [_art("Story", text="x" * 10000)]
    out = to_markdown(items, max_text_chars=100)
    assert "x" * 100 in out
    assert "x" * 500 not in out


def test_markdown_cluster_autodetect():
    clusters = [_cluster("Big story", size=3)]
    out = to_markdown(clusters)
    assert "Big story" in out
    assert "Cluster of 3 article(s)" in out
    assert "News Clusters" in out


def test_markdown_cluster_includes_all_members_flag():
    clusters = [_cluster("Story", size=2)]
    with_members = to_markdown(clusters, include_all_members=True)
    without_members = to_markdown(clusters, include_all_members=False)
    assert "Other reports" in with_members
    assert "Other reports" not in without_members


def test_markdown_unicode_preserved():
    out = to_markdown([_art("日本語のニュース")])
    assert "日本語のニュース" in out


def test_markdown_custom_title():
    out = to_markdown([_art("X")], title="Custom Title")
    assert "# Custom Title" in out

def test_markdown_toc_anchor_preserves_unicode():
    items = [_art("पढ़ें 21 सितम्बर के मुख्य समाचार"), _art("Second")]
    out = to_markdown(items)
    # Devanagari word characters survive the slug
    assert "पढ़ें" in out
    assert "(#1-पढ़ें-21" in out or "(#1-" + "पढ़ें" in out
# ----------------------------------------------------------------------
# to_json
# ----------------------------------------------------------------------

def test_json_empty_envelope():
    parsed = json.loads(to_json([]))
    assert parsed["count"] == 0
    assert parsed["articles"] == []


def test_json_envelope_shape():
    items = [_art("Story A"), _art("Story B")]
    parsed = json.loads(to_json(items))
    assert parsed["schema_version"] == "1.0"
    assert parsed["kind"] == "articles"
    assert parsed["count"] == 2
    assert len(parsed["articles"]) == 2


def test_json_cluster_kind():
    parsed = json.loads(to_json([_cluster("Story", size=2)]))
    assert parsed["kind"] == "clusters"
    assert "clusters" in parsed
    assert parsed["count"] == 1


def test_json_strips_internal_keys():
    items = [_art("Story", _tier="google", _field_sources={"a": "b"})]
    parsed = json.loads(to_json(items))
    article = parsed["articles"][0]
    assert "_tier" not in article
    assert "_field_sources" not in article


def test_json_include_internal_keeps_keys():
    items = [_art("Story", _tier="google")]
    parsed = json.loads(to_json(items, include_internal=True))
    assert parsed["articles"][0]["_tier"] == "google"


def test_json_envelope_false_returns_bare_list():
    items = [_art("Story")]
    parsed = json.loads(to_json(items, envelope=False))
    assert isinstance(parsed, list)
    assert parsed[0]["title"] == "Story"


def test_json_writes_to_path(tmp_path):
    out_path = tmp_path / "out.json"
    returned = to_json([_art("Story")], path=out_path)
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8") == returned


def test_json_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "out.json"
    to_json([_art("Story")], path=out_path)
    assert out_path.exists()


def test_json_unicode_preserved():
    out = to_json([_art("日本語のニュース")])
    assert "日本語のニュース" in out


def test_json_extra_meta():
    parsed = json.loads(to_json([_art("Story")], extra_meta={"query": "test"}))
    assert parsed["query"] == "test"