"""The MDM schema explains itself, and an old store is refused.

Operator, 2026-09-30: "make the table self explainable". Every table, view,
column and function in `mdm` carries a comment, so `\\d+` and the Data
Catalog say what each holds, who writes it and who reads it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.store import Conflict, migrate
from tests.integration.test_clean_mdm_postgres import database, postgres  # noqa: F401


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
        # The per-kind views are generated, and commented, for every kind.
        kinds = conn.scalar(text(
            "SELECT count(*) FROM pg_views WHERE schemaname='mdm' AND viewname LIKE '%\\_stage'"))
        assert kinds == 8


def test_only_the_mdm_schema_exists(database):
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT to_regnamespace('mdm_v2')")) is None
        assert conn.scalar(text(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'mdm\\_%'")) == 0


def test_a_store_with_the_retired_mdm_v2_schema_is_refused(database):
    with database.admin.begin() as conn:
        conn.execute(text("CREATE SCHEMA mdm_v2"))
    with pytest.raises(Conflict, match="retired mdm_v2 schema"):
        migrate(database.admin, application_role="clean_application")
