"""Real-Postgres integration coverage for Ticket 40's graph-generation
serialization guard (Incremental Change Propagation map).

SQLite-backed unit tests (``tests/mdm/test_graph_generation_builder.py``)
prove ``create_generation()``'s own conflict-handling logic, but SQLite's
single-writer lock trivially serializes every write without ever exercising
a real partial-unique-index violation under genuinely concurrent
transactions -- exactly the thing Ticket 40's acceptance criteria require
proof of. This file proves (a) the "at most one non-terminal generation"
rule is a real database-level constraint, not just application-level
discipline, and (b) two genuinely concurrent ``create_generation()`` calls
against the same live Postgres converge to exactly one non-terminal row.
"""
from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm import generation
from edgar_warehouse.mdm.database import MdmGraphGeneration

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATIONS_DIR = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"
GENERATION_MIGRATIONS = (
    MIGRATIONS_DIR / "009_graph_generation_builder.sql",
    MIGRATIONS_DIR / "016_serialize_graph_generation.sql",
)


@dataclass(frozen=True)
class PostgresGenerationDb:
    container: str
    database_url: str


def _run(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, input=input_text, text=True, capture_output=True, check=False
    )


def _psql(container: str, sql: str) -> subprocess.CompletedProcess[str]:
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
        "postgres",
        "-d",
        "postgres",
        input_text=sql,
    )


@pytest.fixture(scope="module")
def postgres_generation_db() -> Iterator[PostgresGenerationDb]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket40-{uuid.uuid4().hex[:10]}"
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

        for migration_file in GENERATION_MIGRATIONS:
            copied = _run(
                "docker", "cp", str(migration_file), f"{container}:/tmp/{migration_file.name}"
            )
            assert copied.returncode == 0, copied.stderr
            applied = _run(
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
                f"/tmp/{migration_file.name}",
            )
            assert applied.returncode == 0, applied.stderr

        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresGenerationDb(
            container=container,
            database_url=f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres",
        )
    finally:
        _run("docker", "stop", container)


@pytest.fixture(autouse=True)
def _clean_generations(postgres_generation_db: PostgresGenerationDb) -> Iterator[None]:
    yield
    _psql(postgres_generation_db.container, "DELETE FROM mdm_graph_generation;")


def test_index_rejects_a_second_non_terminal_row_via_direct_sql(
    postgres_generation_db: PostgresGenerationDb,
) -> None:
    """The "at most one non-terminal generation" rule is a real database-level
    constraint, not just application-level discipline -- proven by inserting
    two 'building' rows directly, bypassing create_generation() entirely."""
    first = _psql(
        postgres_generation_db.container,
        "INSERT INTO mdm_graph_generation (status, rule_version, schema_version) "
        "VALUES ('building', 'v1', 'v1');",
    )
    assert first.returncode == 0, first.stderr

    second = _psql(
        postgres_generation_db.container,
        "INSERT INTO mdm_graph_generation (status, rule_version, schema_version) "
        "VALUES ('building', 'v1', 'v1');",
    )
    assert second.returncode != 0
    assert "uq_graph_generation_single_non_terminal" in second.stderr


def test_index_rejects_verified_alongside_building_too(
    postgres_generation_db: PostgresGenerationDb,
) -> None:
    """'verified' is non-terminal too -- the guard must reject a second
    non-terminal row regardless of which of the two non-terminal statuses
    each row is in."""
    first = _psql(
        postgres_generation_db.container,
        "INSERT INTO mdm_graph_generation (status, rule_version, schema_version) "
        "VALUES ('verified', 'v1', 'v1');",
    )
    assert first.returncode == 0, first.stderr

    second = _psql(
        postgres_generation_db.container,
        "INSERT INTO mdm_graph_generation (status, rule_version, schema_version) "
        "VALUES ('building', 'v1', 'v1');",
    )
    assert second.returncode != 0
    assert "uq_graph_generation_single_non_terminal" in second.stderr


def test_two_genuinely_concurrent_creates_converge_to_exactly_one_non_terminal_generation(
    postgres_generation_db: PostgresGenerationDb,
) -> None:
    """Real threads, real separate connections/sessions -- not sequential
    calls -- racing create_generation() against the same live Postgres.
    Exactly one must win; the other must fail with
    ConcurrentGenerationBuildRejected (fails outright, no internal
    queue/retry), and the loser's failure must not corrupt the winner's
    row."""
    database_url = postgres_generation_db.database_url

    def _attempt(label: str) -> tuple[str, str]:
        engine = create_engine(database_url)
        try:
            with Session(engine) as session:
                try:
                    gen = generation.create_generation(
                        session, rule_version=label, schema_version=label
                    )
                    session.commit()
                    return ("ok", gen.generation_id)
                except generation.ConcurrentGenerationBuildRejected as exc:
                    return ("rejected", str(exc))
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_attempt, f"racer-{i}") for i in range(2)]
        results = [future.result() for future in futures]

    outcomes = sorted(result[0] for result in results)
    assert outcomes == ["ok", "rejected"]

    verify_engine = create_engine(database_url)
    try:
        with Session(verify_engine) as session:
            rows = session.scalars(
                select(MdmGraphGeneration).where(
                    MdmGraphGeneration.status.in_(["building", "verified"])
                )
            ).all()
            assert len(rows) == 1
    finally:
        verify_engine.dispose()
