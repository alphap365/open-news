import pytest

@pytest.fixture
def sample_article_dict():
    return {
        "title": "Breaking News: AI takes over",
        "url": "https://example.com/story/2026/01/01/ai",
        "source": "Example News",
        "published": "2026-01-01T12:00:00",
        "description": "A detailed story about AI taking over the world.",
        "text": "This is the full body text. " * 50,
    }

@pytest.fixture
def sample_articles_list(sample_article_dict):
    return [
        {**sample_article_dict, "title": "AI takes over the world", "url": "https://a.com/1"},
        {**sample_article_dict, "title": "AI takes over the world update", "url": "https://b.com/2"},
        {**sample_article_dict, "title": "Different story", "url": "https://c.com/3"},
    ]