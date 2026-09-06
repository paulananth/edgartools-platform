"""release-readiness ticket 87: an immutable-object conflict on a single
accession (confirmed live to be a genuine, if narrow, SEC-side byte-level
drift -- not a bug in this repo's capture path, see the ticket file) must
not abort an entire `targeted-resync --scope-type cik` run. Isolate to the
one accession and continue; any other exception type still fails the run,
matching the existing `_is_immutable_object_conflict` classification
already used by the daily-artifact-resume path (test_artifact_fetch_concurrency.py).
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from edgar_warehouse.application import warehouse_orchestrator
from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


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


def _submissions_result(accessions: list[str]) -> dict:
    return {
        "raw_writes": [],
        "rows_written": 0,
        "rows_skipped": 0,
        "recent_accessions": accessions,
    }


class _FakeDb:
    """Minimal get_filing-only stand-in for _configured_parser_accessions.

    Every accession maps to a Form 4 (a configured parser form). An
    accession with no entry in ``filing_dates`` gets no filing_date key at
    all, so it always passes the gate's lookback check regardless of
    window (see _ownership_within_lookback's "undated rows are rare, keep
    them" rule) -- this is what these conflict-isolation tests use, since
    they're about conflict handling, not lookback filtering, and every
    accession must reach _run_accession_resync unfiltered. Shared with
    test_targeted_resync_lookback_gating.py, which passes real
    ``filing_dates`` to exercise genuine date-window filtering instead.
    """

    def __init__(self, filing_dates: dict[str, date] | None = None) -> None:
        self._filing_dates = filing_dates or {}

    def get_filing(self, accession_number: str) -> dict:
        filing: dict = {"form": "4"}
        filing_date = self._filing_dates.get(accession_number)
        if filing_date is not None:
            filing["filing_date"] = filing_date.isoformat()
        return filing


def test_immutable_object_conflict_on_one_accession_does_not_abort_the_cik_resync(
    tmp_path,
) -> None:
    accessions = ["0000320193-24-000073", "0000320193-24-000075", "0000320193-24-000077"]
    conflicting = "0000320193-24-000075"

    def fake_run_accession_resync(*, accession_number, **_kwargs):
        if accession_number == conflicting:
            raise WarehouseRuntimeError(
                f"immutable object 'filings/sec/cik=320193/accession={conflicting}/"
                "primary/wk-form4_1717453877.xml' already exists with different content"
            )
        return {"raw_writes": [{"accession_number": accession_number}], "rows_written": 1}

    with (
        patch.object(
            warehouse_orchestrator,
            "submissions_orchestrator",
            return_value=_submissions_result(accessions),
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_accession_resync",
            side_effect=fake_run_accession_resync,
        ),
    ):
        raw_writes, metrics = warehouse_orchestrator._capture_bronze_raw(
            context=_context(tmp_path),
            db=_FakeDb(),
            bookkeeping=object(),
            command_name="targeted-resync",
            arguments={
                "scope_type": "cik",
                "scope_key": "320193",
                "include_artifacts": True,
                "include_text": False,
                "include_parsers": False,
            },
            scope={"scope_type": "cik", "scope_key": "320193"},
            now=datetime(2026, 8, 4, 12, tzinfo=UTC),
            sync_run_id="test-run",
        )

    # The two non-conflicting accessions still processed and merged.
    assert len(raw_writes) == 2
    assert metrics["rows_inserted"] == 2
    # The conflicting accession is recorded as skipped, not silently dropped.
    assert metrics["accessions_conflict_skipped"] == 1


def test_non_conflict_error_on_one_accession_still_aborts_the_whole_run(tmp_path) -> None:
    """A genuinely different failure (network error, real bug, etc.) must
    still fail the whole command -- only the specific immutable-object-
    conflict classification is isolated, never a blanket catch-all."""
    accessions = ["0000320193-24-000073", "0000320193-24-000075"]

    def fake_run_accession_resync(*, accession_number, **_kwargs):
        if accession_number == "0000320193-24-000075":
            raise WarehouseRuntimeError("SEC request failed: connection reset")
        return {"raw_writes": [], "rows_written": 1}

    with (
        patch.object(
            warehouse_orchestrator,
            "submissions_orchestrator",
            return_value=_submissions_result(accessions),
        ),
        patch.object(
            warehouse_orchestrator,
            "_run_accession_resync",
            side_effect=fake_run_accession_resync,
        ),
    ):
        try:
            warehouse_orchestrator._capture_bronze_raw(
                context=_context(tmp_path),
                db=_FakeDb(),
                bookkeeping=object(),
                command_name="targeted-resync",
                arguments={
                    "scope_type": "cik",
                    "scope_key": "320193",
                    "include_artifacts": True,
                    "include_text": False,
                    "include_parsers": False,
                },
                scope={"scope_type": "cik", "scope_key": "320193"},
                now=datetime(2026, 8, 4, 12, tzinfo=UTC),
                sync_run_id="test-run",
            )
        except WarehouseRuntimeError as exc:
            assert "connection reset" in str(exc)
        else:
            raise AssertionError("expected the non-conflict error to propagate and fail the run")
