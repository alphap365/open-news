"""Pure query-string helpers for the Google News engine.

No network, no side effects — safe to import and call from anywhere.
The public entry point (``search_raw``) delegates here for the
``q=...`` param, then adds the locale params itself.
"""

from ...config import SearchConfig


_TIME_LIMIT_TO_GNEWS = {"d": "1d", "w": "7d", "m": "30d"}


def _build_query(config: SearchConfig) -> str:
    """Assemble the ``q=`` search string for Google News RSS.

    Handles:
      * ``query_mode`` — 'any' (default), 'all' (explicit AND), or
        'exact_phrase' (double-quoted).
      * ``exclude_terms`` — prefixed with ``-`` and space-separated.
      * Custom date range — ``after:YYYY-MM-DD`` / ``before:YYYY-MM-DD``
        operators, which Google News RSS supports natively. Takes
        precedence over the coarse ``time_limit`` window.
      * ``time_limit`` — mapped to Google's ``when:`` operator.
    """
    query = config.query
    if config.query_mode == "exact_phrase":
        query = f'"{query}"'
    elif config.query_mode == "all":
        # Google News RSS treats space-separated bare terms as implicit
        # AND already; being explicit costs nothing and documents intent.
        query = " AND ".join(query.split())
    # "any" mode: leave as-is, engine's default OR-ish relevance applies.

    if config.exclude_terms:
        query += " " + " ".join(f"-{t}" for t in config.exclude_terms)

    if config.start_date or config.end_date:
        if config.start_date:
            query += f" after:{config.start_date}"
        if config.end_date:
            query += f" before:{config.end_date}"
    else:
        when = _TIME_LIMIT_TO_GNEWS.get(config.time_limit)
        if when:
            query += f" when:{when}"

    return query