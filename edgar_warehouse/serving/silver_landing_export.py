"""Landing-zone export buffer for Snowflake-native silver.

silver-snowflake-migration map, Ticket 01: the landing zone is fed by
exactly the rows a command parses and hands to `SilverDatabase`'s
merge_*/upsert_* methods this run -- not a full re-read of the local
silver.duckdb (which would re-export rows that were already exported by an
earlier run, defeating "append-only" the moment two runs overlap in
content). `SilverDatabase` is the single chokepoint every one of those
methods lives on, so this buffer attaches there via decorators
(`track_landing_rows`/`track_landing_row`/`track_landing_accounting_flag_scores`
below) rather than requiring changes at every external call site.

Opt-in and a complete no-op by default: `SilverDatabase(db_path)` with no
`landing_export` argument behaves exactly as it does today -- every
decorated method checks `self.landing_export is not None` before doing
anything, so existing callers (and the 2000+ tests exercising them) are
unaffected.
"""
from __future__ import annotations

import functools
import inspect
from collections import defaultdict
from typing import Any, Callable


class LandingExportBuffer:
    """Accumulates the rows a single command run wrote to silver, per landing table.

    Keyed by lowercase landing table name (matching
    `generate_silver_landing_ddl.py`'s table-name convention). Flushed to
    Parquet + a run manifest at the end of a command by
    `edgar_warehouse.serving.silver_landing_writer.flush_landing_export`.
    """

    def __init__(self) -> None:
        self._rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def record(self, table_name: str, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._rows[table_name].extend(rows)

    def tables(self) -> dict[str, list[dict[str, Any]]]:
        """A snapshot dict of {table_name: rows}, table names with zero rows omitted."""
        return {name: rows for name, rows in self._rows.items() if rows}

    def row_count(self, table_name: str) -> int:
        return len(self._rows.get(table_name, ()))

    def total_row_count(self) -> int:
        return sum(len(rows) for rows in self._rows.values())


def track_landing_rows(table_name: str) -> Callable:
    """Decorator for merge_*(rows: list[dict], ...) bulk methods.

    Records the `rows` argument into `self.landing_export` after a
    successful call -- if the method raises, nothing is recorded, matching
    "only export what was actually written."
    """

    def decorator(method: Callable) -> Callable:
        sig = inspect.signature(method)

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            result = method(self, *args, **kwargs)
            landing_export = getattr(self, "landing_export", None)
            if landing_export is not None:
                bound = sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                rows = bound.arguments.get("rows")
                if rows:
                    landing_export.record(table_name, rows)
            return result

        return wrapper

    return decorator


def track_landing_row(table_name: str) -> Callable:
    """Decorator variant for upsert_*(row: dict, ...) singular methods."""

    def decorator(method: Callable) -> Callable:
        sig = inspect.signature(method)

        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            result = method(self, *args, **kwargs)
            landing_export = getattr(self, "landing_export", None)
            if landing_export is not None:
                bound = sig.bind(self, *args, **kwargs)
                bound.apply_defaults()
                row = bound.arguments.get("row")
                if row is not None:
                    landing_export.record(table_name, [row])
            return result

        return wrapper

    return decorator


def track_landing_accounting_flag_scores(method: Callable) -> Callable:
    """Decorator for `update_accounting_flag_scores`'s scalar-arg partial backfill.

    That method takes individually-named scalar args (cik, accession_number,
    beneish_m_score, altman_z_score, piotroski_f_score), not a rows/row
    dict, and returns True only when a real row matched (its own
    RETURNING-based success signal -- see its docstring). Records only on a
    real match, and only the five columns this call actually carries; every
    other sec_accounting_flag column is absent from the recorded row. This
    is safe specifically because the dbt silver model for sec_accounting_flag
    uses LAST_VALUE(... IGNORE NULLS) for these three score columns
    (generate_silver_dbt_models.py's _COALESCE_PRESERVING_COLUMNS) -- a
    plain last-row-wins collapse would treat this partial row's absent
    columns as "now NULL" and silently wipe out the rest of the record.
    """
    sig = inspect.signature(method)

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        result = method(self, *args, **kwargs)
        landing_export = getattr(self, "landing_export", None)
        if result and landing_export is not None:
            bound = sig.bind(self, *args, **kwargs)
            bound.apply_defaults()
            a = bound.arguments
            landing_export.record(
                "sec_accounting_flag",
                [
                    {
                        "cik": a["cik"],
                        "accession_number": a["accession_number"],
                        "beneish_m_score": a["beneish_m_score"],
                        "altman_z_score": a["altman_z_score"],
                        "piotroski_f_score": a["piotroski_f_score"],
                    }
                ],
            )
        return result

    return wrapper
