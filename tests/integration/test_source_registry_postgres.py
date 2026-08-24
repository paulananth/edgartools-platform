"""Real-Postgres integration coverage for Ticket 20's Source Family Registry.

Same rationale as ``test_acquisition_ledger_postgres.py``'s docstrings for
Tickets 14/18/19: SQLite-backed unit tests (``tests/acquisition/
test_registry_ledger.py``) prove the ledger's own logic, but Ticket 20's
acceptance rests on a real dedicated database role
(``edgartools_acquisition_registry_owner``) actually fencing these two
tables the way ``migrations/014_source_registry.sql`` claims, and on the
self-managing first-install/rerun-gated migration function
(``_apply_source_registry_migration``) actually behaving the way its own
docstring says against a real Postgres role graph -- neither is exercisable
against SQLite.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from edgar_warehouse.acquisition.registry_ledger import (
    CoverageSpec,
    NoActiveRegistryVersion,
    SourceRegistryLedger,
    active_in_scope_forms,
    build_active_source_family_registry,
)
from edgar_warehouse.acquisition.source_family_registry import FilingArtifactPolicy
from edgar_warehouse.mdm.migrations import runtime as migrations

POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATION = (
    Path(__file__).parents[2]
    / "edgar_warehouse"
    / "mdm"
    / "migrations"
    / "014_source_registry.sql"
)


@dataclass(frozen=True)
class PostgresRegistry:
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
def postgres_registry() -> Iterator[PostgresRegistry]:
    if shutil.which("docker") is None:
        pytest.skip("Docker is unavailable")
    image = _run("docker", "image", "inspect", POSTGRES_IMAGE)
    if image.returncode != 0:
        pytest.skip(f"{POSTGRES_IMAGE} is not available locally")

    container = f"edgartools-ticket20-{uuid.uuid4().hex[:10]}"
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
        copied = _run("docker", "cp", str(MIGRATION), f"{container}:/tmp/registry.sql")
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
            "/tmp/registry.sql",
        )
        assert migrated.returncode == 0, migrated.stderr
        port_result = _run("docker", "port", container, "5432/tcp")
        assert port_result.returncode == 0, port_result.stderr
        port = port_result.stdout.strip().rsplit(":", 1)[-1]
        yield PostgresRegistry(
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


def test_registry_owner_role_fences_the_two_tables_from_application(
    postgres_registry: PostgresRegistry,
) -> None:
    """The migration's own claim -- application can only touch
    source_registry_version/source_registry_coverage via SET ROLE
    edgartools_acquisition_registry_owner, never directly -- proven at the
    real grant level, the same shape as the 013 "universal_login"/
    "forged_role" proofs.
    """

    direct_insert_denied = _psql(
        postgres_registry.container,
        """
        INSERT INTO source_registry_version (
            status, operator_authorization_reference
        ) VALUES ('draft', 'operator-direct-insert-attempt');
        """,
        user="application",
    )
    assert direct_insert_denied.returncode != 0
    assert (
        "permission denied for table source_registry_version"
        in direct_insert_denied.stderr
    )

    with_role = _psql(
        postgres_registry.container,
        """
        SET ROLE edgartools_acquisition_registry_owner;
        INSERT INTO source_registry_version (
            status, operator_authorization_reference
        ) VALUES ('draft', 'operator-set-role-insert');
        SELECT status FROM source_registry_version
        WHERE operator_authorization_reference = 'operator-set-role-insert';
        """,
        user="application",
    )
    assert with_role.returncode == 0, with_role.stderr
    assert "draft" in with_role.stdout


def test_open_draft_blocks_activation_then_activates_after_catchup_against_real_postgres(
    postgres_registry: PostgresRegistry,
) -> None:
    """Ticket 20 bullet 4, end-to-end against real Postgres via the actual
    Python API: activating a draft with an unmet catch-up obligation must
    block (leaving no active version -- ``get_active_registry`` stays
    ``None``/raises), and only activates once the obligation is proven met.
    """

    engine = create_engine(postgres_registry.database_url)
    try:
        ledger = SourceRegistryLedger(engine)

        with pytest.raises(NoActiveRegistryVersion):
            build_active_source_family_registry(engine, identity="test@example.com")
        assert active_in_scope_forms(engine, "filing_artifact") == frozenset()

        draft = ledger.open_draft(
            [
                CoverageSpec(
                    source_family="filing_artifact",
                    coverage_action="add",
                    in_scope_forms=("3", "3/A", "4", "4/A", "5", "5/A"),
                    acquisition_mode="on_demand_fetch",
                    completeness_policy="non_empty_payload",
                    discovery_policy="daily_index_driven",
                    required_producers=("sec_raw_object",),
                    coverage_start_date=date(2026, 1, 1),
                    catchup_required_through_date=date(2026, 1, 3),
                )
            ],
            operator_authorization_reference="pg-open-draft-1",
        )
        assert draft.status == "draft"

        blocked = ledger.activate(draft.version_id)
        assert blocked.status == "activation_blocked"
        assert blocked.blocker is not None
        assert "filing_artifact" in blocked.blocker
        assert ledger.get_active_registry() is None

        # Partial catch-up progress (through the 2nd, not yet the required
        # 3rd) must still block.
        ledger.record_catchup_progress("filing_artifact", date(2026, 1, 2))
        still_blocked = ledger.activate(draft.version_id)
        assert still_blocked.status == "activation_blocked"
        assert ledger.get_active_registry() is None

        ledger.record_catchup_progress("filing_artifact", date(2026, 1, 3))
        activated = ledger.activate(draft.version_id)
        assert activated.status == "active"

        active = ledger.get_active_registry()
        assert active is not None
        assert active.version_id == draft.version_id
        assert active.coverage[0].source_family == "filing_artifact"

        registry = build_active_source_family_registry(engine, identity="test@example.com")
        assert set(registry) == {"filing_artifact"}
        assert isinstance(registry["filing_artifact"], FilingArtifactPolicy)
        assert active_in_scope_forms(engine, "filing_artifact") == frozenset(
            {"3", "3/A", "4", "4/A", "5", "5/A"}
        )
    finally:
        engine.dispose()


def test_activate_supersedes_previous_version_and_single_active_index_is_real(
    postgres_registry: PostgresRegistry,
) -> None:
    """Second half of Ticket 20 bullet 4: activating a new version supersedes
    the prior one atomically, and the "at most one active version" rule is
    a real database-level constraint (the partial unique index), not just
    application-level discipline -- proven by trying to bypass the ledger
    and mark two rows active directly under the owning role.
    """

    engine = create_engine(postgres_registry.database_url)
    try:
        ledger = SourceRegistryLedger(engine)
        first = ledger.open_draft(
            [
                CoverageSpec(
                    source_family="filing_artifact",
                    coverage_action="add",
                    in_scope_forms=("3", "4", "5"),
                    acquisition_mode="on_demand_fetch",
                    completeness_policy="non_empty_payload",
                    discovery_policy="daily_index_driven",
                    required_producers=("sec_raw_object",),
                    coverage_start_date=date(2026, 1, 1),
                    catchup_required_through_date=date(2026, 1, 1),
                )
            ],
            operator_authorization_reference="pg-supersede-1",
        )
        ledger.record_catchup_progress("filing_artifact", date(2026, 1, 1))
        first_active = ledger.activate(first.version_id)
        assert first_active.status == "active"

        # A carry-forward-only draft needs no new catch-up proof.
        second = ledger.open_draft(
            [],
            operator_authorization_reference="pg-supersede-2",
        )
        assert second.coverage[0].coverage_action == "carry_forward"
        second_active = ledger.activate(second.version_id)
        assert second_active.status == "active"

        active = ledger.get_active_registry()
        assert active is not None
        assert active.version_id == second.version_id
    finally:
        engine.dispose()

    two_actives_rejected = _psql(
        postgres_registry.container,
        """
        SET ROLE edgartools_acquisition_registry_owner;
        UPDATE source_registry_version SET status = 'active', activated_at = NOW()
        WHERE operator_authorization_reference = 'pg-supersede-1';
        """,
        user="application",
    )
    assert two_actives_rejected.returncode != 0
    assert "uq_source_registry_version_single_active" in two_actives_rejected.stderr


def test_apply_source_registry_migration_rerun_against_real_postgres(
    postgres_registry: PostgresRegistry,
) -> None:
    """Exercise ``_apply_source_registry_migration``'s self-managing
    first-install/rerun path against the real role graph the ``application``
    engine actually connects as, mirroring the 013 proof
    (``test_repository_uses_application_role_and_postgres_uuid_columns``'s
    trailing assertions) rather than trusting the docstring's claim.
    """

    application_engine = create_engine(postgres_registry.database_url)
    admin_engine = create_engine(postgres_registry.admin_database_url)
    try:
        # The table already exists (module fixture applied 014 as `postgres`).
        # `application` is itself a member of edgartools_acquisition_registry_owner
        # here -- unlike 013's split owner/operational-role shape -- so a
        # rerun through the application engine is expected to be able to
        # manage (re-apply) the migration, not silently skip it.
        result = migrations._apply_source_registry_migration(application_engine)
        assert result is True

        admin_result = migrations._apply_source_registry_migration(admin_engine)
        assert admin_result is True
    finally:
        application_engine.dispose()
        admin_engine.dispose()
