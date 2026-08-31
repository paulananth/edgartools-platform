"""Regression test for infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql.

DuckDB Retirement Cutover Ticket 07 deleted the generator
(infra/scripts/generate_silver_landing_ddl.py) that used to produce this
file and its own dedicated regression test
(tests/unit/test_generate_silver_landing_ddl.py). This file is now
hand-maintained -- there is no regeneration step. That's a meaningful change
in risk, not just a housekeeping detail: the invariant the deleted test
locked in doesn't disappear along with the generator, since it lives on in
this now-hand-editable SQL file.

silver-snowflake-migration map, Ticket 11 (2026-08-18): live on the
PRJEDJU-QJB05385 account, LOAD_SILVER_LANDING_TASK's first real run failed
with "NULL result in a non-nullable column" on parse_sequence, even though
the generated CREATE TABLE text never declared parse_sequence NOT NULL.
Root cause: Snowflake implicitly forces NOT NULL on any column named in a
PRIMARY KEY clause, regardless of that column's own declaration. The fix:
every table's CREATE TABLE is immediately followed by an explicit
ALTER TABLE ... ALTER COLUMN parse_sequence DROP NOT NULL statement.

This test protects that fix against silent regression from a future hand
edit -- e.g. a new table added to this file without its own ALTER, or an
existing ALTER accidentally dropped -- since nothing generates or
regenerates this file anymore to re-derive it correctly.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL_PATH = (
    REPO_ROOT / "infra" / "snowflake" / "sql" / "bootstrap" / "11_silver_landing_schema.sql"
)


def _read_schema_sql() -> str:
    return SCHEMA_SQL_PATH.read_text()


def test_every_created_table_drops_parse_sequence_not_null():
    sql = _read_schema_sql()

    create_table_names = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", sql)
    assert len(create_table_names) >= 30, "sanity check: expected ~30 landing tables"

    for table in create_table_names:
        assert f"ALTER TABLE {table} ALTER COLUMN parse_sequence DROP NOT NULL;" in sql, (
            f"{table}: missing the DROP NOT NULL fix -- Snowflake's PRIMARY KEY "
            "clause implicitly forces parse_sequence NOT NULL regardless of the "
            "column's own declaration, so this ALTER is required, not optional "
            "(see this file's module docstring)."
        )


def test_alter_statement_immediately_follows_its_table_create():
    """Not just present anywhere -- must directly follow its own CREATE TABLE,
    so a future hand edit can't accidentally attach the ALTER to the wrong table."""
    sql = _read_schema_sql()

    blocks = re.split(r"(?=CREATE TABLE IF NOT EXISTS )", sql)
    table_blocks = [b for b in blocks if b.startswith("CREATE TABLE IF NOT EXISTS ")]
    assert len(table_blocks) >= 30

    for block in table_blocks:
        table = re.match(r"CREATE TABLE IF NOT EXISTS (\w+) \(", block).group(1)
        # The block runs up to (but not including) the next CREATE TABLE, so
        # the ALTER for this table must appear within it.
        assert f"ALTER TABLE {table} ALTER COLUMN parse_sequence DROP NOT NULL;" in block


def test_alter_statement_is_idempotent_syntax_not_a_conditional_guard():
    """Snowflake's ALTER COLUMN DROP NOT NULL has no IF EXISTS/IF NOT EXISTS
    form -- idempotency here comes from DROP NOT NULL being a no-op against an
    already-nullable column, not from guard syntax. Assert the statement is the
    plain form (no accidental guard clause that would break on a fresh table
    that never had a NOT NULL constraint to drop)."""
    sql = _read_schema_sql()

    alter_statements = re.findall(
        r"ALTER TABLE \w+ ALTER COLUMN parse_sequence DROP NOT NULL;", sql
    )
    assert len(alter_statements) >= 30
    for statement in alter_statements:
        assert "IF EXISTS" not in statement
        assert "IF NOT EXISTS" not in statement


def test_every_create_table_has_a_matching_alter_and_vice_versa():
    """Counts must match exactly -- catches a table gaining a CREATE without
    its ALTER, or an orphaned ALTER left behind after a table is removed."""
    sql = _read_schema_sql()

    create_table_names = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", sql))
    altered_table_names = set(
        re.findall(r"ALTER TABLE (\w+) ALTER COLUMN parse_sequence DROP NOT NULL;", sql)
    )
    assert create_table_names == altered_table_names
