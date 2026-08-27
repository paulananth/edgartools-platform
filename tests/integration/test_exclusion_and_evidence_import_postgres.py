"""Real-Postgres integration coverage for Ticket 34's exclusion-reason and
evidence-import mechanisms.

Same rationale as ``test_conflict_postgres.py``'s own docstring: SQLite-
backed unit tests (``tests/acquisition/test_ledger.py``,
``test_evidence_import.py``) prove the ledger logic, but migration 017's
self-managing rerun path and the real GRANT-level fencing on
``source_evidence_import`` (owned by 013's ``edgartools_acquisition_owner``,
operational GRANTs to the existing ``edgartools_acquisition_operator`` role
-- no new role provisioned) are only exercisable against a real Postgres
role graph.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.acquisition.evidence_import import EvidenceImportLedger
from edgar_warehouse.acquisition.ledger import (
    AcquisitionLedger,
    DecisionCause,
    DecisionOwnerRole,
    FetchDecisionRequest,
    FetchDisposition,
)
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.mdm.migrations import runtime as migrations

POSTGRES_IMAGE = "postgres:16-alpine"
LEDGER_MIGRATION = (
    Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations" / "013_acquisition_ledger.sql"
)
EXCLUSION_IMPORT_MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "017_source_exclusion_and_evidence_import.sql"
)


@dataclass(frozen=True)
class PostgresExclusionImport:
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


def _psql_file(container: str, remote_path: str) -> subprocess.CompletedProcess[str]:
    return _run(
        "docker", "exec", "-e", "PGPASSWORD=test", container,
        "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres", "-f", remote_path,
    )


@pytest.fixture(scope="module")
def postgres_exclusion_import() -> Iterator[PostgresExclusionImport]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket34-{uuid.uuid4().hex[:10]}"
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

        copied = _run(
            "docker", "cp", str(EXCLUSION_IMPORT_MIGRATION), f"{container}:/tmp/exclusion_import.sql"
        )
        assert copied.returncode == 0, copied.stderr
        migrated = _psql_file(container, "/tmp/exclusion_import.sql")
        assert migrated.returncode == 0, migrated.stderr

        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresExclusionImport(
            container=container,
            database_url=f"postgresql+psycopg2://application:test@127.0.0.1:{port}/postgres",
            admin_database_url=f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres",
        )
    finally:
        _run("docker", "stop", container)


def test_apply_exclusion_and_evidence_import_migration_rerun_against_real_postgres(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    """Same self-managing shape as 015's own rerun proof: `application` is
    never a member of `edgartools_acquisition_owner`, so a rerun through the
    application engine silently skips (False); only the admin engine (a
    member via 013's own DO block) can actually manage a rerun."""

    application_engine = create_engine(postgres_exclusion_import.database_url)
    admin_engine = create_engine(postgres_exclusion_import.admin_database_url)
    try:
        result = migrations._apply_exclusion_and_evidence_import_migration(application_engine)
        assert result is False

        admin_result = migrations._apply_exclusion_and_evidence_import_migration(admin_engine)
        assert admin_result is True
    finally:
        application_engine.dispose()
        admin_engine.dispose()


def test_repeated_full_migration_reruns_survive_the_widened_view(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    """Regression test: 013's own source_change_status view-recreation
    statement unconditionally reasserts a 12-column shape on every owner-
    privileged rerun -- but 017 appends a 13th (exclusion_reason). Postgres
    refuses to narrow a view back down via CREATE OR REPLACE ("cannot drop
    columns from view"), so a naive rerun of the *whole* 013-then-017
    sequence (exactly what a real admin-privileged `mdm migrate` rerun does
    -- e.g. a disaster-recovery re-provisioning) would abort permanently
    the moment it hit that statement, reproduced live before 013's own view
    statement was made defensive against this. Runs the real admin-engine
    rerun sequence twice (not once) to prove it's durably safe, not just
    safe on the very first post-widen rerun."""

    admin_engine = create_engine(postgres_exclusion_import.admin_database_url)
    try:
        for _ in range(2):
            ledger_result = migrations._apply_acquisition_ledger_migration(admin_engine)
            assert ledger_result is True
            exclusion_result = migrations._apply_exclusion_and_evidence_import_migration(
                admin_engine
            )
            assert exclusion_result is True

        columns = _psql(
            postgres_exclusion_import.container,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'source_change_status' "
            "AND column_name = 'exclusion_reason';",
        )
        assert columns.returncode == 0, columns.stderr
        assert "exclusion_reason" in columns.stdout
    finally:
        admin_engine.dispose()


def test_exclusion_reason_check_constraint_is_real_at_the_database_level(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    """The "reasoned, not just authorized" rule is a real database-level
    constraint, not just Python-side validation -- proven by trying to
    insert an OPERATOR_EXCLUDED row with no exclusion_reason directly under
    the owning role, bypassing the ledger's own Python check entirely."""

    bypass = _psql(
        postgres_exclusion_import.container,
        """
        SET ROLE edgartools_acquisition_owner;
        INSERT INTO source_observation_cursor VALUES
            ('filing_artifact', 'unreasoned-bypass/document', 1);
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action,
            operator_authorization_reference
        ) VALUES (
            'candidate-unreasoned-bypass', 'filing_artifact',
            'unreasoned-bypass/document',
            'https://www.sec.gov/Archives/unreasoned-bypass.txt', 1,
            'OPERATOR_REQUEST', 'operator-request-bypass', 'ACQUISITION_OPERATOR',
            'OPERATOR_EXCLUDED', 'attempted unreasoned exclusion', 'NONE',
            'operator-authorization-bypass'
        );
        """,
    )
    assert bypass.returncode != 0
    assert "ck_source_fetch_decision_exclusion_reason" in bypass.stderr


def test_exclusion_reason_is_visible_on_the_real_source_change_status_view(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    """Ticket 34 bullet 1: "visible in Source Change Status" means the real
    source_change_status view (013's own comment: "ad-hoc operator queries
    against Postgres directly"), not only the Python SourceChangeStatus
    dataclass -- an operator querying this view directly must be able to
    see *why* something was excluded, not just that it was."""

    seeded = _psql(
        postgres_exclusion_import.container,
        """
        SET ROLE edgartools_acquisition_owner;
        INSERT INTO source_observation_cursor VALUES
            ('filing_artifact', 'view-visibility/document', 1);
        INSERT INTO source_fetch_decision (
            candidate_id, source_family, logical_source_key, source_url,
            observation_position, cause, cause_reference, owner_role,
            fetch_disposition, blocker, next_action,
            operator_authorization_reference, exclusion_reason
        ) VALUES (
            'candidate-view-visibility', 'filing_artifact',
            'view-visibility/document',
            'https://www.sec.gov/Archives/view-visibility.txt', 1,
            'OPERATOR_REQUEST', 'operator-request-view', 'ACQUISITION_OPERATOR',
            'OPERATOR_EXCLUDED', 'view visibility exclusion', 'NONE',
            'operator-authorization-view', 'Excluded pending legal review.'
        );
        """,
    )
    assert seeded.returncode == 0, seeded.stderr

    queried = _psql(
        postgres_exclusion_import.container,
        "SELECT exclusion_reason FROM source_change_status "
        "WHERE candidate_id = 'candidate-view-visibility';",
    )
    assert queried.returncode == 0, queried.stderr
    assert "Excluded pending legal review." in queried.stdout


def test_evidence_import_table_is_owned_by_the_owner_role_and_fenced_from_application(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    owner = _psql(
        postgres_exclusion_import.container,
        "SELECT tableowner FROM pg_tables WHERE tablename = 'source_evidence_import';",
    )
    assert owner.returncode == 0, owner.stderr
    assert "edgartools_acquisition_owner" in owner.stdout

    direct_insert = _psql(
        postgres_exclusion_import.container,
        """
        INSERT INTO source_evidence_import (
            source_family, logical_source_key, source_environment,
            source_bronze_reference, expected_checksum, raw_evidence_hash,
            local_bronze_reference, operator_authorization_reference, reason
        ) VALUES (
            'filing_artifact', 'k', 'dev', 'ref', 'h', 'h', 'filing_artifact/h',
            'auth', 'direct bypass attempt'
        );
        """,
        user="application",
    )
    assert direct_insert.returncode != 0
    assert "permission denied for table source_evidence_import" in direct_insert.stderr


def test_only_acquisition_operator_can_insert_into_source_evidence_import(
    postgres_exclusion_import: PostgresExclusionImport,
) -> None:
    """Ticket 34's own GRANT design: `edgartools_acquisition_operator` gets
    INSERT+SELECT; every other operational role gets SELECT only -- proven
    at the GRANT level, not just by which Python method happens to call it,
    per this codebase's own established Ticket-20 lesson (a hand-rolled
    application-code check proves nothing a direct-SQL caller can't bypass)."""

    worker_insert = _psql(
        postgres_exclusion_import.container,
        """
        SET ROLE edgartools_acquisition_worker;
        INSERT INTO source_evidence_import (
            source_family, logical_source_key, source_environment,
            source_bronze_reference, expected_checksum, raw_evidence_hash,
            local_bronze_reference, operator_authorization_reference, reason
        ) VALUES (
            'filing_artifact', 'k', 'dev', 'ref-worker', 'h', 'h',
            'filing_artifact/h', 'auth', 'worker attempted insert'
        );
        """,
        user="application",
    )
    assert worker_insert.returncode != 0
    assert "permission denied for table source_evidence_import" in worker_insert.stderr

    operator_insert = _psql(
        postgres_exclusion_import.container,
        """
        SET ROLE edgartools_acquisition_operator;
        INSERT INTO source_evidence_import (
            source_family, logical_source_key, source_environment,
            source_bronze_reference, expected_checksum, raw_evidence_hash,
            local_bronze_reference, operator_authorization_reference, reason
        ) VALUES (
            'filing_artifact', 'k', 'dev', 'ref-operator', 'h', 'h',
            'filing_artifact/h', 'auth', 'genuine operator insert'
        );
        """,
        user="application",
    )
    assert operator_insert.returncode == 0, operator_insert.stderr


def test_evidence_import_ledger_round_trip_against_real_postgres(
    postgres_exclusion_import: PostgresExclusionImport, tmp_path
) -> None:
    engine = create_engine(postgres_exclusion_import.database_url)
    bronze_root = StorageLocation(str(tmp_path / "bronze"))
    try:
        importer = EvidenceImportLedger(engine, bronze_root)
        payload = b"<XML>real postgres import round trip</XML>"
        checksum = hashlib.sha256(payload).hexdigest()

        imported = importer.import_evidence(
            source_family="filing_artifact",
            logical_source_key="pg-import/document",
            source_environment="dev",
            source_bronze_reference="filing_artifact/pg-import-source",
            payload=payload,
            expected_checksum=checksum,
            operator_authorization_reference="pg-import-authorization",
            reason="Real Postgres round trip proof.",
        )

        assert imported.raw_evidence_hash == checksum
        stored = (tmp_path / "bronze" / "filing_artifact" / checksum).read_bytes()
        assert stored == payload

        # The resulting local reference is immediately usable as a normal
        # ALREADY_CAPTURED_VERIFIED verified_evidence_reference -- no new
        # disposition or Facade path needed for it to "become processable".
        ledger = AcquisitionLedger(engine)
        status = ledger.create_fetch_decision(
            FetchDecisionRequest(
                candidate_id="candidate-imported-evidence",
                source_family="filing_artifact",
                logical_source_key="pg-import/document",
                source_url="https://www.sec.gov/Archives/pg-import.txt",
                cause=DecisionCause.OPERATOR_REQUEST,
                cause_reference="pg-import-authorization",
                disposition=FetchDisposition.ALREADY_CAPTURED_VERIFIED,
                blocker="imported from another environment",
                next_action="NONE",
                owner_role=DecisionOwnerRole.ACQUISITION_OPERATOR,
                verified_evidence_reference=imported.local_bronze_reference,
            )
        )
        assert status.is_terminal is True
        assert status.fetch_disposition is FetchDisposition.ALREADY_CAPTURED_VERIFIED
    finally:
        engine.dispose()
