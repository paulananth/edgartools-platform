"""pipeline-resumability ticket 02: default-path Clean and Merge Filings (formerly BatchSilver) resume markers.

Covers edgar_warehouse.application.batch_silver_resume, which reuses
relationship_bulk_load.py's batch_identity_for_ciks/build_remaining_cik_batches
helpers for the Clean and Merge Filings resume.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from edgar_warehouse.application.batch_silver_resume import (
    ResumeRunNotFoundError,
    batch_done_prefix,
    build_default_batch_done_marker,
    cik_batches_path,
    compute_remaining_batches,
    resume_prefix,
    write_default_batch_done_marker,
)
from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    batch_identity_for_ciks,
)
from edgar_warehouse.infrastructure.dataset_path_catalog import default_path_resolver


def test_resume_prefix_matches_seed_bronze_batches_convention() -> None:
    # Relative to context.bronze_root.root (already WAREHOUSE_BRONZE_ROOT,
    # e.g. s3://bucket/warehouse/bronze) -- NOT prefixed with "warehouse/
    # bronze/" itself, matching default_path_resolver().
    # cik_universe_batches_path()'s own relative_path convention exactly.
    assert resume_prefix("run-1") == "reference/cik_universe/runs/run-1"
    assert cik_batches_path("run-1") == "reference/cik_universe/runs/run-1/cik_batches.jsonl"
    assert batch_done_prefix("run-1") == "reference/cik_universe/runs/run-1/batch_done/"


def test_default_marker_schema() -> None:
    marker = build_default_batch_done_marker(
        ciks=[3, 1, 2], resume_ledger_run_id="run-1", completed_at="2026-08-08T00:00:00Z",
    )
    assert marker["marker_kind"] == "default_batch_done"
    assert marker["batch_identity"] == batch_identity_for_ciks([1, 2, 3])
    assert marker["cik_list"] == "1,2,3"
    assert marker["cik_count"] == 3
    # The marker records completion only: no ledger or terminal-count fields
    # (the strict release marker that carried them was deleted in Ticket 11).
    assert "inventory_fingerprint" not in marker
    assert "ledger_fingerprint" not in marker
    assert "terminal_counts" not in marker


def test_default_marker_rejects_empty_cik_list() -> None:
    with pytest.raises(InventoryError, match="non-empty"):
        build_default_batch_done_marker(
            ciks=[], resume_ledger_run_id="run-1", completed_at="2026-08-08T00:00:00Z",
        )


def test_write_default_batch_done_marker_roundtrip(tmp_path: Path) -> None:
    path = write_default_batch_done_marker(
        bronze_root=str(tmp_path),
        ciks=[10, 20],
        resume_ledger_run_id="run-1",
        completed_at="2026-08-08T00:00:00Z",
    )
    identity = batch_identity_for_ciks([10, 20])
    assert path.endswith(f"batch_done/{identity}.json")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload["batch_identity"] == identity
    assert payload["resume_ledger_run_id"] == "run-1"


def _write_manifest(root: Path, run_id: str, rows: list[dict]) -> None:
    path = root / cik_batches_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )


class TestComputeRemainingBatches:
    def test_fails_closed_when_manifest_missing(self, tmp_path: Path) -> None:
        with pytest.raises(ResumeRunNotFoundError, match="no frozen"):
            compute_remaining_batches(
                bronze_root=str(tmp_path), resume_ledger_run_id="nonexistent-run",
            )

    def test_fails_closed_when_manifest_empty(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, "run-1", [])
        with pytest.raises(ResumeRunNotFoundError, match="empty"):
            compute_remaining_batches(
                bronze_root=str(tmp_path), resume_ledger_run_id="run-1",
            )

    def test_all_done_proceeds_with_zero_remaining(self, tmp_path: Path) -> None:
        """A real manifest with every batch already marked done is a valid,
        non-error outcome -- distinct from a bogus/missing pointer (advisor
        concern: an empty remaining list must not be ambiguous)."""
        batches = [{"cik_list": "1,2"}, {"cik_list": "3"}]
        _write_manifest(tmp_path, "run-1", batches)
        write_default_batch_done_marker(
            bronze_root=str(tmp_path), ciks=[1, 2],
            resume_ledger_run_id="run-1", completed_at="2026-08-08T00:00:00Z",
        )
        write_default_batch_done_marker(
            bronze_root=str(tmp_path), ciks=[3],
            resume_ledger_run_id="run-1", completed_at="2026-08-08T00:00:00Z",
        )
        remaining, counts = compute_remaining_batches(
            bronze_root=str(tmp_path), resume_ledger_run_id="run-1",
        )
        assert remaining == []
        assert counts == {
            "total_batch_count": 2, "done_batch_count": 2, "remaining_batch_count": 0,
        }

    def test_partial_resume_computes_exact_complement(self, tmp_path: Path) -> None:
        batches = [{"cik_list": "1,2"}, {"cik_list": "3"}, {"cik_list": "4,5"}]
        _write_manifest(tmp_path, "run-1", batches)
        write_default_batch_done_marker(
            bronze_root=str(tmp_path), ciks=[1, 2],
            resume_ledger_run_id="run-1", completed_at="2026-08-08T00:00:00Z",
        )
        remaining, counts = compute_remaining_batches(
            bronze_root=str(tmp_path), resume_ledger_run_id="run-1",
        )
        assert remaining == [{"cik_list": "3"}, {"cik_list": "4,5"}]
        assert counts == {
            "total_batch_count": 3, "done_batch_count": 1, "remaining_batch_count": 2,
        }

    def test_no_markers_yet_returns_full_manifest(self, tmp_path: Path) -> None:
        """A resumed run whose original attempt never completed a single
        batch still has a real manifest -- remaining == everything, not an
        error."""
        batches = [{"cik_list": "1,2"}, {"cik_list": "3"}]
        _write_manifest(tmp_path, "run-1", batches)
        remaining, counts = compute_remaining_batches(
            bronze_root=str(tmp_path), resume_ledger_run_id="run-1",
        )
        assert remaining == batches
        assert counts["done_batch_count"] == 0


class TestComputeRemainingBatchesDispatchIntegration:
    """End-to-end through warehouse_orchestrator._capture_bronze_raw's
    "compute-remaining-batches" branch -- exercises the real
    context.bronze_root.write_text/default_path_resolver() path convention
    both Initialize From Bronze and Clean and Merge Filings' ItemReader actually use, not just
    batch_silver_resume.py's own functions in isolation. This is what
    surfaced a real double-prefix bug during implementation (resume_prefix()
    originally re-added "warehouse/bronze/" on top of context.bronze_root.root,
    which already contains it)."""

    def _make_context(self, tmp_path: Path):
        from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
        from edgar_warehouse.infrastructure.object_storage import StorageLocation

        bronze = tmp_path / "bronze"
        storage = tmp_path / "storage"
        silver = tmp_path / "silver"
        for p in (bronze, storage, silver):
            p.mkdir()
        return WarehouseCommandContext(
            bronze_root=StorageLocation(str(bronze)),
            storage_root=StorageLocation(str(storage)),
            silver_root=StorageLocation(str(silver)),
            snowflake_export_root=None,
            environment_name="test",
            identity="test@example.com",
            runtime_mode="bronze_capture",
        )

    def test_reads_original_manifest_and_writes_filtered_remainder_at_the_real_path(
        self, tmp_path: Path
    ) -> None:
        from datetime import UTC, datetime

        from edgar_warehouse.application import warehouse_orchestrator as wo

        context = self._make_context(tmp_path)
        # Seed the original run's manifest the same way Initialize From Bronze
        # really does: context.bronze_root.write_text(relative_path, ...).
        original_rel = default_path_resolver().cik_universe_batches_path("original-run")
        context.bronze_root.write_text(original_rel, '{"cik_list": "1,2"}\n{"cik_list": "3"}\n')
        write_default_batch_done_marker(
            bronze_root=context.bronze_root.root, ciks=[1, 2],
            resume_ledger_run_id="original-run", completed_at="2026-08-08T00:00:00Z",
        )

        raw_writes, metrics = wo._capture_bronze_raw(
            context=context, db=None, bookkeeping=None, command_name="compute-remaining-batches",
            arguments={"resume_ledger_run_id": "original-run", "run_id": "resume-run-2"},
            scope={}, now=datetime.now(UTC), sync_run_id="resume-run-2",
        )

        assert raw_writes == []
        assert metrics["total_batch_count"] == 2
        assert metrics["done_batch_count"] == 1
        assert metrics["remaining_batch_count"] == 1
        assert metrics["resume_ledger_run_id"] == "original-run"

        # Clean and Merge Filings' ItemReader always reads runs/{$$.Execution.Name}/
        # cik_batches.jsonl -- confirm this handler populated exactly that
        # path (not the original run's path, a copy/filter under the NEW
        # execution name) with only the not-yet-done batch.
        resumed_rel = default_path_resolver().cik_universe_batches_path("resume-run-2")
        written = (tmp_path / "bronze" / resumed_rel).read_text(encoding="utf-8")
        assert written.strip() == '{"cik_list": "3"}'

    def test_raises_on_bogus_pointer_without_writing_anything(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from edgar_warehouse.application import warehouse_orchestrator as wo

        context = self._make_context(tmp_path)

        with pytest.raises(ResumeRunNotFoundError):
            wo._capture_bronze_raw(
                context=context, db=None, bookkeeping=None, command_name="compute-remaining-batches",
                arguments={"resume_ledger_run_id": "typo-d-run-id", "run_id": "resume-run-2"},
                scope={}, now=datetime.now(UTC), sync_run_id="resume-run-2",
            )

        resumed_rel = default_path_resolver().cik_universe_batches_path("resume-run-2")
        assert not (tmp_path / "bronze" / resumed_rel).exists()

    def test_missing_resume_ledger_run_id_argument_raises(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from edgar_warehouse.application.errors import WarehouseRuntimeError
        from edgar_warehouse.application import warehouse_orchestrator as wo

        context = self._make_context(tmp_path)

        with pytest.raises(WarehouseRuntimeError, match="--resume-ledger-run-id"):
            wo._capture_bronze_raw(
                context=context, db=None, bookkeeping=None, command_name="compute-remaining-batches",
                arguments={"run_id": "resume-run-2"},
                scope={}, now=datetime.now(UTC), sync_run_id="resume-run-2",
            )


class TestBootstrapBatchWritesDefaultDoneMarker:
    """bootstrap-batch's success path (warehouse_orchestrator.py,
    right after _run_submissions_bronze_then_silver) now writes a default_batch_done
    marker. _run_submissions_bronze_then_silver itself is mocked -- this covers the
    marker-write wiring, not the underlying SEC-fetch pipeline (already covered
    elsewhere)."""

    def _make_context(self, tmp_path: Path):
        from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
        from edgar_warehouse.infrastructure.object_storage import StorageLocation

        return WarehouseCommandContext(
            bronze_root=StorageLocation(str(tmp_path / "bronze")),
            storage_root=StorageLocation(str(tmp_path / "storage")),
            silver_root=StorageLocation(str(tmp_path / "silver")),
            snowflake_export_root=None,
            environment_name="test",
            identity="tester@example.com",
            runtime_mode="bronze_capture",
        )

    def test_default_path_writes_marker_under_resume_ledger_run_id(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime
        from unittest.mock import patch

        from edgar_warehouse.application import warehouse_orchestrator as wo

        context = self._make_context(tmp_path)
        with patch.object(
            wo, "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 1, "rows_skipped": 0},
        ):
            raw_writes, metrics = wo._capture_bronze_raw(
                context=context, db=None, bookkeeping=None, command_name="bootstrap-batch",
                arguments={
                    "cik_list": [1, 2], "resume_ledger_run_id": "original-run",
                },
                scope={}, now=datetime.now(UTC), sync_run_id="fresh-execution-name",
            )

        assert metrics["resume_ledger_run_id"] == "original-run"
        identity = batch_identity_for_ciks([1, 2])
        marker_path = (
            tmp_path / "bronze" / batch_done_prefix("original-run") / f"{identity}.json"
        )
        assert marker_path.exists()
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
        assert payload["resume_ledger_run_id"] == "original-run"
        assert payload["cik_list"] == "1,2"

    def test_default_path_falls_back_to_sync_run_id_when_flag_omitted(
        self, tmp_path: Path
    ) -> None:
        """Every run (fresh or resumed) writes markers under SOME effective
        run id -- when --resume-ledger-run-id is omitted, that's this run's
        own sync_run_id, so a LATER resume can point at it."""
        from datetime import UTC, datetime
        from unittest.mock import patch

        from edgar_warehouse.application import warehouse_orchestrator as wo

        context = self._make_context(tmp_path)
        with patch.object(
            wo, "_run_submissions_bronze_then_silver",
            return_value={"raw_writes": [], "rows_written": 1, "rows_skipped": 0},
        ):
            _, metrics = wo._capture_bronze_raw(
                context=context, db=None, bookkeeping=None, command_name="bootstrap-batch",
                arguments={"cik_list": [7]},
                scope={}, now=datetime.now(UTC), sync_run_id="fresh-execution-name",
            )

        assert metrics["resume_ledger_run_id"] == "fresh-execution-name"
        identity = batch_identity_for_ciks([7])
        marker_path = (
            tmp_path / "bronze" / batch_done_prefix("fresh-execution-name") / f"{identity}.json"
        )
        assert marker_path.exists()

