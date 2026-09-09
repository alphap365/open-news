from dataclasses import dataclass, field
from typing import List, Optional

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

    def __post_init__(self):
        super().__post_init__()
        if not self.query.strip():
            raise ValueError("query must be a non-empty string")
        _validate_choice(self.query_mode, VALID_QUERY_MODES, "query_mode")
        _validate_choice(self.sort_by, VALID_SORT_SEARCH, "sort_by")