from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Protocol

from ..cache import UserProfile, load_user_profile
from .cluster import DEFAULT_THRESHOLD as DEFAULT_CLUSTER_THRESHOLD
from .cluster import cluster_articles, cluster_to_article

logger = logging.getLogger(__name__)

# Scoring weights for personalized feeds. They sum to 1.0 and are exposed
# through FeedConfig so applications can tune them per deployment.
DEFAULT_FEED_WEIGHTS: dict[str, float] = {
    "interest": 0.55,
    "category": 0.15,
    "language": 0.10,
    "source": 0.10,
    "freshness": 0.10,
}


class FeedCache(Protocol):
    """Minimal cache interface accepted by personalized feed generation."""

    def get(self, namespace: str, key: str, default: Any = None) -> Any: ...

    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None: ...


class FeedCacheDeletable(FeedCache, Protocol):
    """A FeedCache backend that can also invalidate entries.

    ``FeedEngine.clear_cached_feed()`` uses this when available and reports
    ``False`` for backends that only implement ``get``/``set``.
    """

    def delete(self, namespace: str, key: str) -> None: ...


class FeedError(Exception):
    """Base FeedEngine exception."""


class FeedProfileRequiredError(FeedError):
    """
    Raised when personalized feed generation requires
    a valid cached user profile.
    """


@dataclass(frozen=True)
class FeedConfig:
    """Feed generation settings.

    Defaults reproduce the pre-1.0.7b1 behaviour exactly; the added fields
    only give applications a way to tune clustering and scoring.
    """

    cache_ttl: int = 300
    max_items: int = 50
    cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD
    drop_singletons: bool = False
    weights: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FEED_WEIGHTS)
    )

    def __post_init__(self) -> None:
        if self.cache_ttl < 0:
            raise ValueError("cache_ttl must be non-negative")
        if self.max_items < 0:
            raise ValueError("max_items must be non-negative")
        if not 0.0 <= self.cluster_threshold <= 1.0:
            raise ValueError("cluster_threshold must be between 0 and 1")
        supplied = dict(self.weights or {})
        unknown = set(supplied) - set(DEFAULT_FEED_WEIGHTS)
        if unknown:
            raise ValueError(f"unknown feed weight(s): {sorted(unknown)}")
        merged = dict(DEFAULT_FEED_WEIGHTS)
        merged.update({key: float(value) for key, value in supplied.items()})
        if any(value < 0 for value in merged.values()):
            raise ValueError("feed weights must be non-negative")
        object.__setattr__(self, "weights", merged)


class FeedEngine:
    """
    Feed generation engine.

    Personalized feeds require a valid UserProfile in the
    encrypted cache.

    Generic feeds can be generated without user data.
    """

    def __init__(
        self,
        cache: FeedCache | None = None,
        config: FeedConfig | None = None,
    ) -> None:
        self.cache = cache
        self.config = config or FeedConfig()

    def build(
        self,
        articles: Iterable[dict[str, Any]],
        *,
        user_id: str | None = None,
        personalized: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        clusters = cluster_articles(
            [dict(article) for article in articles],
            threshold=self.config.cluster_threshold,
            drop_singletons=self.config.drop_singletons,
            sort_by="date",
        )
        articles = [cluster_to_article(cluster) for cluster in clusters]

        if not articles:
            return []

        profile = None

        if personalized:
            if not user_id:
                raise FeedProfileRequiredError(
                    "user_id is required for personalized feeds"
                )
            if self.cache is None:
                raise FeedProfileRequiredError(
                    "A cache backend is required for personalized feeds"
                )

            profile = load_user_profile(
                self.cache,
                user_id,
            )

            if profile is None:
                raise FeedProfileRequiredError(
                    f"No valid cached profile for user {user_id!r}"
                )

        if profile is None:
            ranked = self._rank_generic(articles)
        else:
            ranked = self._rank_personalized(
                articles,
                profile,
            )

        result_limit = limit if limit is not None else self.config.max_items

        result = ranked[: max(result_limit, 0)]

        if personalized and user_id:
            self._cache_result(
                user_id,
                result,
            )

        return result

    def get_cached_feed(
        self,
        user_id: str,
        *,
        validate: bool = True,
        max_age: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the cached feed for ``user_id``.

        With ``validate=True`` (the default) an entry whose stored
        ``generated_at`` is older than ``max_age`` seconds — or than
        ``config.cache_ttl`` when ``max_age`` is omitted — is treated as
        missing. This matters for FeedCache backends that ignore the TTL they
        are handed, which the engine cannot otherwise detect.
        """
        if self.cache is None:
            raise FeedError("A cache backend is required to read cached feeds")
        cached = self.cache.get(
            "calculated_feed",
            user_id,
        )
        if not validate or not isinstance(cached, dict):
            return cached

        ttl = self.config.cache_ttl if max_age is None else max_age
        generated_at = cached.get("generated_at")
        if not isinstance(generated_at, (int, float)):
            logger.debug("cached feed for %r has no usable generated_at", user_id)
            return None
        if time.time() - float(generated_at) > ttl:
            logger.debug("cached feed for %r is older than %ss", user_id, ttl)
            return None
        return cached

    def clear_cached_feed(self, user_id: str) -> bool:
        """Delete the cached feed for ``user_id``.

        Returns ``False`` when the cache backend cannot delete entries
        (it only implements ``get``/``set``).
        """
        if self.cache is None:
            raise FeedError("A cache backend is required to clear cached feeds")
        delete = getattr(self.cache, "delete", None)
        if not callable(delete):
            return False
        delete("calculated_feed", user_id)
        return True

    def _rank_generic(
        self,
        articles: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        scored = []

        for article in articles:
            item = dict(article)

            freshness = self._freshness_score(
                article.get("last_seen")
                or article.get("published_at")
                or article.get("published")
            )

            item["_feed_score"] = freshness

            scored.append(item)

        return sorted(
            scored,
            key=lambda item: item["_feed_score"],
            reverse=True,
        )

    def _rank_personalized(
        self,
        articles: list[dict[str, Any]],
        profile: UserProfile,
    ) -> list[dict[str, Any]]:
        interests = self._normalize(profile.interests)

        categories = self._normalize(profile.categories)

        preferred_languages = self._normalize(profile.languages)

        preferred_sources = self._normalize(profile.preferred_sources)

        blocked_sources = self._normalize(profile.blocked_sources)

        weights = self.config.weights

        scored: list[dict[str, Any]] = []

        for article in articles:
            stripped = self._strip_blocked_sources(article, blocked_sources)
            if stripped is None:
                continue
            article, coverage = stripped

            source_names = self._coverage_sources(coverage)
            article_languages = self._coverage_languages(coverage)
            article_categories = self._coverage_categories(coverage)
            text = self._coverage_text(coverage)

            interest_score = self._token_overlap(
                text,
                interests,
            )

            category_score = self._set_overlap(
                article_categories,
                categories,
            )

            language_score = (
                1.0 if article_languages.intersection(preferred_languages) else 0.0
            )

            source_score = 1.0 if source_names.intersection(preferred_sources) else 0.0

            freshness_score = self._freshness_score(
                article.get("last_seen")
                or article.get("published_at")
                or article.get("published")
            )

            score = (
                interest_score * weights["interest"]
                + category_score * weights["category"]
                + language_score * weights["language"]
                + source_score * weights["source"]
                + freshness_score * weights["freshness"]
            )

            item = dict(article)
            item["_feed_score"] = round(
                score,
                6,
            )

            scored.append(item)

        return sorted(
            scored,
            key=lambda item: (
                item["_feed_score"],
                str(
                    item.get("last_seen")
                    or item.get("published_at")
                    or item.get("published", "")
                ),
            ),
            reverse=True,
        )

    # ------------------------------------------------------------------
    # Blocked-source handling
    # ------------------------------------------------------------------

    def _strip_blocked_sources(
        self,
        article: dict[str, Any],
        blocked_sources: set[str],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        """Remove blocked outlets from a story.

        Blocked coverage is dropped from ``similar_articles`` and ``sources``.
        When the representative itself comes from a blocked outlet the first
        allowed related article is promoted in its place; the story is dropped
        only when no usable source remains.
        """
        if not blocked_sources:
            return article, self._coverage(article)

        primary = dict(article)
        related = [member for member in self._coverage(primary)[1:]]

        kept = [
            member
            for member in related
            if not self._member_blocked(member, blocked_sources)
        ]

        if self._member_blocked(primary, blocked_sources):
            if not kept:
                return None
            promoted = dict(kept[0])
            remaining = kept[1:]
            for key in ("cluster_id", "cluster_score", "first_seen", "last_seen"):
                if key in primary and key not in promoted:
                    promoted[key] = primary[key]
            primary = promoted
            kept = remaining

        if kept:
            primary["similar_articles"] = kept
        else:
            primary.pop("similar_articles", None)

        declared = primary.get("sources")
        if isinstance(declared, list):
            allowed = [
                name
                for name in declared
                if self._normalize_one(name) not in blocked_sources
            ]
            if allowed:
                primary["sources"] = allowed
            else:
                primary.pop("sources", None)

        if "cluster_size" in primary or kept:
            primary["cluster_size"] = 1 + len(kept)

        return primary, [primary, *kept]

    @staticmethod
    def _coverage(article: dict[str, Any]) -> list[dict[str, Any]]:
        members = [article]
        related = article.get("similar_articles")
        if isinstance(related, list):
            members.extend(member for member in related if isinstance(member, dict))
        return members

    @classmethod
    def _member_blocked(
        cls,
        member: dict[str, Any],
        blocked_sources: set[str],
    ) -> bool:
        """A member is blocked when its own outlet is blocked.

        A story's ``sources`` lists every outlet covering it, so it cannot
        decide whether *this* member came from a blocked outlet; the member's
        own ``source`` (or ``meta.site_name``) does. Members with no outlet
        identity fall back to "all declared sources are blocked".
        """
        primary = cls._normalize_one(member.get("source"))
        meta = member.get("meta")
        if not primary and isinstance(meta, dict):
            primary = cls._normalize_one(meta.get("site_name"))
        if primary:
            return primary in blocked_sources
        names = cls._normalize(member.get("sources", []))
        return bool(names) and names.issubset(blocked_sources)

    @classmethod
    def _member_sources(cls, member: dict[str, Any]) -> set[str]:
        names = cls._normalize(member.get("sources", []))
        primary = cls._normalize_one(member.get("source"))
        if primary:
            names.add(primary)
        meta = member.get("meta")
        if isinstance(meta, dict):
            site_name = cls._normalize_one(meta.get("site_name"))
            if site_name:
                names.add(site_name)
        return names

    @classmethod
    def _coverage_sources(cls, coverage: list[dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        for member in coverage:
            names |= cls._member_sources(member)
        return names

    @classmethod
    def _coverage_languages(cls, coverage: list[dict[str, Any]]) -> set[str]:
        languages: set[str] = set()
        for member in coverage:
            languages |= cls._member_languages(member)
        return languages

    @classmethod
    def _member_languages(cls, member: dict[str, Any]) -> set[str]:
        languages: set[str] = set()
        code = cls._language_code(member.get("language"))
        if code:
            languages.add(code)
        meta = member.get("meta")
        if isinstance(meta, dict):
            for key in ("language", "inLanguage"):
                code = cls._language_code(meta.get(key))
                if code:
                    languages.add(code)
        return languages

    @staticmethod
    def _language_code(value: Any) -> str:
        """Reduce 'en-GB'/'en_GB' to 'en' so profile codes match."""
        if not value:
            return ""
        return str(value).strip().lower().split("-")[0].split("_")[0]

    @classmethod
    def _coverage_categories(cls, coverage: list[dict[str, Any]]) -> set[str]:
        categories: set[str] = set()
        for member in coverage:
            categories |= cls._member_categories(member)
        return categories

    @classmethod
    def _member_categories(cls, member: dict[str, Any]) -> set[str]:
        # The extractor writes `category` (singular); `categories` is accepted
        # for callers that pre-normalise records into lists.
        categories = cls._normalize(member.get("category"))
        categories |= cls._normalize(member.get("categories"))
        return categories

    @classmethod
    def _coverage_text(cls, coverage: list[dict[str, Any]]) -> str:
        return cls._normalize_one(
            " ".join(
                str(member.get(field, ""))
                for field in (
                    "title",
                    "description",
                    "summary",
                )
                for member in coverage
            )
        )

    @staticmethod
    def _normalize(
        values: Any,
    ) -> set[str]:
        if isinstance(values, str):
            values = [values]

        if not isinstance(values, Iterable):
            return set()

        return {str(value).strip().lower() for value in values if str(value).strip()}

    @staticmethod
    def _normalize_one(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        return str(value).strip().lower()

    @staticmethod
    def _token_overlap(
        text: str,
        terms: set[str],
    ) -> float:
        if not text or not terms:
            return 0.0

        tokens = set(text.lower().split())

        if not tokens:
            return 0.0

        return min(
            len(tokens.intersection(terms)) / max(len(terms), 1),
            1.0,
        )

    @staticmethod
    def _set_overlap(
        values: set[str],
        wanted: set[str],
    ) -> float:
        if not values or not wanted:
            return 0.0

        return min(
            len(values.intersection(wanted)) / max(len(wanted), 1),
            1.0,
        )

    @staticmethod
    def _freshness_score(
        published_at: Any,
    ) -> float:
        if not published_at:
            return 0.0

        try:
            if isinstance(
                published_at,
                datetime,
            ):
                published = published_at

            else:
                published = datetime.fromisoformat(
                    str(published_at).replace("Z", "+00:00")
                )

            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)

            age_hours = max(
                (datetime.now(timezone.utc) - published).total_seconds() / 3600,
                0,
            )

            return math.exp(-age_hours / 48)

        except (ValueError, TypeError):
            return 0.0

    def _cache_result(
        self,
        user_id: str,
        result: list[dict[str, Any]],
    ) -> None:
        if self.cache is None:
            raise FeedError("A cache backend is required to cache personalized feeds")
        self.cache.set(
            "calculated_feed",
            user_id,
            {
                "generated_at": time.time(),
                "items": result,
            },
            ttl=self.config.cache_ttl,
        )
