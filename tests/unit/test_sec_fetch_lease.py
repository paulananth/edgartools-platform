"""Cross-command SEC-fetch lease (release-readiness ticket 80, Phase 1).

Mirrors tests/unit/test_identity_refresh_window.py's existing
pipeline_run_lease coverage for the identity-refresh lease, adapted for the
new sec_fetch_active lease: no mode/backstop concept -- a caller either gets
the lease or is deferred.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation

_LEASE_NAME = warehouse_orchestrator.SEC_FETCH_LEASE_NAME


def _context(tmp_path: Path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="tester@example.com",
        runtime_mode="bronze_capture",
    )


def test_sec_fetch_lease_acquire_is_exclusive(tmp_path) -> None:
    """Test plan item 1: a second command genuinely can't acquire while the
    first holds it -- no race where both proceed."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    try:
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="bootstrap-run", mode="fetch", acquired_at=now
        )
        # A concurrently-started daily-incremental must not steal the lease.
        assert not db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="daily-incremental-run", mode="fetch", acquired_at=now
        )
        held = db.get_pipeline_run_lease(_LEASE_NAME)
        assert held is not None
        assert held["run_id"] == "bootstrap-run"
        assert held["status"] == "held"

        # Releasing under the wrong run_id is a no-op -- daily-incremental
        # can't free a lease it never held.
        db.release_pipeline_run_lease(lease_name=_LEASE_NAME, run_id="daily-incremental-run", released_at=now)
        assert db.get_pipeline_run_lease(_LEASE_NAME)["status"] == "held"

        # The actual holder releasing frees it for the next acquirer.
        db.release_pipeline_run_lease(lease_name=_LEASE_NAME, run_id="bootstrap-run", released_at=now)
        assert db.get_pipeline_run_lease(_LEASE_NAME)["status"] == "idle"
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="daily-incremental-run", mode="fetch", acquired_at=now
        )
    finally:
        db.close()


def test_sec_fetch_lease_reclaims_a_stale_hold(tmp_path) -> None:
    """Test plan item 2: a lease held past the 20h default staleness window
    is reclaimable by a later acquire attempt."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        held_at = datetime(2026, 8, 4, 0, 0, tzinfo=UTC)
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="bootstrap-full-run", mode="fetch", acquired_at=held_at
        )

        # Still within the 20h default -- not reclaimable yet.
        still_fresh = held_at + timedelta(hours=10)
        assert not db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="targeted-resync-run", mode="fetch", acquired_at=still_fresh
        )

        # Past the 20h window -- reclaimable even though the first holder
        # never called release.
        past_stale = held_at + timedelta(hours=21)
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="targeted-resync-run", mode="fetch", acquired_at=past_stale
        )
        held = db.get_pipeline_run_lease(_LEASE_NAME)
        assert held["run_id"] == "targeted-resync-run"
    finally:
        db.close()


def test_sec_fetch_lease_crashed_holder_does_not_wedge_it_permanently(tmp_path) -> None:
    """Test plan item 3: a command that fails mid-run (never calls release)
    leaves the lease correctly held -- not silently orphaned open to a race
    -- and the staleness reclaim above is the actual, sole recovery path.
    Release-on-failure is otherwise best-effort by design (matching the
    identity-refresh lease's own documented behavior)."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        crashed_at = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="crashed-bootstrap-run", mode="fetch", acquired_at=crashed_at
        )
        # Simulate the crash: no release_pipeline_run_lease call at all.

        # A fresh command a minute later must still be correctly deferred --
        # a crash must never look like a clean release.
        soon_after = crashed_at + timedelta(minutes=1)
        assert not db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="new-run", mode="fetch", acquired_at=soon_after
        )
        held = db.get_pipeline_run_lease(_LEASE_NAME)
        assert held["run_id"] == "crashed-bootstrap-run"
        assert held["status"] == "held"
    finally:
        db.close()


def test_acquire_sec_fetch_lease_command_records_deferred_on_conflict(tmp_path) -> None:
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="already-running", mode="fetch", acquired_at=now
        )

        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-sec-fetch-lease",
            arguments={"run_id": "new-run"},
            scope={},
            now=now,
            sync_run_id="new-run",
        )
        assert metrics["lease_acquired"] is False

        lease_result_rel = default_path_resolver().sec_fetch_lease_path("new-run")
        written_path = Path(context.bronze_root.join(lease_result_rel))
        assert written_path.exists()
        payload = json.loads(written_path.read_text())
        assert payload == {"lease_acquired": False, "held_by_run_id": "already-running"}
    finally:
        db.close()


def test_acquire_sec_fetch_lease_command_writes_success_to_s3(tmp_path) -> None:
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-sec-fetch-lease",
            arguments={"run_id": "bootstrap-run"},
            scope={},
            now=now,
            sync_run_id="bootstrap-run",
        )
        assert metrics["lease_acquired"] is True

        lease_result_rel = default_path_resolver().sec_fetch_lease_path("bootstrap-run")
        written_path = Path(context.bronze_root.join(lease_result_rel))
        payload = json.loads(written_path.read_text())
        assert payload == {"lease_acquired": True, "held_by_run_id": "bootstrap-run"}
    finally:
        db.close()


def test_release_sec_fetch_lease_command_frees_it(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="bootstrap-run", mode="fetch", acquired_at=now
        )

        warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="release-sec-fetch-lease",
            arguments={"run_id": "bootstrap-run"},
            scope={},
            now=now,
            sync_run_id="bootstrap-run",
        )

        held = db.get_pipeline_run_lease(_LEASE_NAME)
        assert held["status"] == "idle"
    finally:
        db.close()


def test_acquire_sec_fetch_lease_command_uses_16h_staleness_not_the_20h_default(tmp_path) -> None:
    """Release-readiness ticket 84: the sec_fetch_active lease is sized
    against real measured prod runtimes (daily-incremental ~7h7m) with a
    16h ceiling, deliberately shorter than IDENTITY_REFRESH_LEASE_NAME's
    20h default. The orchestrator command must pass stale_after_seconds
    explicitly, not fall through to acquire_pipeline_run_lease's default."""
    from edgar_warehouse.silver_store import SilverDatabase

    context = _context(tmp_path)
    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        held_at = datetime(2026, 8, 4, 0, 0, tzinfo=UTC)
        db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="stuck-bootstrap-run", mode="fetch", acquired_at=held_at
        )

        # Still within 16h -- must stay deferred (would already be
        # reclaimable here under the 20h default, so this proves 16h is
        # actually the value in effect, not just documentation).
        still_within_16h = held_at + timedelta(hours=15, minutes=59)
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-sec-fetch-lease",
            arguments={"run_id": "waiting-run"},
            scope={},
            now=still_within_16h,
            sync_run_id="waiting-run",
        )
        assert metrics["lease_acquired"] is False

        # Just past 16h -- reclaimable.
        past_16h = held_at + timedelta(hours=16, minutes=1)
        _, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=context,
            db=db,
            command_name="acquire-sec-fetch-lease",
            arguments={"run_id": "waiting-run"},
            scope={},
            now=past_16h,
            sync_run_id="waiting-run",
        )
        assert metrics["lease_acquired"] is True
    finally:
        db.close()


def test_lease_command_context_repoints_storage_and_silver_root_to_leases_subpath(tmp_path) -> None:
    """Root-cause fix for task #35's OOM: lease commands must never hydrate
    or publish the full canonical silver.duckdb (1.5GB+ and growing) just to
    touch the tiny pipeline_run_lease table. _lease_command_context() must
    repoint storage_root/silver_root at an isolated "leases" subpath, and
    must leave every other field (bronze_root, snowflake_export_root, etc)
    untouched."""
    context = _context(tmp_path)

    leased = warehouse_orchestrator._lease_command_context(context)

    assert leased.storage_root.root == f"{context.storage_root.root}/leases"
    assert leased.silver_root.root == f"{context.silver_root.root}/leases"
    assert leased.bronze_root is context.bronze_root
    assert leased.snowflake_export_root is context.snowflake_export_root
    assert leased.environment_name == context.environment_name
    assert leased.identity == context.identity
    assert leased.runtime_mode == context.runtime_mode


def test_acquire_sec_fetch_lease_end_to_end_never_touches_main_silver_database(tmp_path) -> None:
    """Full run_command()-level path (not just the _capture_bronze_raw SQL
    block covered above): acquiring the lease must not create or touch
    <silver_root>/silver/sec/silver.duckdb at all -- only the isolated
    <silver_root>/leases/silver/sec/silver.duckdb."""
    from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver

    context = _context(tmp_path)
    main_db_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))
    lease_db_path = Path(f"{context.silver_root.root}/leases").joinpath("silver", "sec", "silver.duckdb")

    assert "acquire-sec-fetch-lease" in warehouse_orchestrator.LEASE_ONLY_COMMANDS
    payload = warehouse_orchestrator._execute_warehouse_bronze_capture(
        context=context,
        command_name="acquire-sec-fetch-lease",
        arguments={"run_id": "e2e-run"},
    )

    assert payload["status"] == "ok"
    assert not main_db_path.exists()
    assert lease_db_path.exists()

    lease_result_rel = default_path_resolver().sec_fetch_lease_path("e2e-run")
    result = json.loads(Path(context.bronze_root.join(lease_result_rel)).read_text())
    assert result == {"lease_acquired": True, "held_by_run_id": "e2e-run"}


def test_release_sec_fetch_lease_end_to_end_uses_leases_subpath_too(tmp_path) -> None:
    context = _context(tmp_path)
    main_db_path = Path(context.silver_root.join("silver", "sec", "silver.duckdb"))

    warehouse_orchestrator._execute_warehouse_bronze_capture(
        context=context,
        command_name="acquire-sec-fetch-lease",
        arguments={"run_id": "e2e-run"},
    )
    payload = warehouse_orchestrator._execute_warehouse_bronze_capture(
        context=context,
        command_name="release-sec-fetch-lease",
        arguments={"run_id": "e2e-run"},
    )

    assert not main_db_path.exists()
    assert payload["status"] == "ok"

    # The lease must actually be free afterward -- re-open the isolated
    # lease store (not the main silver.duckdb) and check directly.
    from edgar_warehouse.silver_store import SilverDatabase

    lease_db_path = Path(f"{context.silver_root.root}/leases").joinpath("silver", "sec", "silver.duckdb")
    db = SilverDatabase(str(lease_db_path))
    try:
        held = db.get_pipeline_run_lease(_LEASE_NAME)
        assert held["status"] == "idle"
    finally:
        db.close()


def test_non_lease_command_does_not_get_repointed(tmp_path, monkeypatch) -> None:
    """Sanity check: only the four lease commands get repointed -- a normal
    data-writing command must still hydrate/publish the real silver.duckdb,
    not silently get redirected to the leases subpath too."""
    context = _context(tmp_path)
    calls: list[str] = []
    original = warehouse_orchestrator._lease_command_context

    def spy(ctx):
        calls.append("called")
        return original(ctx)

    monkeypatch.setattr(warehouse_orchestrator, "_lease_command_context", spy)

    assert "bootstrap-next" not in warehouse_orchestrator.LEASE_ONLY_COMMANDS
    try:
        warehouse_orchestrator._execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-next",
            arguments={"run_id": "e2e-run", "cik_list": []},
        )
    except Exception:
        # bootstrap-next may fail for reasons unrelated to this test (e.g. no
        # CIKs resolved) -- only the repoint-guard behavior is under test.
        pass

    assert calls == []


def test_sec_fetch_lease_is_independent_of_identity_refresh_lease(tmp_path) -> None:
    """The two leases must never collide -- holding one must not block the
    other, and they must be distinct rows/names entirely."""
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    now = datetime(2026, 8, 4, 12, tzinfo=UTC)
    try:
        assert db.acquire_pipeline_run_lease(
            lease_name=warehouse_orchestrator.IDENTITY_REFRESH_LEASE_NAME,
            run_id="daily-identity-refresh-run",
            mode="daily",
            acquired_at=now,
        )
        assert db.acquire_pipeline_run_lease(
            lease_name=_LEASE_NAME, run_id="bootstrap-run", mode="fetch", acquired_at=now
        )
        assert db.get_pipeline_run_lease(warehouse_orchestrator.IDENTITY_REFRESH_LEASE_NAME)["run_id"] == (
            "daily-identity-refresh-run"
        )
        assert db.get_pipeline_run_lease(_LEASE_NAME)["run_id"] == "bootstrap-run"
    finally:
        db.close()
