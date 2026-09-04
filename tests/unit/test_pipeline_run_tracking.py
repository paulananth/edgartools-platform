from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )


def test_silver_database_records_pipeline_run_lifecycle(tmp_path) -> None:
    from edgar_warehouse.silver_store import SilverDatabase

    db = SilverDatabase(str(tmp_path / "silver.duckdb"))
    try:
        db.start_pipeline_run(
            {
                "pipeline_run_id": "run-1",
                "command_name": "seed-universe",
                "runtime_mode": "bronze_capture",
                "environment_name": "test",
                "started_at": datetime(2026, 1, 1, tzinfo=UTC),
                "status": "running",
                "arguments": {"run_id": "run-1"},
                "scope": {"run_date": "2026-01-01"},
                "bronze_root": "s3://bronze",
                "storage_root": "s3://warehouse",
                "silver_root": "/tmp/silver",
            }
        )
        db.complete_pipeline_run(
            "run-1",
            status="succeeded",
            writes=[{"layer": "bronze", "path": "s3://bronze/runs/run-1/manifest.json"}],
            raw_writes=[{"path": "s3://bronze/raw.json", "sha256": "abc"}],
            metrics={"rows_inserted": 1},
        )

        row = db.get_pipeline_run("run-1")
    finally:
        db.close()

    assert row is not None
    assert row["pipeline_run_id"] == "run-1"
    assert row["status"] == "succeeded"
    assert json.loads(row["writes_json"])[0]["layer"] == "bronze"
    assert json.loads(row["raw_writes_json"])[0]["sha256"] == "abc"
    assert json.loads(row["metrics_json"]) == {"rows_inserted": 1}


def test_bronze_capture_records_pipeline_run(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_table_counts.return_value = {}
    raw_path = context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}')
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": raw_path,
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
            return_value=fake_bookkeeping,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(raw_writes, {"rows_inserted": 1, "rows_skipped": 0}),
        ),
    ):
        _execute_warehouse_bronze_capture(
            context=context,
            command_name="seed-universe",
            arguments={"run_id": "run-1"},
        )

    fake_bookkeeping.start_pipeline_run.assert_called_once()
    fake_bookkeeping.complete_pipeline_run.assert_called_once()
    complete_kwargs = fake_bookkeeping.complete_pipeline_run.call_args.kwargs
    assert complete_kwargs["status"] == "succeeded"
    assert complete_kwargs["raw_writes"] == raw_writes
    assert any(write["layer"] == "bronze" for write in complete_kwargs["writes"])
    # 2026-09-01 durability bug: BookkeepingStore's Session never
    # auto-commits (see BookkeepingStore.commit's docstring) -- without an
    # explicit commit call here, every write above is silently rolled back
    # when the process exits. Must fire after complete_pipeline_run.
    fake_bookkeeping.commit.assert_called_once()
    call_order = [c[0] for c in fake_bookkeeping.method_calls]
    assert call_order.index("complete_pipeline_run") < call_order.index("commit")


def test_bronze_capture_commits_bookkeeping_on_failure(tmp_path) -> None:
    """Same durability bug, failure path: a failed run's own failure record
    (complete_sync_run/complete_pipeline_run status='failed') must also be
    committed, or there is no durable trace the run ever failed."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_table_counts.return_value = {}

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
            return_value=fake_bookkeeping,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            side_effect=RuntimeError("boom"),
        ),
    ):
        try:
            _execute_warehouse_bronze_capture(
                context=context,
                command_name="seed-universe",
                arguments={"run_id": "run-1"},
            )
        except RuntimeError:
            pass

    fake_bookkeeping.complete_pipeline_run.assert_called_once()
    assert fake_bookkeeping.complete_pipeline_run.call_args.kwargs["status"] == "failed"
    fake_bookkeeping.commit.assert_called_once()


def test_bronze_capture_never_commits_success_before_silver_publish_succeeds(
    tmp_path,
) -> None:
    """bronze-capture-oom Ticket 02, fixed 2026-09-02: bookkeeping.commit()
    must not fire until silver publish (and landing export) has actually
    succeeded -- a checkpoint or "succeeded" status durably committed
    before that point lets a crash between commit and publish look, on the
    next run, exactly like a genuine no-op skip (the content was never
    durably captured, but the checkpoint says it was). When publish fails,
    the except block must roll back whatever this run staged and commit
    only a clean "failed" record -- not correct an already-committed
    "succeeded" record in place, since nothing should have been committed
    yet at that point."""
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_table_counts.return_value = {}
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}'),
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
            return_value=fake_bookkeeping,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(raw_writes, {"rows_inserted": 1, "rows_skipped": 0}),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            side_effect=RuntimeError("publish boom"),
        ),
    ):
        try:
            _execute_warehouse_bronze_capture(
                context=context,
                command_name="seed-universe",
                arguments={"run_id": "run-1"},
            )
        except RuntimeError:
            pass

    # complete_pipeline_run is still called twice -- once "succeeded"
    # (staged before the publish attempt), once "failed" (from the except
    # block) -- but only the LAST state is ever allowed to become durable.
    assert fake_bookkeeping.complete_pipeline_run.call_count == 2
    statuses = [c.kwargs["status"] for c in fake_bookkeeping.complete_pipeline_run.call_args_list]
    assert statuses == ["succeeded", "failed"]
    # The premature "succeeded" state must be discarded, not committed --
    # exactly one commit, for the "failed" correction only.
    fake_bookkeeping.rollback.assert_called_once()
    assert fake_bookkeeping.commit.call_count == 1
    call_order = [c[0] for c in fake_bookkeeping.method_calls]
    assert call_order.index("rollback") < call_order.index("commit")
    # rollback discards the earlier start_sync_run/start_pipeline_run
    # inserts too (same uncommitted transaction) -- the except path must
    # re-issue them before complete_sync_run/complete_pipeline_run's plain
    # UPDATE statements would otherwise match no row.
    assert fake_bookkeeping.start_sync_run.call_count == 2
    assert fake_bookkeeping.start_pipeline_run.call_count == 2


@pytest.mark.parametrize("failing_stage", ["silver_publish", "landing_export"])
def test_bronze_capture_rolls_back_a_checkpoint_write_on_publish_boundary_failure(
    tmp_path, failing_stage: str
) -> None:
    """Proven against a real BookkeepingStore/session (not a MagicMock) so a
    genuine session.rollback() is exercised: a checkpoint written mid-run
    must not survive a failure anywhere in the durability boundary this fix
    commits behind -- silver publish *and* landing export both succeeding --
    or the next run's skip-if-unchanged comparison would wrongly believe
    this run's content already reached canonical Silver. Parametrized over
    both halves of that boundary (a Standards-review finding: the original
    diff only covered a silver-publish failure, leaving the landing-export
    half -- the one that moved furthest from the old commit point -- an
    unproven claim)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )
    from edgar_warehouse.bookkeeping.database import Base
    from edgar_warehouse.bookkeeping.store import BookkeepingStore

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    real_bookkeeping = BookkeepingStore(session)

    context = WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        # Only needed for the landing_export case (gates whether that block
        # runs at all) -- harmless to always set, since a silver_publish
        # failure raises before this block is ever reached either way.
        silver_landing_export_root=StorageLocation(str(tmp_path / "landing")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
    )
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {}
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}'),
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    def fake_capture_bronze_raw(*, bookkeeping, **_kwargs):
        # Mirrors _apply_submission_snapshot_to_silver's real shape: a
        # checkpoint write issued mid-run, well before either failure point
        # below is reached.
        bookkeeping.upsert_source_checkpoint(
            {
                "source_name": "submissions_main",
                "source_key": "cik:1",
                "raw_object_id": f"should-not-survive-a-failed-{failing_stage}",
            }
        )
        return raw_writes, {"rows_inserted": 1, "rows_skipped": 0}

    if failing_stage == "silver_publish":
        publish_patch = patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            side_effect=RuntimeError("publish boom"),
        )
        landing_patch = patch(
            "edgar_warehouse.application.warehouse_orchestrator.write_landing_export"
        )
    else:
        publish_patch = patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_with_retry",
            return_value={"layer": "silver", "path": "s3://silver.duckdb", "size_bytes": 1},
        )
        landing_patch = patch(
            "edgar_warehouse.application.warehouse_orchestrator.write_landing_export",
            side_effect=RuntimeError("landing export boom"),
        )

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
            return_value=real_bookkeeping,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            side_effect=fake_capture_bronze_raw,
        ),
        publish_patch,
        landing_patch,
    ):
        try:
            _execute_warehouse_bronze_capture(
                context=context,
                command_name="seed-universe",
                arguments={"run_id": "run-1"},
            )
        except RuntimeError:
            pass

    session.close()
    with Session(engine) as later_session:
        later_store = BookkeepingStore(later_session)
        # The checkpoint must not have survived -- otherwise a retry's
        # skip-if-unchanged comparison would wrongly treat this content as
        # already captured.
        assert later_store.get_source_checkpoint("submissions_main", "cik:1") is None
        # A durable trace of the failure must still exist.
        pipeline_row = later_store.get_pipeline_run("run-1")
        assert pipeline_row is not None
        assert pipeline_row["status"] == "failed"


def test_bronze_capture_writes_consolidated_run_manifest(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    context = _context(tmp_path)
    fake_db = MagicMock()
    fake_db.get_table_counts.return_value = {"sec_company": 1}
    fake_bookkeeping = MagicMock()
    fake_bookkeeping.get_table_counts.return_value = {}
    raw_writes = [
        {
            "layer": "bronze_raw",
            "path": context.bronze_root.write_bytes("raw/test.json", b'{"ok": true}'),
            "relative_path": "raw/test.json",
            "sha256": "c0ffee",
        }
    ]

    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage"
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._open_silver_database",
            return_value=fake_db,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._bookkeeping_store",
            return_value=fake_bookkeeping,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=(raw_writes, {"rows_inserted": 1, "rows_skipped": 0}),
        ),
    ):
        result = _execute_warehouse_bronze_capture(
            context=context,
            command_name="seed-universe",
            arguments={"run_id": "run-1"},
        )

    manifest_path = tmp_path / "bronze" / "runs" / "seed-universe" / "run-1" / "run_manifest.json"
    payload = json.loads(manifest_path.read_text())
    assert payload["schema_version"] == 1
    assert payload["command"] == "seed-universe"
    assert payload["run_id"] == "run-1"
    assert payload["created_at"].endswith("Z")
    assert payload["row_counts"]["rows_inserted"] == 1
    assert payload["row_counts"]["silver_table_counts"] == {"sec_company": 1}

    manifests = {entry["layer"]: entry for entry in payload["manifests"]}
    assert {"bronze", "staging", "artifacts"} <= set(manifests)
    assert manifests["bronze"]["path"].endswith("runs/seed-universe/run-1/manifest.json")
    assert manifests["bronze"]["row_counts"] == {"rows_inserted": 1, "rows_skipped": 0}
    assert manifests["staging"]["written_at"].endswith("Z")
    assert any(write["layer"] == "run_manifest" for write in result["writes"])


def test_verify_pipeline_run_rechecks_raw_write_hashes(tmp_path) -> None:
    from edgar_warehouse.application.commands import verify_pipeline_run as vpr_module
    from edgar_warehouse.application.commands.verify_pipeline_run import verify_pipeline_run
    from tests.support.bookkeeping_fixtures import bookkeeping_fixture

    context = _context(tmp_path)
    raw_payload = b'{"ok": true}'
    raw_path = context.bronze_root.write_bytes("raw/test.json", raw_payload)

    # DuckDB Retirement Cutover Ticket 15: pipeline_run now lives in the
    # bookkeeping store, not SilverDatabase.
    bookkeeping = bookkeeping_fixture()
    bookkeeping.start_pipeline_run(
        {
            "pipeline_run_id": "run-1",
            "command_name": "seed-universe",
            "runtime_mode": "bronze_capture",
            "environment_name": "test",
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "status": "running",
            "arguments": {},
            "scope": {},
            "bronze_root": context.bronze_root.root,
            "storage_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
        }
    )
    bookkeeping.complete_pipeline_run(
        "run-1",
        status="succeeded",
        writes=[],
        raw_writes=[
            {
                "layer": "bronze_raw",
                "path": raw_path,
                "relative_path": "raw/test.json",
                "sha256": "6bc0da1f42f96fc37b8bd7ed20ba57606d2a0da5cda2b135c7854fbdc985b8a3",
            }
        ],
        metrics={},
    )

    with patch.object(vpr_module, "_bookkeeping_store", return_value=bookkeeping):
        report = verify_pipeline_run(context=context, run_id="run-1")

    assert report["status"] == "ok"
    assert report["hashes_checked"] == 1
    assert report["missing_paths"] == []
    assert report["hash_mismatches"] == []


def test_verify_pipeline_run_commits_the_verification_record(tmp_path) -> None:
    """2026-09-01 durability bug: without an explicit commit, verify-
    pipeline-run's own record_pipeline_verification write is silently
    rolled back when the process exits, same as the bronze-capture bug."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from edgar_warehouse.application.commands import verify_pipeline_run as vpr_module
    from edgar_warehouse.application.commands.verify_pipeline_run import verify_pipeline_run
    from edgar_warehouse.bookkeeping.database import Base as BookkeepingBase
    from edgar_warehouse.bookkeeping.store import BookkeepingStore

    context = _context(tmp_path)
    raw_payload = b'{"ok": true}'
    raw_path = context.bronze_root.write_bytes("raw/test.json", raw_payload)

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BookkeepingBase.metadata.create_all(engine)
    writer_session = Session(engine)
    bookkeeping = BookkeepingStore(writer_session)
    bookkeeping.start_pipeline_run(
        {
            "pipeline_run_id": "run-1",
            "command_name": "seed-universe",
            "runtime_mode": "bronze_capture",
            "environment_name": "test",
            "started_at": datetime(2026, 1, 1, tzinfo=UTC),
            "status": "running",
            "arguments": {},
            "scope": {},
            "bronze_root": context.bronze_root.root,
            "storage_root": context.storage_root.root,
            "silver_root": context.silver_root.root,
        }
    )
    bookkeeping.complete_pipeline_run(
        "run-1",
        status="succeeded",
        writes=[],
        raw_writes=[
            {
                "layer": "bronze_raw",
                "path": raw_path,
                "relative_path": "raw/test.json",
                "sha256": "6bc0da1f42f96fc37b8bd7ed20ba57606d2a0da5cda2b135c7854fbdc985b8a3",
            }
        ],
        metrics={},
    )
    bookkeeping.commit()

    with patch.object(vpr_module, "_bookkeeping_store", return_value=bookkeeping):
        verify_pipeline_run(context=context, run_id="run-1")

    # Mirrors real process exit: close the writer's session without an
    # explicit commit call site here -- if verify_pipeline_run() didn't
    # commit internally, this write is gone.
    writer_session.close()

    with Session(engine) as later_session:
        row = BookkeepingStore(later_session).get_pipeline_run("run-1")
        assert row is not None
        assert row["verification_status"] == "ok"
