from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
    FetchWorkState,
    StaleFencingToken,
)
from edgar_warehouse.acquisition.processing import (
    ExpectedProducerOutcome,
    ExpectedProducerSpec,
    PriorRevisionNotSettled,
    ProcessingLedger,
    SilverFinalizer,
    SilverOutcome,
)
from edgar_warehouse.acquisition.revisions import (
    ContentImpact,
    RevisionNotEligible,
    SourceRevisionLedger,
)
from edgar_warehouse.mdm.migrations import runtime as migrations

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "013_acquisition_ledger.sql"
)


@dataclass(frozen=True)
class PostgresLedger:
    container: str
    database_url: str
    admin_database_url: str


def _run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _psql(
    container: str,
    sql: str,
    *,
    user: str = "postgres",
) -> subprocess.CompletedProcess[str]:
    return _run(
        "docker",
        "exec",
        "-i",
        "-e",
        "PGPASSWORD=test",
        container,
        "psql",
        "-h",
        "127.0.0.1",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        "postgres",
        input_text=sql,
    )


@pytest.fixture(scope="module")
def postgres_ledger() -> Iterator[PostgresLedger]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket14-{uuid.uuid4().hex[:10]}"
    started = _run(
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        container,
        "-p",
        "127.0.0.1::5432",
        "-e",
        "POSTGRES_PASSWORD=test",
        POSTGRES_IMAGE,
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
        copied = _run("docker", "cp", str(MIGRATION), f"{container}:/tmp/ledger.sql")
        assert copied.returncode == 0, copied.stderr
        migrated = _run(
            "docker",
            "exec",
            "-e",
            "PGPASSWORD=test",
            container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-f",
            "/tmp/ledger.sql",
        )
        assert migrated.returncode == 0, migrated.stderr
        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresLedger(
            container=container,
            database_url=(
                f"postgresql+psycopg2://application:test@127.0.0.1:{port}/postgres"
            ),
            admin_database_url=(
                f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres"
            ),
        )
    finally:
        _run("docker", "stop", container)


def test_postgres_roles_proofs_and_fencing_are_enforced(
    postgres_ledger: PostgresLedger,
) -> None:
    coordinator = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_observation_cursor VALUES
            ('filing_artifact', 'accession/document', 1);
        INSERT INTO source_fetch_decision (
            decision_id, candidate_id, source_family, logical_source_key,
            source_url, observation_position, cause, cause_reference,
            owner_role, fetch_disposition, blocker, next_action
        ) VALUES (
            '00000000-0000-0000-0000-000000000014', 'candidate-real-pg',
            'filing_artifact', 'accession/document',
            'https://www.sec.gov/Archives/example.txt', 1,
            'CAPTURED_DISCOVERY', 'manifest-1', 'ACQUISITION_COORDINATOR',
            'FETCH_AUTHORIZED', NULL, 'ACQUIRE_FETCH_LEASE'
        );
        INSERT INTO source_fetch_work VALUES (
            '00000000-0000-0000-0000-000000000014', 'filing_artifact',
            'accession/document', 'READY', 0, NULL, NULL,
            'ACQUISITION_COORDINATOR', NOW()
        );
        SELECT record_initial_source_fetch_transition(
            '00000000-0000-0000-0000-000000000014',
            'ACQUISITION_COORDINATOR'
        );
        """,
        user="application",
    )
    assert coordinator.returncode == 0, coordinator.stderr

    worker = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_worker;
        SELECT fencing_token FROM claim_source_fetch(
            '00000000-0000-0000-0000-000000000014', 'worker-1', 60, NOW()
        );
        SELECT finalize_source_fetch(
            '00000000-0000-0000-0000-000000000014',
            'worker-1', 1, 'FAILED', NOW()
        );
        SELECT fencing_token FROM claim_source_fetch(
            '00000000-0000-0000-0000-000000000014', 'worker-2', 60, NOW()
        );
        SELECT fetch_state, next_action FROM source_change_status
        WHERE decision_id = '00000000-0000-0000-0000-000000000014';
        """,
        user="application",
    )
    assert worker.returncode == 0, worker.stderr
    assert "             1" in worker.stdout
    assert "             2" in worker.stdout
    assert "LEASED" in worker.stdout
    assert "FETCH_SOURCE" in worker.stdout

    forged = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_worker;
        INSERT INTO source_fetch_transition (
            decision_id, from_state, to_state, owner_role,
            fencing_token, worker_id, reason
        ) VALUES (
            '00000000-0000-0000-0000-000000000014', 'LEASED', 'CAPTURED',
            'ACQUISITION_WORKER', 2, 'worker-2', 'FORGED'
        );
        """,
        user="application",
    )
    assert forged.returncode != 0
    assert "permission denied for table source_fetch_transition" in forged.stderr

    cross_role = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action,
            operator_authorization_reference
        ) VALUES (
            'candidate-cross-role', 'filing_artifact', 'cross-role/document',
            'https://www.sec.gov/Archives/cross-role.txt', 1,
            'OPERATOR_REQUEST', 'operator-request-cross-role',
            'ACQUISITION_OPERATOR', 'OPERATOR_EXCLUDED',
            'cross-role exclusion', 'NONE', 'operator-proof-cross-role'
        );
        """,
        user="application",
    )
    assert cross_role.returncode != 0
    assert "does not own ACQUISITION_OPERATOR transition" in cross_role.stderr

    universal_login = _psql(
        postgres_ledger.container,
        """
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action, scope_proof_reference
        ) VALUES (
            'candidate-universal-login', 'filing_artifact', 'universal/document',
            'https://www.sec.gov/Archives/universal.txt', 1,
            'CAPTURED_DISCOVERY', 'manifest-universal',
            'ACQUISITION_COORDINATOR', 'OUT_OF_SCOPE',
            'outside universe', 'NONE', 'universe-proof'
        );
        """,
        user="application",
    )
    assert universal_login.returncode != 0
    assert "permission denied for table source_fetch_decision" in universal_login.stderr

    stale = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_worker;
        SELECT finalize_source_fetch(
            '00000000-0000-0000-0000-000000000014',
            'worker-1', 1, 'CAPTURED', NOW(), 'filing_artifact/deadbeef'
        );
        """,
        user="application",
    )
    assert stale.returncode != 0
    assert "stale fencing token" in stale.stderr

    unproved = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action
        ) VALUES (
            'candidate-unproved', 'filing_artifact', 'other/document',
            'https://www.sec.gov/Archives/other.txt', 1,
            'CAPTURED_DISCOVERY', 'manifest-2', 'ACQUISITION_COORDINATOR',
            'OUT_OF_SCOPE', 'outside universe', 'NONE'
        );
        """,
        user="application",
    )
    assert unproved.returncode != 0
    assert "ck_source_fetch_decision_scope_proof" in unproved.stderr

    empty_proof = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action, scope_proof_reference
        ) VALUES (
            'candidate-empty-proof', 'filing_artifact', 'empty-proof/document',
            'https://www.sec.gov/Archives/empty-proof.txt', 1,
            'CAPTURED_DISCOVERY', 'manifest-empty', 'ACQUISITION_COORDINATOR',
            'OUT_OF_SCOPE', 'outside universe', 'NONE', '   '
        );
        """,
        user="application",
    )
    assert empty_proof.returncode != 0
    assert "ck_source_fetch_decision_scope_proof" in empty_proof.stderr

    operator = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_operator;
        INSERT INTO source_observation_cursor VALUES
            ('filing_artifact', 'operator/document', 1);
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action,
            operator_authorization_reference
        ) VALUES (
            'candidate-operator', 'filing_artifact', 'operator/document',
            'https://www.sec.gov/Archives/operator.txt', 1,
            'OPERATOR_REQUEST', 'operator-request-1', 'ACQUISITION_OPERATOR',
            'OPERATOR_EXCLUDED', 'operator exclusion', 'NONE',
            'operator-authorization-1'
        );
        """,
        user="application",
    )
    assert operator.returncode == 0, operator.stderr


def test_snowflake_write_ambient_access_is_revoked_on_the_nine_ledger_objects(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 30 (change-propagation map): live prod verification found
    `application` also carries an ambient, platform-managed membership in
    Snowflake Postgres's `snowflake_write` role, independently granting full
    DML on these nine objects regardless of the `application`-scoped REVOKE
    above. `snowflake_write` doesn't exist in this fixture's vanilla
    Postgres, so the migration's new REVOKE block is a guarded no-op during
    the module fixture's own setup (proving the guard doesn't error against
    a plain Postgres instance) -- this test creates a role that plays
    `snowflake_write`'s part, grants it access the way the platform's own
    default-ACL automation would, then re-applies the (idempotent)
    migration and proves that access is gone afterward.
    """
    created = _psql(
        postgres_ledger.container,
        """
        CREATE ROLE snowflake_write NOLOGIN;
        GRANT SELECT, INSERT, UPDATE, DELETE ON source_fetch_decision TO snowflake_write;
        GRANT SELECT ON source_change_status TO snowflake_write;
        """,
    )
    assert created.returncode == 0, created.stderr

    def _has_privilege(table: str) -> bool:
        result = _psql(
            postgres_ledger.container,
            f"SELECT has_table_privilege('snowflake_write', '{table}', 'SELECT');",
        )
        assert result.returncode == 0, result.stderr
        row = result.stdout.splitlines()[2].strip()
        assert row in ("t", "f"), result.stdout
        return row == "t"

    assert _has_privilege("source_fetch_decision") is True
    assert _has_privilege("source_change_status") is True

    copied = _run(
        "docker", "cp", str(MIGRATION), f"{postgres_ledger.container}:/tmp/ledger-rerun.sql"
    )
    assert copied.returncode == 0, copied.stderr
    reapplied = _run(
        "docker",
        "exec",
        "-e",
        "PGPASSWORD=test",
        postgres_ledger.container,
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-f",
        "/tmp/ledger-rerun.sql",
    )
    assert reapplied.returncode == 0, reapplied.stderr

    assert _has_privilege("source_fetch_decision") is False
    assert _has_privilege("source_change_status") is False


def test_privileged_rerun_skip_is_logged_not_silent(
    postgres_ledger: PostgresLedger, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ticket 43 (change-propagation map): `application` -- the only role
    the real prod deploy path (`mdm migrate`) ever connects as -- has no
    membership in `edgartools_acquisition_owner` by design, so a rerun of
    the already-installed migration 013 silently returns False with no
    error. That silence is exactly what let the "MDM Postgres migration-011
    schema drift" incident (CLAUDE.md) go undetected for a day: a rerun
    reporting success while never touching the schema it claimed to. This
    test calls the real function against the real Postgres role graph the
    module fixture already set up (connecting as `application`, which the
    fixture's own migration already proved lacks owner membership) and
    proves the skip is now an observable JSON event, not silence.
    """
    engine = create_engine(postgres_ledger.database_url)
    try:
        applied = migrations._apply_acquisition_ledger_migration(engine)
    finally:
        engine.dispose()

    assert applied is False
    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines() if line.strip()]
    skip_events = [e for e in events if e.get("event") == "mdm_migration_privileged_rerun_skipped"]
    assert len(skip_events) == 1, captured.err
    assert skip_events[0]["migration"] == "013_acquisition_ledger"
    assert skip_events[0]["owner_role"] == "edgartools_acquisition_owner"
    assert skip_events[0]["reason"] == "connecting_role_lacks_owner_membership"


def test_processor_and_silver_finalizer_boundaries_are_grant_enforced_not_just_python_checked(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 25 bullet 5: coordinator/worker/processor/silver-finalizer/
    operator transition ownership stays separate at the real Postgres GRANT
    level, not only behind Python's ``require_processor_role``/
    ``require_silver_finalizer_role`` checks (trivially bypassable by any
    caller that talks to Postgres directly instead of through
    ``revisions.py``/``processing.py``). ``test_postgres_roles_proofs_and_
    fencing_are_enforced`` above already proves the coordinator-vs-operator
    boundary (a trigger-level cause-ownership check); this covers the two
    boundaries that check doesn't: worker-vs-processor (INSERT on
    ``source_revision``) and processor-vs-silver-finalizer (the
    column-scoped UPDATE grants on ``source_expected_producer``/
    ``source_processing_decision`` -- see models.py's
    ``SourceExpectedProducerRecord`` docstring for why no role-check trigger
    backs those up, only the GRANT itself).
    """

    worker_insert = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_worker;
        INSERT INTO source_revision (
            source_family, logical_source_key, observation_position,
            raw_evidence_hash, canonical_source_hash, domain_content_hash,
            contract_version, parser_version, schema_version,
            configuration_version, completeness_type,
            bronze_artifact_reference, content_impact
        ) VALUES (
            'filing_artifact', 'boundary-proof/document', 1,
            'h', 'h', 'h', 'v1', 'v1', 'v1', 'v1', 'COMPLETE',
            'filing_artifact/h', 'CHANGED'
        );
        """,
        user="application",
    )
    assert worker_insert.returncode != 0
    assert "permission denied for table source_revision" in worker_insert.stderr

    coordinator_insert = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_revision (
            source_family, logical_source_key, observation_position,
            raw_evidence_hash, canonical_source_hash, domain_content_hash,
            contract_version, parser_version, schema_version,
            configuration_version, completeness_type,
            bronze_artifact_reference, content_impact
        ) VALUES (
            'filing_artifact', 'boundary-proof-2/document', 1,
            'h', 'h', 'h', 'v1', 'v1', 'v1', 'v1', 'COMPLETE',
            'filing_artifact/h', 'CHANGED'
        );
        """,
        user="application",
    )
    assert coordinator_insert.returncode != 0
    assert "permission denied for table source_revision" in coordinator_insert.stderr

    processor_finalizer_update = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_processor;
        UPDATE source_processing_decision SET silver_outcome = 'PUBLISHED'
        WHERE processing_decision_id = '00000000-0000-0000-0000-000000000000';
        """,
        user="application",
    )
    assert processor_finalizer_update.returncode != 0
    assert (
        "permission denied for table source_processing_decision"
        in processor_finalizer_update.stderr
    )

    processor_expected_producer_update = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_processor;
        UPDATE source_expected_producer SET outcome = 'VERIFIED'
        WHERE expected_producer_id = '00000000-0000-0000-0000-000000000000';
        """,
        user="application",
    )
    assert processor_expected_producer_update.returncode != 0
    assert (
        "permission denied for table source_expected_producer"
        in processor_expected_producer_update.stderr
    )


def test_finalize_source_fetch_persists_failure_detail_and_rejects_it_with_captured(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 17 bullet 3, against real Postgres: the widened 7-arg
    finalize_source_fetch persists a caller-supplied failure detail as
    durable Fetch Attempt evidence, and the server-side guard rejects
    supplying one alongside CAPTURED (defense in depth -- the same rule
    ledger.py already enforces in Python).
    """
    engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(engine)
    try:
        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-pg-failure-detail",
                source_family="filing_artifact",
                logical_source_key="pg-failure-detail/document",
                source_url="https://www.sec.gov/Archives/pg-failure-detail.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-failure-detail",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        lease = ledger.claim_fetch(
            decision.decision_id, worker_id="pg-worker-1", lease_seconds=60
        )

        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="pg-worker-1",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.FAILED,
            failure_detail="HTTP 503 Service Unavailable",
        )

        assert (
            ledger.latest_transition_reason(decision.decision_id)
            == "HTTP 503 Service Unavailable"
        )
    finally:
        engine.dispose()

    server_side_reject = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_coordinator;
        INSERT INTO source_observation_cursor VALUES
            ('filing_artifact', 'pg-bad-detail/document', 1);
        INSERT INTO source_fetch_decision (
            decision_id, candidate_id, source_family, logical_source_key,
            source_url, observation_position, cause, cause_reference,
            owner_role, fetch_disposition, blocker, next_action
        ) VALUES (
            '00000000-0000-0000-0000-000000000099', 'candidate-pg-bad-detail',
            'filing_artifact', 'pg-bad-detail/document',
            'https://www.sec.gov/Archives/pg-bad-detail.txt', 1,
            'CAPTURED_DISCOVERY', 'manifest-pg-bad-detail', 'ACQUISITION_COORDINATOR',
            'FETCH_AUTHORIZED', NULL, 'ACQUIRE_FETCH_LEASE'
        );
        INSERT INTO source_fetch_work VALUES (
            '00000000-0000-0000-0000-000000000099', 'filing_artifact',
            'pg-bad-detail/document', 'READY', 0, NULL, NULL,
            'ACQUISITION_COORDINATOR', NOW()
        );
        SELECT record_initial_source_fetch_transition(
            '00000000-0000-0000-0000-000000000099',
            'ACQUISITION_COORDINATOR'
        );
        SET ROLE edgartools_acquisition_worker;
        SELECT fencing_token FROM claim_source_fetch(
            '00000000-0000-0000-0000-000000000099', 'pg-worker-2', 60, NOW()
        );
        SELECT finalize_source_fetch(
            '00000000-0000-0000-0000-000000000099',
            'pg-worker-2', 1, 'CAPTURED', NOW(),
            'filing_artifact/deadbeef', 'this must be rejected'
        );
        """,
        user="application",
    )
    assert server_side_reject.returncode != 0
    assert "failure detail must not be set" in server_side_reject.stderr


def test_finalize_fetch_raises_python_stale_fencing_token_against_real_postgres(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 17 bullet 5, against real Postgres via the actual
    AcquisitionLedger.finalize_fetch Python API (not raw psql -- prior
    coverage of this exact race only asserted on stderr text from a raw SQL
    call, never on what exception TYPE the Python wrapper raises).

    facade.py's retry helper does ``except StaleFencingToken: raise`` to
    avoid retrying a deterministic race (a newer attempt already won) and
    misclassifying it as an orphaned capture. That guard is only correct if
    a stale-token finalize on Postgres actually raises this Python type --
    prove it does, not just that some error occurs.
    """
    engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(engine)
    try:
        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-pg-stale-token-type",
                source_family="filing_artifact",
                logical_source_key="pg-stale-token-type/document",
                source_url="https://www.sec.gov/Archives/pg-stale-token-type.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-stale-token-type",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        stale_lease = ledger.claim_fetch(
            decision.decision_id, worker_id="pg-worker-stale", lease_seconds=1
        )
        fresh_lease = ledger.claim_fetch(
            decision.decision_id,
            worker_id="pg-worker-fresh",
            lease_seconds=60,
            now=datetime.now(UTC) + timedelta(seconds=2),
        )
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="pg-worker-fresh",
            fencing_token=fresh_lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/won-the-race",
        )

        with pytest.raises(StaleFencingToken):
            ledger.finalize_fetch(
                decision.decision_id,
                worker_id="pg-worker-stale",
                fencing_token=stale_lease.fencing_token,
                final_state=FetchWorkState.FAILED,
                failure_detail="stale worker's belated failure report",
            )

        status = ledger.source_change_status(decision.decision_id)
        assert status.fetch_state is FetchWorkState.CAPTURED
        assert status.captured_artifact_reference == "filing_artifact/won-the-race"
    finally:
        engine.dispose()


def test_repository_uses_application_role_and_postgres_uuid_columns(
    postgres_ledger: PostgresLedger,
) -> None:
    engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(engine)
    try:
        terminal = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-repository-terminal",
                source_family="filing_artifact",
                logical_source_key="repository/terminal",
                source_url="https://www.sec.gov/Archives/repository-terminal.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-repository-1",
                disposition=FetchDisposition.OUT_OF_SCOPE,
                blocker="outside acquisition universe v1",
                next_action="NONE",
                scope_proof_reference="universe-v1/repository-terminal",
            )
        )
        authorized = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-repository-fetch",
                source_family="filing_artifact",
                logical_source_key="repository/fetch",
                source_url="https://www.sec.gov/Archives/repository-fetch.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-repository-2",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        operator_authorized = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-repository-operator-fetch",
                source_family="filing_artifact",
                logical_source_key="repository/operator-fetch",
                source_url=(
                    "https://www.sec.gov/Archives/repository-operator-fetch.txt"
                ),
                cause=DecisionCause.OPERATOR_REQUEST,
                cause_reference="operator-repair-1",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
                owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
            )
        )
        first = ledger.claim_fetch(
            authorized.decision_id,
            worker_id="repository-worker-1",
            lease_seconds=60,
        )
        failed = ledger.finalize_fetch(
            authorized.decision_id,
            worker_id="repository-worker-1",
            fencing_token=first.fencing_token,
            final_state=FetchWorkState.FAILED,
        )
        retried = ledger.claim_fetch(
            authorized.decision_id,
            worker_id="repository-worker-2",
            lease_seconds=60,
        )

        assert terminal.observation_position == 1
        assert ledger.source_change_status(terminal.decision_id) == terminal
        assert operator_authorized.fetch_state is FetchWorkState.READY
        assert failed.next_action == "RETRY_FETCH"
        assert retried.fencing_token == 2
        assert migrations._apply_acquisition_ledger_migration(engine) is False

        admin_engine = create_engine(postgres_ledger.admin_database_url)
        try:
            assert migrations._apply_acquisition_ledger_migration(admin_engine) is True
        finally:
            admin_engine.dispose()
    finally:
        engine.dispose()


def test_materialize_from_capture_round_trips_against_real_postgres(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 18, end-to-end against real Postgres via the actual Python
    API: a coordinator-created, worker-captured decision materializes a
    revision under the dedicated processor role, and the revision is
    genuinely immutable (the same trigger pattern proven for the other
    acquisition tables in Ticket 14).
    """

    engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)
    try:
        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-pg-revision",
                source_family="filing_artifact",
                logical_source_key="pg-revision/document",
                source_url="https://www.sec.gov/Archives/pg-revision.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-revision",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        lease = ledger.claim_fetch(
            decision.decision_id, worker_id="pg-worker-revision", lease_seconds=60
        )
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="pg-worker-revision",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/pg-revision-hash",
        )

        revision = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="pg-revision-hash",
            canonical_source_hash="pg-revision-hash",
            domain_content_hash="pg-revision-domain-hash",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )

        assert revision.decision_id == decision.decision_id
        assert revision.content_impact is ContentImpact.CHANGED
        assert revision.bronze_artifact_reference == "filing_artifact/pg-revision-hash"

        replayed = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="pg-revision-hash",
            canonical_source_hash="pg-revision-hash",
            domain_content_hash="pg-revision-domain-hash",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )
        assert replayed.revision_id == revision.revision_id

        with pytest.raises(RevisionNotEligible):
            revisions.materialize_from_capture(
                "00000000-0000-0000-0000-000000000000",
                raw_evidence_hash="x",
                canonical_source_hash="x",
                domain_content_hash="x",
                contract_version="v1",
                parser_version="v1",
                schema_version="v1",
                configuration_version="v1",
            )
    finally:
        engine.dispose()

    # The processor role -- the only role that ever writes source_revision --
    # is only ever granted SELECT/INSERT (same shape as source_fetch_decision
    # and source_fetch_transition), so an UPDATE is rejected at the grant
    # level. This is a stricter, and simpler to prove, guarantee than the
    # immutability trigger alone -- the trigger's own presence in the schema
    # is covered separately by test_migration.py's SQL-text assertions; the
    # only role that could bypass this grant check (the table owner) is
    # never reachable from the ``application`` login this test connects as.
    no_update_grant = _psql(
        postgres_ledger.container,
        f"""
        SET ROLE edgartools_acquisition_processor;
        UPDATE source_revision SET content_impact = 'NO_IMPACT'
        WHERE decision_id = (
            SELECT decision_id FROM source_fetch_decision
            WHERE candidate_id = 'candidate-pg-revision'
        );
        """,
        user="application",
    )
    assert no_update_grant.returncode != 0
    assert "permission denied for table source_revision" in no_update_grant.stderr

    # Same shape as the existing source_fetch_transition "forged" proof
    # above: edgartools_acquisition_worker has only SELECT on
    # source_revision, so this is rejected at the grant level -- the
    # dedicated enforce_acquisition_revision_role trigger is the (currently
    # unreachable from this login) defense against the table owner itself,
    # mirroring the same layering the older acquisition tables already use.
    forged_role = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_worker;
        INSERT INTO source_revision (
            decision_id, source_family, logical_source_key, observation_position,
            raw_evidence_hash, canonical_source_hash, domain_content_hash,
            contract_version, parser_version, schema_version, configuration_version,
            completeness_type, bronze_artifact_reference, content_impact
        ) VALUES (
            NULL, 'filing_artifact', 'forged/document', 999,
            'x', 'x', 'x', 'v1', 'v1', 'v1', 'v1', 'COMPLETE', 'filing_artifact/x', 'CHANGED'
        );
        """,
        user="application",
    )
    assert forged_role.returncode != 0
    assert "permission denied for table source_revision" in forged_role.stderr


def test_seals_and_finalizes_processing_decision_round_trip_against_real_postgres(
    postgres_ledger: PostgresLedger,
) -> None:
    """Ticket 19, end-to-end against real Postgres via the actual Python
    API: the processor role seals a Processing Decision and its expected
    producer set, the dedicated Silver Finalizer role records a verified
    outcome, and the same-key ordering rule genuinely blocks a later
    revision until the prior one is published -- proven through the real
    role/grant boundary, not just SQLite.
    """

    engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(engine)
    revisions = SourceRevisionLedger(engine)
    processing = ProcessingLedger(engine)
    finalizer = SilverFinalizer(engine)
    try:
        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-pg-processing",
                source_family="filing_artifact",
                logical_source_key="pg-processing/document",
                source_url="https://www.sec.gov/Archives/pg-processing.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-processing",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        lease = ledger.claim_fetch(
            decision.decision_id, worker_id="pg-worker-processing", lease_seconds=60
        )
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="pg-worker-processing",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/pg-processing-hash",
        )
        revision = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="pg-processing-hash",
            canonical_source_hash="pg-processing-hash",
            domain_content_hash="pg-processing-domain-hash",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )

        sealed = processing.seal_expected_producers(
            revision.revision_id,
            expected_producers=(
                ExpectedProducerSpec(
                    producer_name="sec_raw_object",
                    target_table="sec_raw_object",
                    scope_reference="pg-processing-accession",
                ),
            ),
        )
        assert sealed.silver_outcome is SilverOutcome.PENDING

        # A second revision for the same key must not be able to seal while
        # the first is still PENDING.
        second_decision_id = "candidate-pg-processing-2"
        second_decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id=second_decision_id,
                source_family="filing_artifact",
                logical_source_key="pg-processing/document",
                source_url="https://www.sec.gov/Archives/pg-processing-2.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-processing-2",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        second_lease = ledger.claim_fetch(
            second_decision.decision_id,
            worker_id="pg-worker-processing-2",
            lease_seconds=60,
        )
        ledger.finalize_fetch(
            second_decision.decision_id,
            worker_id="pg-worker-processing-2",
            fencing_token=second_lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/pg-processing-hash-2",
        )
        second_revision = revisions.materialize_from_capture(
            second_decision.decision_id,
            raw_evidence_hash="pg-processing-hash-2",
            canonical_source_hash="pg-processing-hash-2",
            domain_content_hash="pg-processing-domain-hash-2",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )
        with pytest.raises(PriorRevisionNotSettled):
            processing.seal_expected_producers(
                second_revision.revision_id,
                expected_producers=(
                    ExpectedProducerSpec(
                        producer_name="sec_raw_object",
                        target_table="sec_raw_object",
                        scope_reference="pg-processing-accession-2",
                    ),
                ),
            )

        published = finalizer.record_producer_outcome(
            sealed.processing_decision_id,
            "sec_raw_object",
            outcome=ExpectedProducerOutcome.VERIFIED,
            verified_reference="pg-raw-object-1",
        )
        assert published.silver_outcome is SilverOutcome.PUBLISHED

        # Now that the prior revision is PUBLISHED, the second may seal.
        second_sealed = processing.seal_expected_producers(
            second_revision.revision_id,
            expected_producers=(
                ExpectedProducerSpec(
                    producer_name="sec_raw_object",
                    target_table="sec_raw_object",
                    scope_reference="pg-processing-accession-2",
                ),
            ),
        )
        assert second_sealed.silver_outcome is SilverOutcome.PENDING
    finally:
        engine.dispose()

    # Grant-layer proof (Ticket 19's design deliberately relies on GRANTs,
    # not a role-check trigger, to split "processor seals" from "finalizer
    # records outcomes" -- see models.py's SourceExpectedProducerRecord
    # docstring): the processor has no UPDATE grant on source_expected_producer
    # at all.
    processor_update_denied = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_processor;
        UPDATE source_expected_producer SET outcome = 'VERIFIED'
        WHERE producer_name = 'sec_raw_object';
        """,
        user="application",
    )
    assert processor_update_denied.returncode != 0
    assert (
        "permission denied for table source_expected_producer"
        in processor_update_denied.stderr
    )

    # The finalizer has no INSERT grant on source_expected_producer at all.
    finalizer_insert_denied = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_silver_finalizer;
        INSERT INTO source_expected_producer (
            processing_decision_id, producer_name, target_table,
            scope_reference, outcome
        )
        SELECT processing_decision_id, 'forged-producer', 'forged_table',
               'forged-scope', 'PENDING'
        FROM source_processing_decision LIMIT 1;
        """,
        user="application",
    )
    assert finalizer_insert_denied.returncode != 0
    assert (
        "permission denied for table source_expected_producer"
        in finalizer_insert_denied.stderr
    )

    # The finalizer's UPDATE grant is column-scoped: it may update outcome/
    # verified_reference/failure_detail/updated_at, but not producer_name.
    finalizer_column_denied = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_silver_finalizer;
        UPDATE source_expected_producer SET producer_name = 'renamed'
        WHERE producer_name = 'sec_raw_object';
        """,
        user="application",
    )
    assert finalizer_column_denied.returncode != 0
    assert (
        "permission denied for table source_expected_producer"
        in finalizer_column_denied.stderr
    )

    # The finalizer's UPDATE grant on source_processing_decision is
    # similarly column-scoped: silver_outcome/settled_at only, not
    # disposition.
    finalizer_decision_column_denied = _psql(
        postgres_ledger.container,
        """
        SET ROLE edgartools_acquisition_silver_finalizer;
        UPDATE source_processing_decision SET disposition = 'QUARANTINED'
        WHERE source_family = 'filing_artifact';
        """,
        user="application",
    )
    assert finalizer_decision_column_denied.returncode != 0
    assert (
        "permission denied for table source_processing_decision"
        in finalizer_decision_column_denied.stderr
    )


def test_concurrent_producer_settlement_rollup_converges_to_published(
    postgres_ledger: PostgresLedger,
) -> None:
    """Two producers under the same Processing Decision settling on genuinely
    concurrent connections must still converge the decision to PUBLISHED
    exactly once -- proving the ``FOR UPDATE`` row lock in
    ``SilverFinalizer.record_producer_outcome`` (which the finalizer role's
    column-scoped UPDATE grant does support, unlike the processor's
    SELECT-only grant on the same table) actually closes the "both threads
    see 1 remaining PENDING" race described in processing.py's own risk
    analysis, rather than only being exercised sequentially.
    """

    from concurrent.futures import ThreadPoolExecutor

    setup_engine = create_engine(postgres_ledger.database_url)
    ledger = AcquisitionLedger(setup_engine)
    revisions = SourceRevisionLedger(setup_engine)
    processing = ProcessingLedger(setup_engine)
    try:
        decision = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-pg-rollup-race",
                source_family="filing_artifact",
                logical_source_key="pg-rollup-race/document",
                source_url="https://www.sec.gov/Archives/pg-rollup-race.txt",
                cause=DecisionCause.CAPTURED_DISCOVERY,
                cause_reference="manifest-pg-rollup-race",
                disposition=FetchDisposition.FETCH_AUTHORIZED,
                blocker=None,
                next_action="ACQUIRE_FETCH_LEASE",
            )
        )
        lease = ledger.claim_fetch(
            decision.decision_id, worker_id="pg-worker-rollup-race", lease_seconds=60
        )
        ledger.finalize_fetch(
            decision.decision_id,
            worker_id="pg-worker-rollup-race",
            fencing_token=lease.fencing_token,
            final_state=FetchWorkState.CAPTURED,
            artifact_reference="filing_artifact/pg-rollup-race-hash",
        )
        revision = revisions.materialize_from_capture(
            decision.decision_id,
            raw_evidence_hash="pg-rollup-race-hash",
            canonical_source_hash="pg-rollup-race-hash",
            domain_content_hash="pg-rollup-race-domain-hash",
            contract_version="v1",
            parser_version="v1",
            schema_version="v1",
            configuration_version="v1",
        )
        sealed = processing.seal_expected_producers(
            revision.revision_id,
            expected_producers=(
                ExpectedProducerSpec("producer-a", "table_a", "scope-a"),
                ExpectedProducerSpec("producer-b", "table_b", "scope-b"),
            ),
        )
        revision_id = revision.revision_id
    finally:
        setup_engine.dispose()

    results: list[SilverOutcome] = []

    def _settle(producer_name: str) -> None:
        engine = create_engine(postgres_ledger.database_url)
        try:
            finalizer = SilverFinalizer(engine)
            updated = finalizer.record_producer_outcome(
                sealed.processing_decision_id,
                producer_name,
                outcome=ExpectedProducerOutcome.VERIFIED,
                verified_reference=f"ref-{producer_name}",
            )
            results.append(updated.silver_outcome)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(_settle, ["producer-a", "producer-b"]))

    assert SilverOutcome.PUBLISHED in results

    verify_engine = create_engine(postgres_ledger.database_url)
    try:
        final_status = ProcessingLedger(verify_engine).read_for_revision(revision_id)
        assert final_status is not None
        assert final_status.silver_outcome is SilverOutcome.PUBLISHED
        assert {p.outcome for p in final_status.expected_producers} == {
            ExpectedProducerOutcome.VERIFIED
        }
    finally:
        verify_engine.dispose()
