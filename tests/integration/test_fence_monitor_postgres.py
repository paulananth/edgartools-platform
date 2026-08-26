"""Real-Postgres integration coverage for Ticket 44 (change-propagation map),
the drift monitor split from Ticket 30's live incident.

Same rationale as ``test_acquisition_ledger_postgres.py``/
``test_source_registry_postgres.py``'s docstrings: this monitor's whole job
is reading real Postgres role/ACL state -- ``has_table_privilege``,
``aclexplode``, ``pg_auth_members`` -- none of which SQLite can model, and
none of which a mocked/stubbed connection would prove anything about.

Every test below connects through ``postgres_fence.database_url`` --
``application``, a real non-superuser LOGIN role -- never the admin DSN, to
prove Ticket 44's own open question (its "Blocked by" checklist item 3):
does the ordinary runtime credential already have enough privilege to run
this check, or would a new, more-privileged credential be needed. It does;
every test here is the proof.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.mdm.fence_monitor import (
    FenceLeak,
    OperationalAccessGap,
    check_ledger_fence,
)

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATIONS_DIR = Path(__file__).parents[2] / "edgar_warehouse" / "mdm" / "migrations"
LEDGER_MIGRATION = MIGRATIONS_DIR / "013_acquisition_ledger.sql"
REGISTRY_MIGRATION = MIGRATIONS_DIR / "014_source_registry.sql"
EVIDENCE_CONFLICT_MIGRATION = MIGRATIONS_DIR / "015_source_evidence_conflict.sql"


@dataclass(frozen=True)
class PostgresFence:
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
def postgres_fence() -> Iterator[PostgresFence]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket44-{uuid.uuid4().hex[:10]}"
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

        application = _psql(container, "CREATE ROLE application LOGIN PASSWORD 'test';")
        assert application.returncode == 0, application.stderr
        _psql_file(container, LEDGER_MIGRATION, "013.sql")
        _psql_file(container, REGISTRY_MIGRATION, "014.sql")
        _psql_file(container, EVIDENCE_CONFLICT_MIGRATION, "015.sql")

        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresFence(
            container=container,
            database_url=f"postgresql+psycopg2://application:test@127.0.0.1:{port}/postgres",
            admin_database_url=f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres",
        )
    finally:
        _run("docker", "stop", container)


def test_fresh_migration_reports_clean(postgres_fence: PostgresFence) -> None:
    """Baseline: right after 013+014 apply, both the deny side (application/
    snowflake_write have no direct grant) and the allow side (every fenced
    table still has an operational grantee) should be clean, connected as
    the ordinary application DSN -- proving the check needs no elevated
    credential for the healthy-path case."""
    engine = create_engine(postgres_fence.database_url)
    try:
        result = check_ledger_fence(engine)
    finally:
        engine.dispose()

    assert result.is_clean, (result.leaks, result.access_gaps)
    # 7 (013's own tables) + 2 (015's source_evidence_conflict counts as one,
    # but 013 also owns source_change_status/source_change_status_detail --
    # see this fixture's migration set) + 2 (014's registry tables).
    assert len(result.fenced_tables) >= 10, result.fenced_tables
    assert "edgartools_acquisition_owner" in result.owner_roles
    assert "edgartools_acquisition_registry_owner" in result.owner_roles
    assert "source_evidence_conflict" in result.fenced_tables


def test_snowflake_write_leak_is_detected_then_clears_after_revoke(
    postgres_fence: PostgresFence,
) -> None:
    """Reproduces Ticket 30's own live incident shape: a platform-managed
    role regains direct DML on an already-fenced table. snowflake_write
    does not exist on a plain Postgres instance, so this test creates it
    itself -- mirroring test_acquisition_ledger_postgres.py's own proof for
    the sibling incident."""
    admin_engine = create_engine(postgres_fence.admin_database_url)
    app_engine = create_engine(postgres_fence.database_url)
    try:
        with admin_engine.begin() as conn:
            conn.execute(text("CREATE ROLE snowflake_write NOLOGIN"))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON source_fetch_decision "
                    "TO snowflake_write"
                )
            )

        result = check_ledger_fence(app_engine)
        leaked = {
            (leak.role, leak.table, leak.privilege)
            for leak in result.leaks
            if leak.table == "source_fetch_decision"
        }
        assert leaked == {
            ("snowflake_write", "source_fetch_decision", "SELECT"),
            ("snowflake_write", "source_fetch_decision", "INSERT"),
            ("snowflake_write", "source_fetch_decision", "UPDATE"),
            ("snowflake_write", "source_fetch_decision", "DELETE"),
        }, result.leaks
        assert not result.access_gaps, result.access_gaps

        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(
                text("REVOKE ALL PRIVILEGES ON source_fetch_decision FROM snowflake_write")
            )

        clean_result = check_ledger_fence(app_engine)
        assert clean_result.is_clean, (clean_result.leaks, clean_result.access_gaps)
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(
                text("REVOKE ALL PRIVILEGES ON source_fetch_decision FROM snowflake_write")
            )
            conn.execute(text("RESET ROLE"))
            conn.execute(text("DROP ROLE IF EXISTS snowflake_write"))
        admin_engine.dispose()
        app_engine.dispose()


def test_new_owner_role_table_is_discovered_without_code_changes(
    postgres_fence: PostgresFence,
) -> None:
    """Proves the fenced-table set is discovered live, not hardcoded: a
    brand-new table owned by edgartools_acquisition_owner (simulating a
    future migration adding one, per Ticket 30's own 'not fix once' note)
    is picked up and its leak detected, with zero changes to this module."""
    admin_engine = create_engine(postgres_fence.admin_database_url)
    app_engine = create_engine(postgres_fence.database_url)
    try:
        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(text("CREATE TABLE source_future_thing (id INT PRIMARY KEY)"))
            conn.execute(text("RESET ROLE"))
            conn.execute(text("CREATE ROLE snowflake_write NOLOGIN"))
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(
                text("GRANT SELECT ON source_future_thing TO snowflake_write")
            )
            conn.execute(text("RESET ROLE"))

        result = check_ledger_fence(app_engine)
        assert "source_future_thing" in result.fenced_tables
        assert any(
            leak.table == "source_future_thing" and leak.role == "snowflake_write"
            for leak in result.leaks
        ), result.leaks
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(text("DROP TABLE IF EXISTS source_future_thing"))
            conn.execute(text("RESET ROLE"))
            conn.execute(text("DROP ROLE IF EXISTS snowflake_write"))
        admin_engine.dispose()
        app_engine.dispose()


def test_operational_access_gap_is_detected_then_clears_after_regrant(
    postgres_fence: PostgresFence,
) -> None:
    """Reproduces the manifest-pipeline-ownership incident's shape on this
    table set: a future re-provisioning strips a table's owner's own grant
    as a side effect of an unrelated change, leaving the deny side clean
    but the pipeline broken. A monitor that only checks for leaks would
    report this as healthy. Empirically confirmed (this module's own
    development) that Postgres does not silently exempt an owner from ACL
    checks -- a REVOKE against the owner's own explicit grant really does
    strip its access, which is exactly what this test reproduces and what
    the check is designed to catch."""
    admin_engine = create_engine(postgres_fence.admin_database_url)
    app_engine = create_engine(postgres_fence.database_url)
    try:
        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(
                text(
                    "REVOKE ALL PRIVILEGES ON source_fetch_decision "
                    "FROM edgartools_acquisition_owner"
                )
            )
            conn.execute(text("RESET ROLE"))

        result = check_ledger_fence(app_engine)
        assert (
            OperationalAccessGap(table="source_fetch_decision", role="edgartools_acquisition_owner")
            in result.access_gaps
        )
        assert not any(leak.table == "source_fetch_decision" for leak in result.leaks)
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text("SET ROLE edgartools_acquisition_owner"))
            conn.execute(
                text(
                    "GRANT SELECT, INSERT, UPDATE ON source_fetch_decision "
                    "TO edgartools_acquisition_owner"
                )
            )
            conn.execute(text("RESET ROLE"))
        admin_engine.dispose()
        app_engine.dispose()

    restored = check_ledger_fence(create_engine(postgres_fence.database_url))
    assert not any(
        gap.table == "source_fetch_decision" for gap in restored.access_gaps
    ), restored.access_gaps
