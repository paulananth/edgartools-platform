"""Landing-zone export buffer for Snowflake-native silver.

silver-snowflake-migration map, Ticket 01: the landing zone is fed by
exactly the rows a command parses and hands to `SilverDatabase`'s
merge_*/upsert_* methods this run -- not a full re-read of the local
silver.duckdb (which would re-export rows that were already exported by an
earlier run, defeating "append-only" the moment two runs overlap in
content). `SilverDatabase` is the single chokepoint every one of those
methods lives on, so this buffer attaches there via decorators
(`track_landing_rows`/`track_landing_row` below) rather than requiring
changes at every external call site. `update_accounting_flag_scores`
(silver_store.py) records into the buffer directly instead of via a
decorator -- see its docstring for why (silver-retirement-integrity
Ticket 04: it must record the full post-update row, not just its own
scalar arguments).

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

    Keyed by lowercase landing table name (matching the table names in
    `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`, lowercased).
    Flushed to Parquet + a run manifest at the end of a command by
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
