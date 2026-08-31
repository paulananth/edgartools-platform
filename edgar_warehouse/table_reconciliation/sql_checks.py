"""Low-level SQL primitives shared by the table-reconciliation collector.

Every function here takes a duck-typed ``reader`` -- anything satisfying
``.fetch(sql, params) -> list[dict]`` (``SilverDatabase``,
``ShardedSilverReader``, ``SnowflakeSilverReader`` all already implement
this protocol; see ``edgar_warehouse/mdm/resolvers/base.py``'s
``SilverReader`` Protocol for the canonical shape). This keeps the module
usable against either store without a dialect branch, and testable against
a plain in-memory fake.

Identifiers are validated (rejecting anything that isn't a plain
alphanumeric/underscore token) but deliberately embedded **unquoted**, not
double-quoted. Confirmed live against real Snowflake (2026-08-31,
``EDGARTOOLS_PROD.EDGARTOOLS_SILVER``): every object here was created
unquoted and Snowflake folds unquoted identifiers to uppercase at creation
time, so a double-quoted lowercase reference (``"sec_company"``) is a
case-sensitive literal that does not match the real ``SEC_COMPANY`` object
and fails with "does not exist or not authorized" -- an unquoted reference
resolves through Snowflake's normal case-insensitive folding instead, and
was confirmed live to return real rows. DuckDB's own tables (``_DDL`` in
``silver_store.py``, also created unquoted) are case-insensitive for
lookups either way, so the same unquoted form works unchanged on that side
too -- confirmed directly (bare, quoted-lowercase, and uppercase references
all resolved identically against an in-memory DuckDB fixture).
"""
from __future__ import annotations

import re
from typing import Any, Protocol

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Reader(Protocol):
    def fetch(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]: ...


def safe_identifier(identifier: str) -> str:
    """Validates `identifier` is a plain token safe to embed unquoted in
    SQL text, and returns it unchanged. Raises on anything else -- this is
    the only defense against SQL injection here, since these functions
    build query text by interpolation rather than parameterizing
    identifiers (SQL does not support binding identifiers as parameters).
    """
    if not _SAFE_IDENTIFIER.match(identifier):
        raise ValueError(f"invalid SQL identifier: {identifier!r}")
    return identifier


def table_exists(reader: Reader, table: str, *, information_schema: bool = False) -> bool:
    """``information_schema=True`` for Snowflake (no ``duckdb_tables()``
    there); ``False`` (default) for DuckDB.
    """
    if information_schema:
        rows = reader.fetch(
            "SELECT 1 AS present FROM information_schema.tables WHERE table_name = ? LIMIT 1",
            [table.upper()],
        )
    else:
        rows = reader.fetch(
            "SELECT 1 AS present FROM duckdb_tables() WHERE table_name = ? LIMIT 1",
            [table],
        )
    return bool(rows)


def count_rows(reader: Reader, table: str) -> int:
    rows = reader.fetch(f"SELECT COUNT(*) AS row_count FROM {safe_identifier(table)}")
    return int(rows[0]["row_count"])


def orphan_count(
    reader: Reader,
    *,
    child_table: str,
    child_column: str,
    parent_table: str,
    parent_column: str,
) -> int:
    rows = reader.fetch(
        f"""
        SELECT COUNT(*) AS orphan_count
        FROM {safe_identifier(child_table)} child
        LEFT JOIN {safe_identifier(parent_table)} parent
          ON child.{safe_identifier(child_column)} = parent.{safe_identifier(parent_column)}
        WHERE child.{safe_identifier(child_column)} IS NOT NULL
          AND parent.{safe_identifier(parent_column)} IS NULL
        """
    )
    return int(rows[0]["orphan_count"])


def duplicate_key_group_count(reader: Reader, table: str, key_columns: tuple[str, ...]) -> int:
    """Count of distinct key-tuples that appear more than once -- proves
    (or disproves) the declared business key is actually unique. Zero is
    the only passing value; the declared primary key is a *should-be*
    invariant, not something the store enforces for us on the Snowflake
    side (a dynamic table has no unique constraint at all).
    """
    cols = ", ".join(safe_identifier(c) for c in key_columns)
    rows = reader.fetch(
        f"""
        SELECT COUNT(*) AS duplicate_group_count
        FROM (
            SELECT {cols}
            FROM {safe_identifier(table)}
            GROUP BY {cols}
            HAVING COUNT(*) > 1
        ) dupes
        """
    )
    return int(rows[0]["duplicate_group_count"])


def max_authority_value(reader: Reader, table: str, authority_column: str) -> Any:
    rows = reader.fetch(
        f"SELECT MAX({safe_identifier(authority_column)}) AS max_value FROM {safe_identifier(table)}"
    )
    return rows[0]["max_value"] if rows else None


def fetch_key_cohort(
    reader: Reader,
    table: str,
    key_columns: tuple[str, ...],
    *,
    limit: int,
    where_sql: str | None = None,
    where_params: list[Any] | None = None,
) -> list[tuple[Any, ...]]:
    """Deterministic key-tuple sample: boundary rows (min and max by the
    declared key ordering) plus a stable-hash-ordered fill to `limit`,
    mirroring the Bounded Idempotency Rerun's own "boundary... plus
    remaining slots filled by stable hash order" selection shape
    (``docs/release-readiness/maxconcurrency4-data-integrity-proof.md``).
    Returns fewer than `limit` rows if the table has fewer distinct keys.
    """
    cols = ", ".join(safe_identifier(c) for c in key_columns)
    where_clause = f"WHERE {where_sql}" if where_sql else ""
    params = list(where_params or [])

    # Two separate ordered queries, not a UNION of them -- a UNION's output
    # row order across its branches is not guaranteed stable run to run
    # (confirmed empirically: DuckDB returned min-then-max on one call and
    # max-then-min on the next for an identical query), which would make
    # this "deterministic" cohort selection silently non-deterministic.
    min_row = reader.fetch(
        f"SELECT {cols} FROM {safe_identifier(table)} {where_clause} ORDER BY {cols} ASC LIMIT 1",
        params,
    )
    max_row = reader.fetch(
        f"SELECT {cols} FROM {safe_identifier(table)} {where_clause} ORDER BY {cols} DESC LIMIT 1",
        params,
    )
    boundary_keys = [tuple(row[c] for c in key_columns) for row in (min_row + max_row)]

    fill_needed = max(limit - len(boundary_keys), 0)
    fill_keys: list[tuple[Any, ...]] = []
    if fill_needed:
        hash_expr = " || '|' || ".join(f"CAST({safe_identifier(c)} AS VARCHAR)" for c in key_columns)
        rows = reader.fetch(
            f"""
            SELECT {cols}
            FROM {safe_identifier(table)}
            {where_clause}
            ORDER BY MD5({hash_expr})
            LIMIT ?
            """,
            params + [fill_needed],
        )
        fill_keys = [tuple(row[c] for c in key_columns) for row in rows]

    seen: set[tuple[Any, ...]] = set()
    ordered: list[tuple[Any, ...]] = []
    for key in boundary_keys + fill_keys:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def fetch_rows_by_keys(
    reader: Reader,
    table: str,
    key_columns: tuple[str, ...],
    keys: list[tuple[Any, ...]],
    *,
    select_columns: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Fetch full rows for an explicit set of key-tuples (the cohort
    ``fetch_key_cohort`` selected). Empty ``keys`` returns ``[]`` without a
    query.
    """
    if not keys:
        return []
    columns_sql = "*" if not select_columns else ", ".join(safe_identifier(c) for c in select_columns)
    key_cols_sql = ", ".join(safe_identifier(c) for c in key_columns)
    placeholders = ", ".join("(" + ", ".join("?" for _ in key_columns) + ")" for _ in keys)
    flat_params: list[Any] = [value for key in keys for value in key]
    rows = reader.fetch(
        f"""
        SELECT {columns_sql}
        FROM {safe_identifier(table)}
        WHERE ({key_cols_sql}) IN ({placeholders})
        """,
        flat_params,
    )
    return rows
