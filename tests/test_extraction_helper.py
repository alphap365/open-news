from open_news.core.strategies import _clean_author_name, _valid_date
from datetime import datetime, timedelta

def test_clean_author_name():
    assert _clean_author_name("By John Doe") == "John Doe"
    assert _clean_author_name("Jane Smith, Staff Writer") == "Jane Smith"
    assert _clean_author_name("X") is None          # too short → None
    assert _clean_author_name("John123") is None    # contains digits

def test_valid_date():
    assert _valid_date(datetime(1990, 1, 1)) is None
    future = datetime.now() + timedelta(days=10)
    assert _valid_date(future) is None
    valid = datetime.now()
    assert _valid_date(valid) == valid