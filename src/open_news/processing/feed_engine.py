from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol

from ..cache import UserProfile, load_user_profile
from .cluster import cluster_articles, cluster_to_article


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


class FeedError(Exception):
    """Base FeedEngine exception."""


class FeedProfileRequiredError(FeedError):
    """
    Raised when personalized feed generation requires
    a valid cached user profile.
    """


@dataclass(frozen=True)
class FeedConfig:
    cache_ttl: int = 300
    max_items: int = 50


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

        result = ranked[:result_limit]

        if personalized and user_id:
            self._cache_result(
                user_id,
                result,
            )

        return result

    def get_cached_feed(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        if self.cache is None:
            raise FeedError("A cache backend is required to read cached feeds")
        return self.cache.get(
            "calculated_feed",
            user_id,
        )

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

        scored: list[dict[str, Any]] = []

        for article in articles:
            related = article.get("similar_articles")
            coverage = [article]
            if isinstance(related, list):
                coverage.extend(
                    member for member in related if isinstance(member, dict)
                )
            source_names = self._normalize(article.get("sources", []))
            primary_source = self._normalize_one(article.get("source"))
            if primary_source:
                source_names.add(primary_source)

            article_languages = {
                self._normalize_one(member.get("language"))
                for member in coverage
                if member.get("language")
            }
            article_categories = {
                category
                for member in coverage
                for category in self._normalize(member.get("categories", []))
            }

            text = self._normalize_one(
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

            if source_names and source_names.issubset(blocked_sources):
                continue

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
                interest_score * 0.55
                + category_score * 0.15
                + language_score * 0.10
                + source_score * 0.10
                + freshness_score * 0.10
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
