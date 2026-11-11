import csv
import io
import json

from open_news import to_csv, to_jsonld, to_text


def _article(**overrides):
    article = {
        "title": "AI news",
        "url": "https://example.com/ai",
        "description": "A report about AI.",
        "text": "Full article body.",
        "publish_date": "2026-11-11T09:00:00+00:00",
        "source": "Example News",
        "authors": ["Ada Reporter"],
        "keywords": ["AI", "technology"],
        "images": ["https://example.com/image.jpg"],
        "meta": {"site_name": "Example News"},
        "_tier": "internal",
    }
    article.update(overrides)
    return article


def _cluster(article=None):
    article = article or _article()
    return {
        "id": 7,
        "label": "AI policy update",
        "size": 2,
        "score": 0.9,
        "sources": ["Example News", "Other News"],
        "first_seen": "2026-11-11",
        "last_seen": "2026-11-12",
        "representative": article,
        "articles": [article],
    }


def test_text_export_includes_context_and_strips_internal_fields():
    result = to_text([_article()])

    assert "Title: AI news" in result
    assert "URL: https://example.com/ai" in result
    assert "Source: Example News" in result
    assert "Article text:\nFull article body." in result
    assert "_tier" not in result


def test_text_export_handles_clusters_and_text_limits():
    result = to_text([_cluster(_article(text="abcdef"))], max_text_chars=3)

    assert "Story group 1: AI policy update" in result
    assert "Cluster size: 2" in result
    assert "Sources: Example News, Other News" in result
    assert "abc" in result
    assert "abcdef" not in result


def test_text_export_can_omit_body_and_write_file(tmp_path):
    path = tmp_path / "nested" / "news.txt"
    result = to_text([_article()], path=path, include_text=False)

    assert "Article text:" not in result
    assert path.read_text(encoding="utf-8") == result


def test_jsonld_export_uses_schema_org_news_article():
    result = json.loads(to_jsonld([_article()]))

    assert result["@context"] == "https://schema.org"
    assert result["@type"] == "ItemList"
    assert result["numberOfItems"] == 1
    article = result["itemListElement"][0]["item"]
    assert article["@type"] == "NewsArticle"
    assert article["headline"] == "AI news"
    assert article["author"] == [{"@type": "Person", "name": "Ada Reporter"}]
    assert article["publisher"] == {"@type": "Organization", "name": "Example News"}
    assert "_tier" not in article


def test_jsonld_export_maps_cluster_metadata_and_writes_file(tmp_path):
    path = tmp_path / "structured" / "news.jsonld"
    result = to_jsonld([_cluster()], path=path)
    article = json.loads(result)["itemListElement"][0]["item"]
    properties = {item["name"]: item["value"] for item in article["additionalProperty"]}

    assert properties["clusterSize"] == 2
    assert properties["clusterLabel"] == "AI policy update"
    assert path.read_text(encoding="utf-8") == result


def test_csv_export_preserves_nested_values_as_json():
    rows = list(csv.DictReader(io.StringIO(to_csv([_article()]))))

    assert rows[0]["title"] == "AI news"
    assert json.loads(rows[0]["authors"]) == ["Ada Reporter"]
    assert json.loads(rows[0]["keywords"]) == ["AI", "technology"]
    assert rows[0]["text"] == "Full article body."


def test_csv_export_flattens_clusters_and_can_omit_text(tmp_path):
    path = tmp_path / "news.csv"
    result = to_csv([_cluster()], path=path, include_text=False)
    rows = list(csv.DictReader(io.StringIO(result)))

    assert rows[0]["cluster_id"] == "7"
    assert rows[0]["cluster_label"] == "AI policy update"
    assert rows[0]["cluster_size"] == "2"
    assert "text" not in rows[0]
    assert path.read_text(encoding="utf-8") == result


def test_empty_structured_exports_keep_valid_shapes():
    assert to_text([]) == ""
    assert json.loads(to_jsonld([]))["itemListElement"] == []
    assert next(csv.reader(io.StringIO(to_csv([]))))[0] == "cluster_id"
