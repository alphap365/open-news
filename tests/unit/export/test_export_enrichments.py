import csv
import io
import json

from open_news import to_csv, to_jsonld


def _article(**overrides):
    article = {
        "title": "AI news",
        "url": "https://example.com/ai",
        "description": "A report about AI.",
        "summary": "Short summary.",
        "text": "Full article body.",
        "category": "Science",
        "language": "en",
        "source": "Example News",
    }
    article.update(overrides)
    return article


def _cluster(**overrides):
    article = _article()
    cluster = {
        "id": 1,
        "label": "AI policy update",
        "size": 2,
        "score": 0.9,
        "sources": ["Example News", "Other News"],
        "first_seen": "2026-11-10",
        "last_seen": "2026-11-11",
        "representative": article,
        "articles": [article],
    }
    cluster.update(overrides)
    return cluster


def _jsonld_item(items):
    return json.loads(to_jsonld(items))["itemListElement"][0]["item"]


def test_jsonld_emits_identity_language_and_section():
    article = _jsonld_item([_article()])

    assert article["@id"] == "https://example.com/ai"
    assert article["mainEntityOfPage"] == {
        "@type": "WebPage",
        "@id": "https://example.com/ai",
    }
    assert article["inLanguage"] == "en"
    assert article["articleSection"] == "Science"


def test_jsonld_reads_language_from_meta():
    article = _jsonld_item([_article(language=None, meta={"inLanguage": "fr"})])

    assert article["inLanguage"] == "fr"


def test_jsonld_omits_identity_fields_without_a_url():
    article = _jsonld_item([_article(url=None)])

    assert "@id" not in article
    assert "mainEntityOfPage" not in article


def test_jsonld_cluster_includes_date_range():
    article = _jsonld_item([_cluster()])
    properties = {
        entry["name"]: entry["value"] for entry in article["additionalProperty"]
    }

    assert properties["firstSeen"] == "2026-11-10"
    assert properties["lastSeen"] == "2026-11-11"


def test_csv_includes_language_and_summary_columns():
    rows = list(csv.DictReader(io.StringIO(to_csv([_article()]))))

    assert rows[0]["language"] == "en"
    assert rows[0]["summary"] == "Short summary."
