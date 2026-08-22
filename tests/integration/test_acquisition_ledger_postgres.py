from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
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
)
from edgar_warehouse.mdm.migrations import runtime as migrations

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "012_acquisition_ledger.sql"
)


@dataclass(frozen=True)
class PostgresLedger:
    container: str
    database_url: str


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
            'worker-1', 1, 'CAPTURED', NOW()
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
    finally:
        engine.dispose()
