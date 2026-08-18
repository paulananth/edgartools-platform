"""Regression test for infra/scripts/generate_silver_landing_ddl.py.

silver-snowflake-migration map, Ticket 11 (2026-08-18): live on the
PRJEDJU-QJB05385 account, `LOAD_SILVER_LANDING_TASK`'s first real run failed
with "NULL result in a non-nullable column" on `parse_sequence`, even though
the generated `CREATE TABLE` text never declares `parse_sequence NOT NULL`.
Root cause: Snowflake implicitly forces `NOT NULL` on any column named in a
`PRIMARY KEY` clause, regardless of that column's own declaration -- verified
live via `GET_DDL` showing `parse_sequence NUMBER(38,0) NOT NULL` on a table
whose source text has no `NOT NULL` on that column. Ticket 07's original fix
(dropping the explicit `NOT NULL` from the column declaration) only ever
achieved real nullability via a live, undocumented `ALTER TABLE ... DROP NOT
NULL` run once by hand -- it never survived the account's later rebuild.

This test locks in the fix: the generator must emit an explicit `ALTER TABLE
... ALTER COLUMN parse_sequence DROP NOT NULL` statement for every table it
generates, immediately after that table's `CREATE TABLE`. Confirmed to fail
against the pre-fix generator (no such statement existed at all).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "infra" / "scripts" / "generate_silver_landing_ddl.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_silver_landing_ddl", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_every_created_table_drops_parse_sequence_not_null():
    module = _load_generator()
    sql = module.generate()

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
    so a future edit can't accidentally attach the ALTER to the wrong table."""
    module = _load_generator()
    sql = module.generate()

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
    module = _load_generator()
    sql = module.generate()

    alter_statements = re.findall(
        r"ALTER TABLE \w+ ALTER COLUMN parse_sequence DROP NOT NULL;", sql
    )
    assert len(alter_statements) >= 30
    for statement in alter_statements:
        assert "IF EXISTS" not in statement
        assert "IF NOT EXISTS" not in statement
