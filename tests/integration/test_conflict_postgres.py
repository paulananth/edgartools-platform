"""Real-Postgres integration coverage for Ticket 25's evidence-conflict/repair path.

Same rationale as ``test_acquisition_ledger_postgres.py``/
``test_source_registry_postgres.py``'s own docstrings: SQLite-backed unit
tests (``tests/acquisition/test_conflict.py``, ``test_revisions.py``) prove
the ledger's own logic, but migration 015's self-managing first-install/
rerun path (the table is owned by 013's ``edgartools_acquisition_owner``,
same as ``source_revision`` -- ``application`` is never a member of that
role, only of the five operational roles, so it provisions no new role of
its own and reuses 013's existing owner/operator split rather than 014's
merged single-role shape) and the real GRANT-level separation it relies on
are only exercisable against a real Postgres role graph.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.acquisition.conflict import ConflictAlreadyResolved, ConflictLedger
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
)
from edgar_warehouse.acquisition.revisions import RevisionRelationship, SourceRevisionLedger
from edgar_warehouse.mdm.migrations import runtime as migrations

POSTGRES_IMAGE = "postgres:16-alpine"
LEDGER_MIGRATION = (
    Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations" / "013_acquisition_ledger.sql"
)
CONFLICT_MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "015_source_evidence_conflict.sql"
)
EXCLUSION_IMPORT_MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "017_source_exclusion_and_evidence_import.sql"
)


@dataclass(frozen=True)
class PostgresConflict:
    container: str
    database_url: str
    admin_database_url: str


def _run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)


def _psql(container: str, sql: str, *, user: str = "postgres") -> subprocess.CompletedProcess[str]:
    return _run(
        "docker", "exec", "-i", "-e", "PGPASSWORD=test", container,
        "psql", "-h", "127.0.0.1", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", "postgres",
        input_text=sql,
    )


def _psql_scalar(container: str, sql: str, *, user: str = "postgres") -> str:
    result = _run(
        "docker", "exec", "-i", "-e", "PGPASSWORD=test", container,
        "psql", "-h", "127.0.0.1", "-v", "ON_ERROR_STOP=1", "-U", user, "-d", "postgres",
        "-t", "-A",
        input_text=sql,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _psql_file(container: str, remote_path: str) -> subprocess.CompletedProcess[str]:
    return _run(
        "docker", "exec", "-e", "PGPASSWORD=test", container,
        "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres", "-f", remote_path,
    )


@pytest.fixture(scope="module")
def postgres_conflict() -> Iterator[PostgresConflict]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket25-{uuid.uuid4().hex[:10]}"
    started = _run(
        "docker", "run", "-d", "--rm", "--name", container,
        "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", POSTGRES_IMAGE,
    )
    assert started.returncode == 0, started.stderr
    try:
        for _ in range(40):
            ready = _psql(container, "SELECT 1;")
            if ready.returncode == 0:
                break
            time.sleep(0.25)
        else:
            pytest.fail("ephemeral PostgreSQL did not become ready")

        application = _psql(container, "CREATE ROLE application LOGIN PASSWORD 'test';")
        assert application.returncode == 0, application.stderr

        copied_ledger = _run("docker", "cp", str(LEDGER_MIGRATION), f"{container}:/tmp/ledger.sql")
        assert copied_ledger.returncode == 0, copied_ledger.stderr
        migrated_ledger = _psql_file(container, "/tmp/ledger.sql")
        assert migrated_ledger.returncode == 0, migrated_ledger.stderr

        copied_conflict = _run("docker", "cp", str(CONFLICT_MIGRATION), f"{container}:/tmp/conflict.sql")
        assert copied_conflict.returncode == 0, copied_conflict.stderr
        migrated_conflict = _psql_file(container, "/tmp/conflict.sql")
        assert migrated_conflict.returncode == 0, migrated_conflict.stderr

        # Ticket 34: SourceFetchDecisionRecord's ORM mapping now includes
        # exclusion_reason -- this fixture's round-trip tests read/write
        # source_fetch_decision through the real ORM, so 017 must be applied
        # here too or those reads fail with UndefinedColumn.
        copied_exclusion_import = _run(
            "docker", "cp", str(EXCLUSION_IMPORT_MIGRATION), f"{container}:/tmp/exclusion_import.sql"
        )
        assert copied_exclusion_import.returncode == 0, copied_exclusion_import.stderr
        migrated_exclusion_import = _psql_file(container, "/tmp/exclusion_import.sql")
        assert migrated_exclusion_import.returncode == 0, migrated_exclusion_import.stderr

        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresConflict(
            container=container,
            database_url=f"postgresql+psycopg2://application:test@127.0.0.1:{port}/postgres",
            admin_database_url=f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres",
        )
    finally:
        _run("docker", "stop", container)


def test_apply_source_evidence_conflict_migration_rerun_against_real_postgres(
    postgres_conflict: PostgresConflict,
) -> None:
    """Exercise ``_apply_source_evidence_conflict_migration``'s self-managing
    first-install/rerun path against the real role graph. Unlike 014's
    single merged registry-owner role, ``source_evidence_conflict`` is owned
    by 013's split ``edgartools_acquisition_owner`` -- ``application`` is
    never a member of that role (only of the five *operational* roles), so
    a rerun through the application engine is expected to silently skip
    (``False``), same as :func:`_apply_acquisition_ledger_migration` already
    does for 013's own tables; only the admin engine (a member of the owner
    role, granted during the module fixture's own migration run) can
    actually manage a rerun.
    """

    application_engine = create_engine(postgres_conflict.database_url)
    admin_engine = create_engine(postgres_conflict.admin_database_url)
    try:
        result = migrations._apply_source_evidence_conflict_migration(application_engine)
        assert result is False

        admin_result = migrations._apply_source_evidence_conflict_migration(admin_engine)
        assert admin_result is True
    finally:
        application_engine.dispose()
        admin_engine.dispose()


def test_conflict_table_is_owned_by_the_owner_role_and_fenced_from_application(
    postgres_conflict: PostgresConflict,
) -> None:
    owner = _psql(
        postgres_conflict.container,
        "SELECT tableowner FROM pg_tables WHERE tablename = 'source_evidence_conflict';",
    )
    assert owner.returncode == 0, owner.stderr
    assert "edgartools_acquisition_owner" in owner.stdout

    direct_insert = _psql(
        postgres_conflict.container,
        """
        INSERT INTO source_evidence_conflict (
            relative_path, existing_content_hash, new_content_hash, quarantine_bronze_reference
        ) VALUES ('p', 'a', 'b', 'q-direct');
        """,
        user="application",
    )
    assert direct_insert.returncode != 0
    assert "permission denied for table source_evidence_conflict" in direct_insert.stderr


def test_conflict_ledger_round_trip_against_real_postgres(
    postgres_conflict: PostgresConflict,
) -> None:
    """Record a conflict, resolve it in favor of the conflicting evidence,
    and confirm a real REPAIR child revision lands -- against real Postgres
    role-fencing, not SQLite.
    """

    engine = create_engine(postgres_conflict.database_url)
    try:
        ledger = AcquisitionLedger(engine)
        revisions = SourceRevisionLedger(engine)
        conflicts = ConflictLedger(engine)

        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-conflict-pg",
                source_family="filing_artifact",
                logical_source_key="conflict-pg/document",
                source_url="https://www.sec.gov/Archives/conflict-pg.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="discovery-manifest-1",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="FETCH_SOURCE",
            )
        )
        lease = ledger.claim_fetch(decision.decision_id, worker_id="worker-1", lease_seconds=300)
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="worker-1",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/original-hash-pg",
        )
        parent = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="original-hash-pg",
            canonical_source_hash="original-hash-pg",
            domain_content_hash="original-hash-pg",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )

        conflict = conflicts.record_evidence_conflict(
            relative_path="filings/sec/conflict-pg/primary.xml",
            existing_content_hash="original-hash-pg",
            new_content_hash="conflicting-hash-pg",
            quarantine_bronze_reference=(
                "filings/sec/conflict-pg/primary.xml.conflict/conflicting-hash-pg"
            ),
            source_family="filing_artifact",
            logical_source_key="conflict-pg/document",
        )
        assert conflict.status == "PENDING"

        resolved, revision = conflicts.resolve_conflict(
            conflict.conflict_id,
            parent_revision_id=parent.revision_id,
            accept="conflicting",
            operator_authorization_reference="jira/OPS-PG-1",
            reason="SEC confirmed the corrected bytes are authoritative",
        )

        assert resolved.status == "REPAIRED"
        assert revision is not None
        assert revision.parent_revision_id == parent.revision_id
        assert revision.revision_relationship is RevisionRelationship.REPAIR
        assert resolved.repair_revision_id == revision.revision_id
    finally:
        engine.dispose()


def test_resolve_conflict_concurrent_opposing_outcomes_never_orphan_a_revision(
    postgres_conflict: PostgresConflict,
) -> None:
    """Ticket 25 bullet 2, race safety: two operators concurrently resolving
    the *same* conflict with opposite outcomes must never both win, and the
    loser must never leave behind an untracked revision.

    Caught by review: an earlier draft materialized ``accept="conflicting"``'s
    REPAIR revision *before* attempting a conditional ``UPDATE ... WHERE
    status = 'PENDING'``. A concurrent ``accept="existing"`` resolve that won
    that UPDATE first left the already-materialized REPAIR revision
    permanently orphaned -- created, but referenced by nothing (the closed
    conflict's own ``repair_revision_id`` would point at the parent, not it).
    The fix locks the conflict row (``SELECT ... FOR UPDATE``) before either
    branch runs, so the loser finds the row already ``REPAIRED`` and never
    calls ``materialize_repair`` at all -- provable only against real
    Postgres locking, not SQLite (which has no row-level lock semantics to
    serialize the two threads in the first place).
    """

    setup_engine = create_engine(postgres_conflict.database_url)
    try:
        ledger = AcquisitionLedger(setup_engine)
        revisions = SourceRevisionLedger(setup_engine)
        conflicts = ConflictLedger(setup_engine)

        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-conflict-race",
                source_family="filing_artifact",
                logical_source_key="conflict-race/document",
                source_url="https://www.sec.gov/Archives/conflict-race.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="discovery-manifest-1",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="FETCH_SOURCE",
            )
        )
        lease = ledger.claim_fetch(decision.decision_id, worker_id="worker-1", lease_seconds=300)
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="worker-1",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/original-hash-race",
        )
        parent = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="original-hash-race",
            canonical_source_hash="original-hash-race",
            domain_content_hash="original-hash-race",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )
        conflict = conflicts.record_evidence_conflict(
            relative_path="filings/sec/conflict-race/primary.xml",
            existing_content_hash="original-hash-race",
            new_content_hash="conflicting-hash-race",
            quarantine_bronze_reference=(
                "filings/sec/conflict-race/primary.xml.conflict/conflicting-hash-race"
            ),
            source_family="filing_artifact",
            logical_source_key="conflict-race/document",
        )

        barrier = threading.Barrier(2)
        results: dict[str, str] = {}

        def _attempt(accept: str, auth_ref: str) -> None:
            engine = create_engine(postgres_conflict.database_url)
            try:
                thread_conflicts = ConflictLedger(engine)
                barrier.wait()
                try:
                    thread_conflicts.resolve_conflict(
                        conflict.conflict_id,
                        parent_revision_id=parent.revision_id,
                        accept=accept,
                        operator_authorization_reference=auth_ref,
                        reason=f"{accept} thread resolution attempt",
                    )
                    results[accept] = "ok"
                except ConflictAlreadyResolved:
                    results[accept] = "rejected"
            finally:
                engine.dispose()

        thread_a = threading.Thread(target=_attempt, args=("existing", "jira/OPS-RACE-A"))
        thread_b = threading.Thread(target=_attempt, args=("conflicting", "jira/OPS-RACE-B"))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=30)
        thread_b.join(timeout=30)

        assert set(results) == {"existing", "conflicting"}
        # Exactly one side won and applied its outcome; the other was
        # rejected as a mismatched replay of an already-settled conflict --
        # both winning, or both being rejected, would itself be a bug.
        assert sorted(results.values()) == ["ok", "rejected"]

        repair_row_count = int(
            _psql_scalar(
                postgres_conflict.container,
                "SELECT count(*) FROM source_revision WHERE parent_revision_id = "
                f"'{parent.revision_id}' AND revision_relationship = 'REPAIR';",
            )
        )
        if results["conflicting"] == "ok":
            # "conflicting" won: exactly one REPAIR revision exists -- the
            # winner's, not a second orphaned one from the loser.
            assert repair_row_count == 1
        else:
            # "existing" won: "conflicting" never reached materialize_repair
            # at all, having found the row already REPAIRED under the lock --
            # zero REPAIR revisions, not one orphaned and unreferenced.
            assert repair_row_count == 0
    finally:
        setup_engine.dispose()
