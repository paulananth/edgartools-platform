"""Tests for MDM runtime/e2e support helpers."""

from __future__ import annotations

from pathlib import Path

from edgar_warehouse.cli import build_parser
from edgar_warehouse.mdm.api.auth import _parse_key_payload
from edgar_warehouse.mdm.migrations import runtime as migrations
from edgar_warehouse.mdm.migrations.runtime import MDM_TABLES


def test_api_key_payload_accepts_csv_and_json() -> None:
    assert _parse_key_payload("alpha,beta") == {"alpha", "beta"}
    assert _parse_key_payload('{"keys": ["alpha", " beta "]}') == {"alpha", "beta"}


def test_mdm_runtime_table_list_includes_sql_and_graph_surfaces() -> None:
    assert "mdm_company" in MDM_TABLES
    assert "mdm_relationship_instance" in MDM_TABLES
    assert "mdm_change_log" in MDM_TABLES


def test_postgres_migration_covers_mdm_tables_without_tsql_tokens() -> None:
    path = Path(migrations.__file__).with_name("001_initial_schema.sql")
    sql = path.read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    for table in MDM_TABLES:
        assert f"create table if not exists {table}" in normalized

    assert "uuid primary key" in normalized
    assert "jsonb" in normalized
    assert "timestamptz" in normalized

    sql_upper = sql.upper()
    for token in ("NVARCHAR", "SYSUTCDATETIME", "NEWID()", "DATETIMEOFFSET", "OBJECT_ID"):
        assert token not in sql_upper


def test_postgres_migrate_routes_to_postgres_schema(monkeypatch) -> None:
    class _Dialect:
        name = "postgresql"

    class _Engine:
        dialect = _Dialect()

    applied_files: list[str] = []

    def _record_apply(_engine, filename: str) -> None:
        applied_files.append(filename)

    monkeypatch.setattr(migrations, "_apply_sql_file", _record_apply)
    monkeypatch.setattr(migrations, "count_tables", lambda _engine: {})

    result = migrations.migrate(_Engine(), seed=False)

    assert result["dialect"] == "postgresql"
    assert applied_files == ["001_initial_schema.sql"]


def test_mdm_cli_exposes_e2e_operations() -> None:
    parser = build_parser()
    for command in ("migrate", "counts", "check-connectivity", "sync-graph", "api"):
        args = parser.parse_args(["mdm", command])
        assert args.command == "mdm"
        assert args.mdm_command == command
