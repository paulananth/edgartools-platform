"""Explore-grade ER data products (not pure-SEC Agent-Grade).

Phase-1 modules:
- ``earnings_calendar`` — ERDP-03 forward earnings calendar (Gold Explore)

Boundary: never inject Explore tables into ``subject_features`` (ADR 0001).
"""

from edgar_warehouse.explore.earnings_calendar import (
    SESSIONS,
    SOURCE_SYSTEMS,
    STATUSES,
    build_earnings_calendar_table,
    current_calendar_rows,
    load_firm_manual_csv,
    load_firm_manual_records,
    map_session,
    mark_reported,
    normalize_calendar_row,
    parse_finnhub_earnings_calendar,
    validate_calendar_rows,
)

__all__ = [
    "SESSIONS",
    "SOURCE_SYSTEMS",
    "STATUSES",
    "build_earnings_calendar_table",
    "current_calendar_rows",
    "load_firm_manual_csv",
    "load_firm_manual_records",
    "map_session",
    "mark_reported",
    "normalize_calendar_row",
    "parse_finnhub_earnings_calendar",
    "validate_calendar_rows",
]
