from __future__ import annotations

from pathlib import Path

from edgar_warehouse.mdm.migrations import runtime as migrations

MIGRATION_NAME = "012_acquisition_ledger.sql"


def _migration_sql() -> str:
    return (
        Path(migrations.__file__).with_name(MIGRATION_NAME).read_text(encoding="utf-8")
    )


def test_acquisition_ledger_migration_is_registered() -> None:
    assert MIGRATION_NAME in Path(migrations.__file__).read_text(encoding="utf-8")


def test_postgres_schema_enforces_ledger_authority_contract() -> None:
    normalized = " ".join(_migration_sql().lower().split())

    for relation in (
        "source_observation_cursor",
        "source_fetch_decision",
        "source_fetch_work",
        "source_fetch_transition",
    ):
        assert f"create table if not exists {relation}" in normalized

    assert (
        "create unique index if not exists uq_source_fetch_work_active_key"
        in normalized
    )
    assert "where fetch_state in ('ready','leased')" in normalized
    assert "create or replace view source_change_status" in normalized
    assert "already_captured_verified" in normalized
    assert "out_of_scope" in normalized
    assert "operator_excluded" in normalized
    assert "download_deferred" in normalized


def test_postgres_schema_makes_history_immutable_and_checks_role_and_fencing() -> None:
    normalized = " ".join(_migration_sql().lower().split())

    assert "source_fetch_decision is immutable" in normalized
    assert "source_fetch_transition is immutable" in normalized
    assert "create role edgartools_acquisition_coordinator nologin" in normalized
    assert "create role edgartools_acquisition_worker nologin" in normalized
    assert "create role edgartools_acquisition_operator nologin" in normalized
    assert "security definer" in normalized
    assert "pg_has_role(session_user" in normalized
    assert "stale fencing token" in normalized
    assert "revoke insert, update, delete" in normalized
    assert "revoke execute on function claim_source_fetch" in normalized
    assert "revoke execute on function finalize_source_fetch" in normalized
