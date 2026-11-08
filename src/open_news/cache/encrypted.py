from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken


class CacheError(Exception):
    """Base exception for cache errors."""


class CacheKeyError(CacheError):
    """Raised when the encryption key is invalid or unavailable."""


class EncryptedCache:
    """
    Encrypted SQLite cache.

    The SQLite database contains:
        - opaque HMAC-derived keys
        - encrypted values
        - expiry metadata

    User identifiers and payloads are never stored in plaintext.
    """

    def __init__(
        self,
        path: str | Path,
        key: Optional[bytes | str] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._fernet = Fernet(self._normalize_key(key))

        self._db = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                namespace TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                value BLOB NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL,
                PRIMARY KEY (namespace, cache_key)
            )
            """
        )
        self._db.commit()

    @staticmethod
    def _normalize_key(key: Optional[bytes | str]) -> bytes:
        if key is None:
            key = os.environ.get("OPEN_NEWS_CACHE_KEY")

        if key is None:
            raise CacheKeyError("OPEN_NEWS_CACHE_KEY is required")

        if isinstance(key, str):
            key = key.encode("utf-8")

        try:
            # Fernet keys are already base64-encoded.
            Fernet(key)
            return key
        except Exception as exc:
            raise CacheKeyError("Invalid Fernet key") from exc

    def _opaque_key(self, namespace: str, key: str) -> str:
        """
        Derive a stable database key without storing the original key.
        """
        digest = hmac.new(
            self._fernet._signing_key,
            f"{namespace}:{key}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return digest

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        payload = json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        encrypted = self._fernet.encrypt(payload)

        expires_at = time.time() + ttl if ttl is not None else None

        opaque_key = self._opaque_key(namespace, key)

        self._db.execute(
            """
            INSERT INTO cache (
                namespace,
                cache_key,
                value,
                expires_at,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(namespace, cache_key)
            DO UPDATE SET
                value = excluded.value,
                expires_at = excluded.expires_at,
                created_at = excluded.created_at
            """,
            (
                namespace,
                opaque_key,
                encrypted,
                expires_at,
                time.time(),
            ),
        )
        self._db.commit()

    def get(
        self,
        namespace: str,
        key: str,
        default: Any = None,
    ) -> Any:
        opaque_key = self._opaque_key(namespace, key)

        row = self._db.execute(
            """
            SELECT value, expires_at
            FROM cache
            WHERE namespace = ?
              AND cache_key = ?
            """,
            (namespace, opaque_key),
        ).fetchone()

        if row is None:
            return default

        encrypted, expires_at = row

        if expires_at is not None and time.time() >= expires_at:
            self.delete(namespace, key)
            return default

        try:
            decrypted = self._fernet.decrypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, ValueError, json.JSONDecodeError):
            # Corrupt/unreadable cache entries must never become
            # trusted user information.
            self.delete(namespace, key)
            return default

    def exists(self, namespace: str, key: str) -> bool:
        sentinel = object()
        return self.get(namespace, key, sentinel) is not sentinel

    def delete(self, namespace: str, key: str) -> None:
        opaque_key = self._opaque_key(namespace, key)

        self._db.execute(
            """
            DELETE FROM cache
            WHERE namespace = ?
              AND cache_key = ?
            """,
            (namespace, opaque_key),
        )
        self._db.commit()

    def clear_namespace(self, namespace: str) -> None:
        self._db.execute(
            "DELETE FROM cache WHERE namespace = ?",
            (namespace,),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "EncryptedCache":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
