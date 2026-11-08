from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROFILE_SCHEMA = 1


class InvalidUserProfile(ValueError):
    """Raised when cached user data is invalid."""


@dataclass(frozen=True)
class UserProfile:
    user_id: str

    interests: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    preferred_sources: tuple[str, ...] = ()
    blocked_sources: tuple[str, ...] = ()

    schema_version: int = PROFILE_SCHEMA

    def validate(self) -> None:
        if self.schema_version != PROFILE_SCHEMA:
            raise InvalidUserProfile("Unsupported user profile schema")

        if not self.user_id.strip():
            raise InvalidUserProfile("user_id is required")

        if len(self.user_id) > 256:
            raise InvalidUserProfile("user_id is too long")

        for field_name in (
            "interests",
            "categories",
            "languages",
            "preferred_sources",
            "blocked_sources",
        ):
            values = getattr(self, field_name)

            if not isinstance(values, tuple):
                raise InvalidUserProfile(f"{field_name} must be a tuple")

            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise InvalidUserProfile(f"{field_name} contains invalid values")

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "schema_version": self.schema_version,
            "user_id": self.user_id,
            "interests": list(self.interests),
            "categories": list(self.categories),
            "languages": list(self.languages),
            "preferred_sources": list(self.preferred_sources),
            "blocked_sources": list(self.blocked_sources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        if not isinstance(data, dict):
            raise InvalidUserProfile("Profile must be an object")

        profile = cls(
            user_id=str(data.get("user_id", "")),
            interests=tuple(data.get("interests", [])),
            categories=tuple(data.get("categories", [])),
            languages=tuple(data.get("languages", [])),
            preferred_sources=tuple(data.get("preferred_sources", [])),
            blocked_sources=tuple(data.get("blocked_sources", [])),
            schema_version=int(data.get("schema_version", 0)),
        )

        profile.validate()
        return profile


def store_user_profile(
    cache: Any,
    profile: UserProfile,
) -> None:
    profile.validate()

    cache.set(
        "user_profile",
        profile.user_id,
        profile.to_dict(),
    )


def load_user_profile(
    cache: Any,
    user_id: str,
) -> UserProfile | None:
    data = cache.get(
        "user_profile",
        user_id,
    )

    if data is None:
        return None

    try:
        profile = UserProfile.from_dict(data)

        if profile.user_id != user_id:
            return None

        return profile

    except (InvalidUserProfile, TypeError, ValueError):
        # Never trust malformed cached profile data.
        return None
