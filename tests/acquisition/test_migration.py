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
CONFLICT_MIGRATION_NAME = "015_source_evidence_conflict.sql"
EXCLUSION_IMPORT_MIGRATION_NAME = "017_source_exclusion_and_evidence_import.sql"
VALIDATORS_MIGRATION_NAME = "018_source_fetch_validators.sql"
REPO_ROOT = Path(__file__).parents[2]


def _migration_sql() -> str:
    return (
        Path(migrations.__file__).with_name(MIGRATION_NAME).read_text(encoding="utf-8")
    )


def _conflict_migration_sql() -> str:
    return (
        Path(migrations.__file__)
        .with_name(CONFLICT_MIGRATION_NAME)
        .read_text(encoding="utf-8")
    )


def _exclusion_import_migration_sql() -> str:
    return (
        Path(migrations.__file__)
        .with_name(EXCLUSION_IMPORT_MIGRATION_NAME)
        .read_text(encoding="utf-8")
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


def test_postgres_schema_seals_processing_decisions_and_expected_producers() -> None:
    """Ticket 19: the processing/expected-producer tables, the dedicated
    Silver Finalizer role, the same-key ordering index, and the
    column-scoped GRANT split (processor INSERTs, finalizer UPDATEs only
    specific columns -- no role-check trigger backs this up, see
    models.py's SourceExpectedProducerRecord docstring) are all present.
    """

    normalized = " ".join(_migration_sql().lower().split())

    assert "create table if not exists source_processing_decision" in normalized
    assert "create table if not exists source_expected_producer" in normalized
    assert (
        "create role edgartools_acquisition_silver_finalizer nologin" in normalized
    )
    assert "uq_source_processing_decision_revision" in normalized
    assert "uq_source_processing_decision_active_key" in normalized
    assert "uq_source_expected_producer_name" in normalized
    assert "ck_source_processing_decision_no_process_required_published" in normalized
    assert "ck_source_processing_decision_settled_at_shape" in normalized
    assert (
        "'process_required','no_impact','out_of_scope','operator_excluded',"
        "'superseded','quarantined','retryable_failure'" in normalized
    )
    assert "'pending','published','failed'" in normalized
    assert "'pending','verified','no_impact','failed'" in normalized
    # Column-scoped GRANTs, not a role-check trigger, are the enforcement
    # layer for who may update a producer's outcome.
    assert (
        "grant update (outcome, verified_reference, failure_detail, updated_at) "
        "on source_expected_producer to edgartools_acquisition_silver_finalizer"
        in normalized
    )
    assert (
        "grant update (silver_outcome, settled_at) on source_processing_decision "
        "to edgartools_acquisition_silver_finalizer" in normalized
    )
    assert (
        "grant select, insert on source_processing_decision, "
        "source_expected_producer to edgartools_acquisition_processor"
        in normalized
    )
    assert "create or replace view source_change_status_detail" in normalized


def test_bootstrap_and_restore_cover_processing_and_expected_producer() -> None:
    bootstrap = (REPO_ROOT / "infra/scripts/bootstrap-prod-mdm.sh").read_text()
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()

    assert "source_processing_decision" in bootstrap
    assert "source_expected_producer" in bootstrap
    assert "source_change_status_detail" in bootstrap
    assert "edgartools_acquisition_silver_finalizer" in restore
    assert (
        "to_regclass('public.source_processing_decision') IS NOT NULL" in restore
    )
    assert (
        "GRANT UPDATE (silver_outcome, settled_at) ON source_processing_decision"
        in restore
    )
    assert (
        "GRANT UPDATE (outcome, verified_reference, failure_detail, updated_at)"
        in restore
    )


def test_conflict_migration_is_registered() -> None:
    assert CONFLICT_MIGRATION_NAME in Path(migrations.__file__).read_text(encoding="utf-8")


def test_conflict_migration_defines_source_evidence_conflict_and_reuses_existing_013_roles() -> None:
    """Ticket 25 bullet 1/2: the conflict table, its resolution-completeness
    constraint, and (critically) the *absence* of a new role-provisioning
    DO block -- this migration reuses 013's roles: owned by
    edgartools_acquisition_owner (same as source_revision -- CREATE on
    schema public was only ever granted to the owner role, not to any
    operational role), with operational GRANTs to
    edgartools_acquisition_processor. No new role is created.
    """

    normalized = " ".join(_conflict_migration_sql().lower().split())

    assert "create table if not exists source_evidence_conflict" in normalized
    assert "uq_source_evidence_conflict_quarantine" in normalized
    assert "ck_source_evidence_conflict_status" in normalized
    assert "ck_source_evidence_conflict_resolution_complete" in normalized
    assert "'pending','repaired'" in normalized
    assert "references source_revision(revision_id)" in normalized
    assert "grant select, insert" in normalized
    assert "to edgartools_acquisition_processor" in normalized
    assert "owner to edgartools_acquisition_owner" in normalized
    # No new role: unlike 013/014, this file provisions nothing via
    # CREATE ROLE -- it reuses 013's edgartools_acquisition_processor.
    assert "create role" not in normalized


def test_conflict_migration_grants_read_access_to_every_other_acquisition_role() -> None:
    normalized = " ".join(_conflict_migration_sql().lower().split())

    assert "grant select on source_evidence_conflict to" in normalized
    for role in (
        "edgartools_acquisition_coordinator",
        "edgartools_acquisition_worker",
        "edgartools_acquisition_operator",
        "edgartools_acquisition_silver_finalizer",
    ):
        assert role in normalized


def test_bootstrap_and_restore_cover_evidence_conflict() -> None:
    bootstrap = (REPO_ROOT / "infra/scripts/bootstrap-prod-mdm.sh").read_text()
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()

    assert "source_evidence_conflict" in bootstrap
    assert "to_regclass('public.source_evidence_conflict') IS NOT NULL" in restore
    assert (
        "ALTER TABLE source_evidence_conflict OWNER TO edgartools_acquisition_owner"
        in restore
    )


def test_exclusion_and_evidence_import_migration_is_registered() -> None:
    assert EXCLUSION_IMPORT_MIGRATION_NAME in Path(migrations.__file__).read_text(
        encoding="utf-8"
    )


def test_exclusion_reason_migration_guards_its_check_constraint_for_rerun_safety() -> None:
    """Postgres has no `ADD CONSTRAINT IF NOT EXISTS` for CHECK constraints --
    a bare `ALTER TABLE ... ADD CONSTRAINT` here would fail with
    "already exists" on any rerun by a role with real owner membership
    (reproduced live against Postgres before this guard was added)."""

    normalized = " ".join(_exclusion_import_migration_sql().lower().split())

    assert "add column if not exists exclusion_reason" in normalized
    assert "select 1 from pg_constraint" in normalized
    assert "ck_source_fetch_decision_exclusion_reason" in normalized
    assert (
        "check (fetch_disposition <> 'operator_excluded' or exclusion_reason is not null)"
        in normalized
    )
    # Ticket 34 bullet 1, "visible in Source Change Status": the real
    # operator-facing view, not just the Python dataclass, must also expose it.
    assert "create or replace view source_change_status as" in normalized
    assert "decision.exclusion_reason" in normalized


def test_evidence_import_migration_defines_source_evidence_import_and_reuses_existing_013_roles() -> (
    None
):
    """Ticket 34: the import table, its lineage uniqueness constraint, and
    (critically) the *absence* of a new role-provisioning DO block -- this
    migration reuses 013's roles: owned by edgartools_acquisition_owner
    (CREATE on schema public was only ever granted to the owner role), with
    operational GRANTs to the existing edgartools_acquisition_operator (an
    import is a deliberate operator action, same class of responsibility as
    OPERATOR_REQUEST/OPERATOR_EXCLUDED fetch decisions). No new role."""

    normalized = " ".join(_exclusion_import_migration_sql().lower().split())

    assert "create table if not exists source_evidence_import" in normalized
    assert "uq_source_evidence_import_source_reference" in normalized
    assert "unique (source_environment, source_bronze_reference)" in normalized
    assert "grant select, insert on source_evidence_import to edgartools_acquisition_operator" in normalized
    assert "owner to edgartools_acquisition_owner" in normalized
    assert "create role" not in normalized


def test_evidence_import_migration_grants_read_access_to_every_other_acquisition_role() -> (
    None
):
    normalized = " ".join(_exclusion_import_migration_sql().lower().split())

    assert "grant select on source_evidence_import to" in normalized
    for role in (
        "edgartools_acquisition_coordinator",
        "edgartools_acquisition_worker",
        "edgartools_acquisition_processor",
        "edgartools_acquisition_silver_finalizer",
    ):
        assert role in normalized


def test_bootstrap_and_restore_cover_exclusion_and_evidence_import() -> None:
    bootstrap = (REPO_ROOT / "infra/scripts/bootstrap-prod-mdm.sh").read_text()
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()

    assert "source_evidence_import" in bootstrap
    assert "to_regclass('public.source_evidence_import') IS NOT NULL" in restore
    assert (
        "ALTER TABLE source_evidence_import OWNER TO edgartools_acquisition_owner"
        in restore
    )


def _validators_migration_sql() -> str:
    return (
        Path(migrations.__file__)
        .with_name(VALIDATORS_MIGRATION_NAME)
        .read_text(encoding="utf-8")
    )


def test_validators_migration_is_registered() -> None:
    assert VALIDATORS_MIGRATION_NAME in Path(migrations.__file__).read_text(
        encoding="utf-8"
    )


def test_validators_migration_adds_columns_and_replaces_fenced_finalize() -> None:
    """Ticket 28: additive ETag/Last-Modified columns, and the 7-arg
    finalize_source_fetch is dropped so validators write in the same
    SECURITY DEFINER UPDATE. A sidecar UPDATE as worker would permission-
    deny (013 grants that role SELECT only on source_fetch_work)."""

    normalized = " ".join(_validators_migration_sql().lower().split())

    assert "add column if not exists captured_etag" in normalized
    assert "add column if not exists captured_last_modified" in normalized
    assert (
        "drop function if exists finalize_source_fetch("
        "uuid, text, bigint, text, timestamptz, text, text)"
        in normalized
    )
    assert "captured_etag = requested_etag" in normalized
    assert "captured_last_modified = requested_last_modified" in normalized
    assert (
        "grant execute on function finalize_source_fetch("
        "uuid, text, bigint, text, timestamptz, text, text, text, text)"
        in normalized
    )
    assert "create table" not in normalized
    assert "create role" not in normalized


def test_bootstrap_and_restore_cover_nine_arg_finalize() -> None:
    restore = (REPO_ROOT / "infra/snowflake/postgres/mdm_post_restore.sql").read_text()
    signature = (
        "finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, "
        "TEXT, TEXT, TEXT, TEXT)"
    )
    assert signature in restore
    assert (
        "finalize_source_fetch(UUID, TEXT, BIGINT, TEXT, TIMESTAMPTZ, TEXT, TEXT)"
        not in restore.replace(signature, "")
    )
