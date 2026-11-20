"""The MDM schema explains itself, and an old store is refused.

Operator, 2026-09-30: "make the table self explainable". Every table, view,
column and function in `mdm` carries a comment, so `\\d+` and the Data
Catalog say what each holds, who writes it and who reads it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.store import migrate


def _uncommented(conn) -> list[str]:
    return list(conn.scalars(text("""
        SELECT 'relation ' || c.relname FROM pg_class c
        WHERE c.relnamespace = 'mdm'::regnamespace AND c.relkind IN ('r', 'v')
          AND coalesce(obj_description(c.oid, 'pg_class'), '') = ''
        UNION ALL
        SELECT 'column ' || c.relname || '.' || a.attname
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relnamespace = 'mdm'::regnamespace AND c.relkind IN ('r', 'v')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND coalesce(col_description(c.oid, a.attnum), '') = ''
        UNION ALL
        SELECT 'function ' || p.oid::regprocedure::text FROM pg_proc p
        WHERE p.pronamespace = 'mdm'::regnamespace
          AND coalesce(obj_description(p.oid, 'pg_proc'), '') = ''
        UNION ALL
        SELECT 'schema mdm' WHERE coalesce(obj_description('mdm'::regnamespace, 'pg_namespace'), '') = ''
        ORDER BY 1""")))


def test_every_table_view_column_and_function_has_a_comment(database):
    with database.admin.connect() as conn:
        assert _uncommented(conn) == []


def test_init_installs_one_stamp_and_the_mastering_tables_only(database):
    """The data database holds MDM's init stamp and the mastering tables: no other MDM table, view or function."""
    with database.admin.connect() as conn:
        assert conn.execute(text("SELECT name FROM mdm.migration")).scalars().all() == ["schema.sql"]
        assert conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='mdm'")).scalars().all() == ["migration"]
        others = conn.execute(text("""SELECT tablename FROM pg_tables WHERE schemaname='public'
            AND tablename NOT LIKE 'mastering\\_%'""")).scalars().all()
        assert others == []
        assert conn.scalar(text("""SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname IN ('mdm', 'public')""")) == 0


def test_migrating_a_store_that_holds_data_changes_nothing(database):
    """A second `mdm init` over a store with rows installs nothing, keeps
    the rows, and leaves the application login its read access."""
    with database.admin.connect() as conn:
        before = conn.scalar(text("SELECT count(*) FROM mdm.migration"))
        policies = conn.scalar(text("SELECT count(*) FROM rules.policy"))
    assert before and policies
    assert not migrate(database.admin, application_role="clean_application")["installed"]
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.migration")) == before
        assert conn.scalar(text("SELECT count(*) FROM rules.policy")) == policies
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.migration")) == before
