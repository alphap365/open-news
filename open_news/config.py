from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Union

VALID_TIME_LIMITS = {"d", "w", "m"}
VALID_SORT_FETCH = {"date", "relevance", "popularity"}
VALID_SORT_SEARCH = {"date", "relevance"}
VALID_OUTPUT_FORMATS = {"json", "markdown"}
VALID_QUERY_MODES = {"any", "all", "exact_phrase"}
VALID_CATEGORIES = {
    "general", "business", "tech", "sports", "health", "science", "entertainment",
}


def _validate_choice(value: str, valid: set, field_name: str) -> str:
    if value not in valid:
        raise ValueError(f"{field_name}={value!r} is invalid; must be one of {sorted(valid)}")
    return value


def _normalize_date(value: Optional[Union[str, date, datetime]], field_name: str) -> Optional[str]:
    """
    Accepts a date/datetime object or a string and returns a plain
    'YYYY-MM-DD' string, or None.

    Accepted string formats: 'YYYY-MM-DD' (preferred) or anything
    `datetime.fromisoformat` understands (e.g. 'YYYY-MM-DDTHH:MM:SS').
    See docs/parameters-reference.md for the full list of accepted inputs.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        if v[-1] in "Zz":
            v = v[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(v).date().isoformat()
        except ValueError:
            raise ValueError(
                f"{field_name}={value!r} is not a valid date; use 'YYYY-MM-DD' "
                f"or an ISO-8601 datetime string"
            )
    raise ValueError(f"{field_name} must be a str, date, or datetime, got {type(value).__name__}")


@dataclass
class BaseDiscoveryConfig:
    """Fields shared by both fetch() and search()."""
    time_limit: str = "d"
    max_results: int = 20
    language: Optional[str] = None
    whitelist: Optional[List[str]] = None
    blacklist: Optional[List[str]] = None
    full_content: bool = False
    search_in: List[str] = field(default_factory=lambda: ["title", "description"])

    def __post_init__(self):
        _validate_choice(self.time_limit, VALID_TIME_LIMITS, "time_limit")
        if self.max_results < 1:
            raise ValueError("max_results must be >= 1")
        bad_fields = set(self.search_in) - {"title", "description", "body"}
        if bad_fields:
            raise ValueError(f"search_in contains unsupported field(s): {bad_fields}")


@dataclass
class FetchConfig(BaseDiscoveryConfig):
    category: str = "general"
    location: Optional[str] = None
    sort_by: str = "date"
    refresh_interval: Optional[int] = None

    def __post_init__(self):
        super().__post_init__()
        _validate_choice(self.category, VALID_CATEGORIES, "category")
        _validate_choice(self.sort_by, VALID_SORT_FETCH, "sort_by")
        if self.refresh_interval is not None and self.refresh_interval < 5:
            raise ValueError("refresh_interval must be >= 5 seconds to avoid hammering the engine")


@dataclass
class SearchConfig(BaseDiscoveryConfig):
    query: str = ""
    query_mode: str = "any"
    exclude_terms: Optional[List[str]] = None
    sort_by: str = "date"
    # Custom date-range search (v1.0.2). When either is set, it takes
    # precedence over `time_limit`'s coarse d/w/m recency window, letting
    # callers ask for e.g. "everything published between two exact dates"
    # instead of just "the last day/week/month". Both are optional and
    # can be used independently (open-ended range).
    start_date: Optional[Union[str, date, datetime]] = None
    end_date: Optional[Union[str, date, datetime]] = None
    # Live/streaming keyword search (v1.0.2) — mirrors fetch()'s
    # refresh_interval. See api.stream_search().
    refresh_interval: Optional[int] = None

    def __post_init__(self):
        super().__post_init__()
        if not self.query.strip():
            raise ValueError("query must be a non-empty string")
        _validate_choice(self.query_mode, VALID_QUERY_MODES, "query_mode")
        _validate_choice(self.sort_by, VALID_SORT_SEARCH, "sort_by")

        self.start_date = _normalize_date(self.start_date, "start_date")
        self.end_date = _normalize_date(self.end_date, "end_date")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError(
                f"start_date ({self.start_date}) must not be after end_date ({self.end_date})"
            )
        if self.refresh_interval is not None and self.refresh_interval < 5:
            raise ValueError("refresh_interval must be >= 5 seconds to avoid hammering the engine")