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
