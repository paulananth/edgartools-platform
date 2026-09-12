"""Real-Postgres integration coverage for manages-fund-duplicate-rows
Ticket 03's monitor.

Same rationale as ``test_fence_monitor_postgres.py``'s docstring: this
check's whole job is grouping/comparing real ``JSONB``/date columns across
rows, which SQLite cannot model faithfully enough to prove anything about
the actual query.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.manages_fund_duplicate_monitor import (
    KNOWN_BACKLOG_CUTOFF,
    check_manages_fund_duplicates,
)

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATIONS_DIR = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"
INITIAL_SCHEMA_MIGRATION = MIGRATIONS_DIR / "001_initial_schema.sql"
SEED_DATA_MIGRATION = MIGRATIONS_DIR / "002_seed_data.sql"
TEMPORAL_CONTRACT_MIGRATION = MIGRATIONS_DIR / "006_relationship_temporal_contract.sql"

_BEFORE_CUTOFF = KNOWN_BACKLOG_CUTOFF.replace(day=19)
_AFTER_CUTOFF = KNOWN_BACKLOG_CUTOFF.replace(day=25)


@dataclass(frozen=True)
class PostgresManagesFund:
    container: str
    database_url: str


def _run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, text=True, capture_output=True, check=False)


def _psql(container: str, sql: str) -> subprocess.CompletedProcess[str]:
    return _run(
        "docker", "exec", "-i", "-e", "PGPASSWORD=test", container,
        "psql", "-h", "127.0.0.1", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
        input_text=sql,
    )


def _psql_file(container: str, path: Path, remote_name: str) -> None:
    copied = _run("docker", "cp", str(path), f"{container}:/tmp/{remote_name}")
    assert copied.returncode == 0, copied.stderr
    applied = _run(
        "docker", "exec", "-e", "PGPASSWORD=test", container,
        "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres",
        "-f", f"/tmp/{remote_name}",
    )
    assert applied.returncode == 0, applied.stderr


@pytest.fixture(scope="module")
def postgres_manages_fund() -> Iterator[PostgresManagesFund]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-manages-fund-dup-{uuid.uuid4().hex[:10]}"
    started = _run(
        "docker", "run", "-d", "--rm", "--name", container,
        "-p", "127.0.0.1::5432", "-e", "POSTGRES_PASSWORD=test", POSTGRES_IMAGE,
    )
    assert started.returncode == 0, started.stderr
    try:
        for _ in range(40):
            if _psql(container, "SELECT 1;").returncode == 0:
                break
            time.sleep(0.25)
        else:
            pytest.fail("ephemeral PostgreSQL did not become ready")

        _psql_file(container, INITIAL_SCHEMA_MIGRATION, "001.sql")
        _psql_file(container, SEED_DATA_MIGRATION, "002.sql")
        _psql_file(container, TEMPORAL_CONTRACT_MIGRATION, "006.sql")

        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresManagesFund(
            container=container,
            database_url=f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres",
        )
    finally:
        _run("docker", "stop", container)


def _insert_entity(conn, entity_type: str) -> str:
    return conn.execute(
        text("INSERT INTO mdm_entity (entity_type) VALUES (:t) RETURNING entity_id"),
        {"t": entity_type},
    ).scalar_one()


def _insert_relationship_row(
    conn,
    *,
    relationship_id: str,
    rel_type_id: str,
    source_entity_id: str,
    target_entity_id: str,
    properties: dict,
    valid_from_date: date,
    valid_to_date: date | None,
    created_at: datetime,
    is_active: bool = True,
    quarantined: bool = False,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO mdm_relationship_instance
                (relationship_id, rel_type_id, source_entity_id, target_entity_id,
                 properties, valid_from_date, valid_to_date, created_at,
                 is_active, quarantined, source_system, source_accession)
            VALUES
                (:relationship_id, :rel_type_id, :source_entity_id, :target_entity_id,
                 CAST(:properties AS JSONB), :valid_from_date, :valid_to_date, :created_at,
                 :is_active, :quarantined, 'iapd_adv_bulk', 'iapd-adv:test')
            """
        ),
        {
            "relationship_id": relationship_id,
            "rel_type_id": rel_type_id,
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "properties": _json_text(properties),
            "valid_from_date": valid_from_date,
            "valid_to_date": valid_to_date,
            "created_at": created_at,
            "is_active": is_active,
            "quarantined": quarantined,
        },
    )


def _json_text(properties: dict) -> str:
    import json

    return json.dumps(properties)


def _manages_fund_rel_type_id(conn) -> str:
    return conn.execute(
        text("SELECT rel_type_id FROM mdm_relationship_type WHERE rel_type_name = 'MANAGES_FUND'")
    ).scalar_one()


def test_clean_when_no_duplicates(postgres_manages_fund: PostgresManagesFund) -> None:
    engine = create_engine(postgres_manages_fund.database_url)
    try:
        result = check_manages_fund_duplicates(engine)
    finally:
        engine.dispose()
    assert result.is_clean
    assert result.new_duplicate_groups == ()


def test_pre_cutoff_duplicate_is_not_flagged(
    postgres_manages_fund: PostgresManagesFund,
) -> None:
    """Reproduces Ticket 01's own known-backlog shape: 4 byte-identical
    active rows on one relationship_id, all created before
    KNOWN_BACKLOG_CUTOFF -- this must NOT alert, since it's the already-
    understood, one-time historical event, not a live regression."""
    engine = create_engine(postgres_manages_fund.database_url)
    try:
        with engine.begin() as conn:
            rel_type_id = _manages_fund_rel_type_id(conn)
            adviser_id = _insert_entity(conn, "adviser")
            fund_id = _insert_entity(conn, "fund")
            relationship_id = str(uuid.uuid4())
            properties = {"private_fund_id": "805-0000000001", "source_filing_id": "1"}
            for _ in range(4):
                _insert_relationship_row(
                    conn,
                    relationship_id=relationship_id,
                    rel_type_id=rel_type_id,
                    source_entity_id=adviser_id,
                    target_entity_id=fund_id,
                    properties=properties,
                    valid_from_date=date(2026, 7, 17),
                    valid_to_date=None,
                    created_at=_BEFORE_CUTOFF,
                )

        result = check_manages_fund_duplicates(engine)
        assert result.is_clean, result.new_duplicate_groups
    finally:
        engine.dispose()


def test_post_cutoff_duplicate_is_flagged(
    postgres_manages_fund: PostgresManagesFund,
) -> None:
    """A genuinely new duplicate (created after KNOWN_BACKLOG_CUTOFF) is
    exactly the regression this check exists to catch."""
    engine = create_engine(postgres_manages_fund.database_url)
    try:
        with engine.begin() as conn:
            rel_type_id = _manages_fund_rel_type_id(conn)
            adviser_id = _insert_entity(conn, "adviser")
            fund_id = _insert_entity(conn, "fund")
            relationship_id = str(uuid.uuid4())
            properties = {"private_fund_id": "805-0000000002", "source_filing_id": "2"}
            for _ in range(2):
                _insert_relationship_row(
                    conn,
                    relationship_id=relationship_id,
                    rel_type_id=rel_type_id,
                    source_entity_id=adviser_id,
                    target_entity_id=fund_id,
                    properties=properties,
                    valid_from_date=date(2026, 9, 1),
                    valid_to_date=None,
                    created_at=_AFTER_CUTOFF,
                )

        result = check_manages_fund_duplicates(engine)
        assert not result.is_clean
        assert len(result.new_duplicate_groups) == 1
        group = result.new_duplicate_groups[0]
        assert group.relationship_id == relationship_id
        assert group.active_count == 2
    finally:
        engine.dispose()


def test_non_overlapping_distinct_properties_are_not_duplicates(
    postgres_manages_fund: PostgresManagesFund,
) -> None:
    """Two rows on the same relationship_id with genuinely different
    properties (a real, legitimate distinct-period case per
    ensure_relationship's own documented "non-overlapping windows are not
    a conflict" behavior) must never be flagged -- this check only cares
    about byte-identical duplicates, not every multi-version relationship_id."""
    engine = create_engine(postgres_manages_fund.database_url)
    try:
        with engine.begin() as conn:
            rel_type_id = _manages_fund_rel_type_id(conn)
            adviser_id = _insert_entity(conn, "adviser")
            fund_id = _insert_entity(conn, "fund")
            relationship_id = str(uuid.uuid4())
            _insert_relationship_row(
                conn,
                relationship_id=relationship_id,
                rel_type_id=rel_type_id,
                source_entity_id=adviser_id,
                target_entity_id=fund_id,
                properties={"private_fund_id": "805-0000000003", "source_filing_id": "3"},
                valid_from_date=date(2025, 1, 1),
                valid_to_date=date(2025, 6, 1),
                created_at=_AFTER_CUTOFF,
            )
            _insert_relationship_row(
                conn,
                relationship_id=relationship_id,
                rel_type_id=rel_type_id,
                source_entity_id=adviser_id,
                target_entity_id=fund_id,
                properties={"private_fund_id": "805-0000000003", "source_filing_id": "4"},
                valid_from_date=date(2026, 1, 1),
                valid_to_date=None,
                created_at=_AFTER_CUTOFF,
            )

        result = check_manages_fund_duplicates(engine)
        # Scoped to this test's own relationship_id, not global cleanliness:
        # test_post_cutoff_duplicate_is_flagged deliberately leaves one real
        # post-cutoff duplicate behind in this module-scoped database.
        assert not any(
            group.relationship_id == relationship_id for group in result.new_duplicate_groups
        ), result.new_duplicate_groups
    finally:
        engine.dispose()


def test_quarantined_or_superseded_rows_are_excluded(
    postgres_manages_fund: PostgresManagesFund,
) -> None:
    """A quarantined duplicate is a different, already-handled failure mode
    (mdm-relationship-versioning-gap's own domain) -- this check must not
    double-count it."""
    engine = create_engine(postgres_manages_fund.database_url)
    try:
        with engine.begin() as conn:
            rel_type_id = _manages_fund_rel_type_id(conn)
            adviser_id = _insert_entity(conn, "adviser")
            fund_id = _insert_entity(conn, "fund")
            relationship_id = str(uuid.uuid4())
            properties = {"private_fund_id": "805-0000000005", "source_filing_id": "5"}
            _insert_relationship_row(
                conn,
                relationship_id=relationship_id,
                rel_type_id=rel_type_id,
                source_entity_id=adviser_id,
                target_entity_id=fund_id,
                properties=properties,
                valid_from_date=date(2026, 9, 1),
                valid_to_date=None,
                created_at=_AFTER_CUTOFF,
            )
            _insert_relationship_row(
                conn,
                relationship_id=relationship_id,
                rel_type_id=rel_type_id,
                source_entity_id=adviser_id,
                target_entity_id=fund_id,
                properties=properties,
                valid_from_date=date(2026, 9, 1),
                valid_to_date=None,
                created_at=_AFTER_CUTOFF,
                quarantined=True,
            )

        result = check_manages_fund_duplicates(engine)
        assert not any(
            group.relationship_id == relationship_id for group in result.new_duplicate_groups
        ), result.new_duplicate_groups
    finally:
        engine.dispose()
