from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from edgar_warehouse.acquisition.models import (
    SourceFetchDecisionRecord,
    SourceFetchTransitionRecord,
    SourceFetchWorkRecord,
    SourceRevisionRecord,
)
from edgar_warehouse.mdm.migrations import runtime as migrations

MIGRATION_NAME = "013_acquisition_ledger.sql"
REPO_ROOT = Path(__file__).parents[2]


def _migration_sql() -> str:
    return (
        Path(migrations.__file__).with_name(MIGRATION_NAME).read_text(encoding="utf-8")
    )


def test_acquisition_ledger_migration_is_registered() -> None:
    assert MIGRATION_NAME in Path(migrations.__file__).read_text(encoding="utf-8")


def test_sqlalchemy_identifiers_compile_as_postgres_uuid() -> None:
    for model in (
        SourceFetchDecisionRecord,
        SourceFetchWorkRecord,
        SourceFetchTransitionRecord,
    ):
        ddl = str(CreateTable(model.__table__).compile(dialect=postgresql.dialect()))
        assert "decision_id UUID" in ddl

    revision_ddl = str(
        CreateTable(SourceRevisionRecord.__table__).compile(dialect=postgresql.dialect())
    )
    assert "revision_id UUID" in revision_ddl
    assert "parent_revision_id UUID" in revision_ddl


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
    assert "where fetch_state in ('ready','leased','failed')" in normalized
    assert "create or replace view source_change_status" in normalized
    assert "already_captured_verified" in normalized
    assert "out_of_scope" in normalized
    assert "operator_excluded" in normalized
    assert "download_deferred" in normalized
    assert "verified_evidence_reference" in normalized
    assert "scope_proof_reference" in normalized
    assert "operator_authorization_reference" in normalized


def test_postgres_schema_makes_history_immutable_and_checks_role_and_fencing() -> None:
    normalized = " ".join(_migration_sql().lower().split())

    assert "source_fetch_decision is immutable" in normalized
    assert "source_fetch_transition is immutable" in normalized
    assert "create role edgartools_acquisition_coordinator nologin" in normalized
    assert "create role edgartools_acquisition_worker nologin" in normalized
    assert "create role edgartools_acquisition_operator nologin" in normalized
    assert "create role edgartools_acquisition_owner nologin" in normalized
    assert "security definer" in normalized
    assert "current_setting('role', true)" in normalized
    assert "owner to edgartools_acquisition_owner" in normalized
    assert "stale fencing token" in normalized
    assert "revoke insert, update, delete" in normalized
    assert "revoke execute on function claim_source_fetch" in normalized
    assert "revoke execute on function finalize_source_fetch" in normalized
    assert "grant edgartools_acquisition_worker to application" in normalized
    assert "with inherit false, set true" in normalized
    assert (
        "grant insert on source_fetch_transition to edgartools_acquisition_worker"
        not in normalized
    )
    assert (
        "grant select, insert on source_fetch_transition to "
        "edgartools_acquisition_coordinator" not in normalized
    )


def test_postgres_schema_materializes_ordered_source_revisions() -> None:
    """Ticket 18: the revision table, its role, and its provenance/identity
    constraints are all present in the migration SQL.
    """

    normalized = " ".join(_migration_sql().lower().split())

    assert "create table if not exists source_revision" in normalized
    assert "create role edgartools_acquisition_processor nologin" in normalized
    assert "source_revision_immutable" in normalized
    assert "enforce_acquisition_revision_role" in normalized
    assert "uq_source_revision_decision" in normalized
    assert "uq_source_revision_observation" in normalized
    assert "uq_source_revision_reinterpretation" in normalized
    assert "ck_source_revision_provenance_exclusive" in normalized
    assert "ck_source_revision_relationship_requires_parent" in normalized
    assert "'repair','supersession','coalescing','reinterpretation'" in normalized
    assert "'changed','no_impact'" in normalized
    # revision identity deliberately excludes transport/operational fields --
    # Ticket 18 bullet 5.
    for excluded in ("run_id", "arrival_time", "object_path", "etag"):
        assert excluded not in normalized


def test_bootstrap_and_restore_preserve_dedicated_acquisition_owner() -> None:
    bootstrap = (REPO_ROOT / "infra/scripts/bootstrap-prod-mdm.sh").read_text()
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()

    assert "CREATE ROLE application NOLOGIN" in bootstrap
    assert "REVOKE ALL PRIVILEGES ON source_observation_cursor" in bootstrap
    assert "source_revision" in bootstrap
    assert "OWNER TO edgartools_acquisition_owner" in restore
    assert "FROM application" in restore
    assert "GRANT edgartools_acquisition_coordinator TO application" in restore
    assert "GRANT edgartools_acquisition_processor TO application" in restore
    assert "GRANT application TO snowflake_admin" in restore
    assert "to_regclass('public.source_fetch_decision') IS NOT NULL" in restore
    assert "to_regclass('public.source_revision') IS NOT NULL" in restore
    assert "GRANT SELECT, INSERT ON source_fetch_decision" in restore
    assert "GRANT SELECT, INSERT ON source_revision TO edgartools_acquisition_processor" in restore
    assert "GRANT EXECUTE ON FUNCTION claim_source_fetch" in restore
    assert "GRANT SELECT ON source_change_status" in restore
    assert restore.index("REVOKE ALL PRIVILEGES ON") < restore.index(
        "ALTER TABLE source_observation_cursor"
    )
