"""SQL-text assertions for migration 014 (Ticket 20's Source Family Registry)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from edgar_warehouse.acquisition.models import (
    SourceRegistryCoverageRecord,
    SourceRegistryVersionRecord,
)
from edgar_warehouse.mdm.migrations import runtime as migrations

MIGRATION_NAME = "014_source_registry.sql"
REPO_ROOT = Path(__file__).parents[2]


def _migration_sql() -> str:
    return Path(migrations.__file__).with_name(MIGRATION_NAME).read_text(encoding="utf-8")


def test_source_registry_migration_is_registered() -> None:
    runtime_source = Path(migrations.__file__).read_text(encoding="utf-8")
    assert MIGRATION_NAME in runtime_source
    assert "_apply_source_registry_migration" in runtime_source


def test_sqlalchemy_identifiers_compile_as_postgres_uuid_and_jsonb() -> None:
    version_ddl = str(
        CreateTable(SourceRegistryVersionRecord.__table__).compile(dialect=postgresql.dialect())
    )
    assert "version_id UUID" in version_ddl

    coverage_ddl = str(
        CreateTable(SourceRegistryCoverageRecord.__table__).compile(dialect=postgresql.dialect())
    )
    assert "coverage_id UUID" in coverage_ddl
    assert "version_id UUID" in coverage_ddl


def test_postgres_schema_versions_and_gates_activation() -> None:
    normalized = " ".join(_migration_sql().lower().split())

    for relation in ("source_registry_version", "source_registry_coverage"):
        assert f"create table if not exists {relation}" in normalized

    assert "create role edgartools_acquisition_registry_owner nologin" in normalized
    assert "uq_source_registry_version_single_active" in normalized
    assert "uq_source_registry_coverage_family" in normalized
    assert "'draft','activation_blocked','active','superseded'" in normalized
    assert "'add','remove','carry_forward'" in normalized
    assert "ck_source_registry_coverage_remove_end_date" in normalized
    assert "ck_source_registry_coverage_add_catchup_required" in normalized
    assert "owner to edgartools_acquisition_registry_owner" in normalized
    assert "grant edgartools_acquisition_registry_owner to application" in normalized
    assert "with inherit false, set true" in normalized
    assert "revoke all privileges on source_registry_version, source_registry_coverage" in normalized


def test_restore_covers_source_registry() -> None:
    # Ticket 47 (change-propagation map): bootstrap-prod-mdm.sh used to
    # re-REVOKE `application` from source_registry_version/coverage here via
    # its own SET ROLE edgartools_acquisition_registry_owner + REVOKE, on a
    # fresh connection opened after the `mdm migrate` subprocess exits. That
    # was always redundant with -- and, being a separate cross-connection
    # REVOKE, the reproducible cause of a failure mode analogous to -- what
    # 014_source_registry.sql's own internal REVOKE already does atomically
    # (see test_postgres_schema_versions_and_gates_activation above). So this
    # is restore-only now.
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()

    assert "CREATE ROLE edgartools_acquisition_registry_owner NOLOGIN" in restore
    assert "GRANT edgartools_acquisition_registry_owner TO application" in restore
    assert "to_regclass('public.source_registry_version') IS NOT NULL" in restore
    assert (
        "GRANT SELECT, INSERT, UPDATE ON source_registry_version, source_registry_coverage"
        in restore
    )
    assert (
        "REVOKE ALL PRIVILEGES ON source_registry_version, source_registry_coverage"
        in restore
    )
