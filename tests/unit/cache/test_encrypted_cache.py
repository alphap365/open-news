import pytest
from cryptography.fernet import Fernet

from open_news import EncryptedCache


@pytest.fixture
def cache(tmp_path):
    instance = EncryptedCache(tmp_path / "cache.db", key=Fernet.generate_key())
    try:
        yield instance
    finally:
        instance.close()


def test_cache_roundtrip(cache):
    cache.set("ns", "key", {"a": 1})

    assert cache.get("ns", "key") == {"a": 1}
    assert cache.exists("ns", "key") is True


def test_stats_reports_rows_and_namespaces(cache):
    cache.set("one", "a", 1)
    cache.set("two", "b", 2)

    stats = cache.stats()

    assert stats["rows"] == 2
    assert stats["expired"] == 0
    assert stats["namespaces"] == ["one", "two"]


def test_stats_on_empty_cache_is_zeroed(cache):
    assert cache.stats() == {"rows": 0, "expired": 0, "namespaces": []}


def test_stats_counts_expired_rows_before_purge(cache):
    cache.set("ns", "fresh", 1, ttl=60)
    cache.set("ns", "stale", 2, ttl=-1)

    stats = cache.stats()

    assert stats["rows"] == 2
    assert stats["expired"] == 1


def test_purge_expired_removes_only_expired_rows(cache):
    cache.set("ns", "fresh", 1, ttl=60)
    cache.set("ns", "stale", 2, ttl=-1)

    assert cache.purge_expired() == 1
    assert cache.get("ns", "fresh") == 1
    assert cache.get("ns", "stale") is None
    assert cache.stats()["rows"] == 1


def test_purge_expired_is_idempotent(cache):
    cache.set("ns", "stale", 1, ttl=-1)
    cache.purge_expired()

    assert cache.purge_expired() == 0


def test_unreadable_entries_are_evicted(cache):
    cache.set("ns", "key", {"a": 1})
    # Corrupt the stored ciphertext; a readable-but-wrong key would change the
    # opaque lookup key and miss the row entirely instead of testing recovery.
    cache._db.execute("UPDATE cache SET value = ?", (b"not-a-token",))
    cache._db.commit()

    assert cache.get("ns", "key") is None
    assert cache.stats()["rows"] == 0
