"""edgar_warehouse/silver_schema.py is the DuckDB-free source of each landing
table's column order and NOT NULL set (silver-merge-engine-migration Ticket 13).

Two guards. The first holds the snapshot to the live DuckDB DDL while that
DDL still exists and is deleted with it (Ticket 17). The second holds it to
infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql, the hand-
maintained landing DDL, and outlives the engine: this repo has already lost
a schema's generator twice (that landing DDL, the MDM mirror schema), so the
snapshot is never left with nothing checking it.
"""

from __future__ import annotations

import re
from pathlib import Path

from edgar_warehouse import silver_schema

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDING_SQL = REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "11_silver_landing_schema.sql"

# Columns DuckDB's DDL has that the landing DDL does not (found by this test
# when it was written; recorded, not hidden): migration 011's
# retirement_state_observed_at. No writer stamps it, so it never reaches a
# landing Parquet file. Drop the entry when 11_*.sql gains the column.
_DUCKDB_ONLY_COLUMNS = {
    "sec_accounting_flag": {"retirement_state_observed_at"},
    "sec_financial_fact": {"retirement_state_observed_at"},
}


def _landing_sql_columns() -> dict[str, list[tuple[str, bool]]]:
    """(column, not_null) per landing table, in DDL order, parse_sequence dropped.
    Snowflake forces NOT NULL on PRIMARY KEY columns; the landing DDL keeps
    parse_sequence as the sole PK and DROPs its NOT NULL, so NOT NULL here
    comes only from the column's own declaration."""
    out: dict[str, list[tuple[str, bool]]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", LANDING_SQL.read_text(), re.DOTALL
    ):
        columns = []
        for raw in match.group(2).split("\n"):
            line = raw.split("--")[0].strip().lstrip(",").strip()
            if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE")):
                continue
            columns.append((line.split()[0].lower(), "NOT NULL" in line.upper()))
        out[match.group(1).lower()] = [c for c in columns if c[0] != "parse_sequence"]
    return out


def test_snapshot_matches_the_live_duckdb_ddl():
    """Deleted with the DuckDB engine (Ticket 17)."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(":memory:")
    try:
        for table, columns in silver_schema.COLUMNS.items():
            rows = db._conn.execute(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            assert tuple(c for c, _ in rows) == columns, table
            assert tuple(c for c, n in rows if n == "NO") == silver_schema.REQUIRED[table], table
    finally:
        db.close()


def test_snapshot_covers_exactly_the_landing_tables():
    assert set(silver_schema.COLUMNS) == set(_landing_sql_columns())
    assert set(silver_schema.REQUIRED) == set(silver_schema.COLUMNS)


def test_snapshot_columns_match_the_landing_ddl_in_order():
    for table, landing_columns in _landing_sql_columns().items():
        extra = _DUCKDB_ONLY_COLUMNS.get(table, set())
        snapshot_columns = [c for c in silver_schema.COLUMNS[table] if c not in extra]
        assert snapshot_columns == [c for c, _ in landing_columns], table


def test_snapshot_required_matches_the_landing_ddl_not_null():
    """The half that gates every write: _record_landing_passthrough raises on
    a row missing a REQUIRED column, so REQUIRED must be what Snowflake will
    reject too."""
    for table, landing_columns in _landing_sql_columns().items():
        landing_required = [c for c, not_null in landing_columns if not_null]
        assert list(silver_schema.REQUIRED[table]) == landing_required, table


def test_every_table_requires_something():
    """A table with no NOT NULL column would make the passthrough's guard a
    no-op for it; every landing table keys on cik or accession_number."""
    for table, required in silver_schema.REQUIRED.items():
        assert required, table
        assert set(required) <= set(silver_schema.COLUMNS[table]), table


def test_snapshot_mappings_are_read_only():
    import pytest

    for mapping in (silver_schema.COLUMNS, silver_schema.REQUIRED):
        with pytest.raises(TypeError):
            mapping["sec_company"] = ()  # type: ignore[index]
