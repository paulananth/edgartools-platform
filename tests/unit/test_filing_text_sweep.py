"""release-readiness Ticket 101: tests for the filing-text sweep
(edgar_warehouse/filing_text_sweep.py) -- the required/processed
computation, per-CIK isolation on failure, the optional --limit cap, and
cleanup-candidate identification (never deletion).

Stubs a Snowflake reader (matching SnowflakeSilverReader.fetch's real
list[dict] return shape, not its cursor internals -- this module never
touches a raw cursor) and mocks submissions_orchestrator/extract_filing_text
at their real definition sites, since filing_text_sweep imports both
locally (inside the function body) to avoid a circular import with
warehouse_orchestrator -- patching the definition site is what a
call-time `from X import Y` actually resolves against.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from edgar_warehouse.filing_text_sweep import run_filing_text_sweep
from edgar_warehouse.infrastructure.object_storage import StorageLocation


class _StubSnowflakeReader:
    """Matches SQL substrings to canned rows, like this repo's own
    StubSilver pattern elsewhere -- adequate here since this module's
    queries are simple enough that substring routing doesn't risk masking
    a real WHERE-clause bug (unlike the richer filtering StubSilver
    deliberately can't validate for run_companies())."""

    def __init__(
        self,
        required_rows: list[dict],
        processed_accessions: set[str],
        all_processed_rows: list[dict],
        *,
        published_after_sweep_rows: list[dict] | None = None,
    ):
        self._required_rows = required_rows
        self._processed_accessions = processed_accessions
        self._all_processed_rows = all_processed_rows
        self._published_after_sweep_rows = published_after_sweep_rows
        self.closed = False
        self.queries: list[str] = []
        self.snapshot_calls = 0

    def fetch_with_query_id(
        self, sql: str, params: list | None = None
    ) -> tuple[list[dict], str]:
        self.queries.append(sql)
        assert "retention_set" in sql
        self.snapshot_calls += 1
        all_processed = self._all_processed_rows
        if self.snapshot_calls > 1 and self._published_after_sweep_rows is not None:
            all_processed = self._published_after_sweep_rows
        rows = list(all_processed)
        represented = {row["accession_number"] for row in rows}
        required_ciks = {
            row["accession_number"]: row["cik"] for row in self._required_rows
        }
        rows.extend(
            {
                "cik": required_ciks[accession],
                "accession_number": accession,
            }
            for accession in sorted(self._processed_accessions - represented)
        )
        required = [
            {
                "retention_set": "required",
                "text_version": "generic_text_v1",
                "text_storage_path": None,
                "text_sha256": None,
                **row,
            }
            for row in self._required_rows
        ]
        processed = [
            {
                "retention_set": "processed",
                "text_version": "generic_text_v1",
                "text_storage_path": (
                    "s3://edgartools-prod-warehouse-690839588395/warehouse/text/sec/"
                    f"cik={row['cik']}/accession={row['accession_number']}/generic_text_v1.txt"
                ),
                "text_sha256": "a" * 64,
                "filing_date": None,
                **row,
            }
            for row in rows
        ]
        return required + processed, f"query-snapshot-{self.snapshot_calls}"

    def close(self) -> None:
        self.closed = True


def _row(cik: int, accession: str, filing_date: date = date(2026, 1, 1)) -> dict[str, Any]:
    return {"cik": cik, "accession_number": accession, "filing_date": filing_date}


def _patched(reader: _StubSnowflakeReader, submissions_mock: MagicMock, extract_mock: MagicMock):
    return (
        patch(
            "edgar_warehouse.silver_support.snowflake_reader.SnowflakeSilverReader.connect",
            return_value=reader,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.submissions_orchestrator",
            submissions_mock,
        ),
        patch(
            "edgar_warehouse.infrastructure.filing_artifact_service.extract_filing_text",
            extract_mock,
        ),
    )


class TestRunFilingTextSweep:
    def test_persists_complete_exact_identity_retention_manifest(
        self, tmp_path
    ) -> None:
        current = "0000910001-26-000001"
        old = "0000910001-24-000001"
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, current)],
            processed_accessions={current},
            all_processed_rows=[
                {"cik": 910001, "accession_number": current},
                {"cik": 910001, "accession_number": old},
            ],
        )
        context = SimpleNamespace(storage_root=StorageLocation(str(tmp_path)))

        p1, p2, p3 = _patched(reader, MagicMock(), MagicMock())
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=context,
                db=MagicMock(),
                bookkeeping=MagicMock(),
                sync_run_id="run-manifest",
                now=datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
            )

        manifest_path = (
            tmp_path
            / "artifacts"
            / "filing_text_retention"
            / "observed_date=2026-09-07"
            / "run_id=run-manifest"
            / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "succeeded"
        assert manifest["run_id"] == "run-manifest"
        assert manifest["required"] == [
            {"accession_number": current, "text_version": "generic_text_v1"}
        ]
        assert {row["accession_number"] for row in manifest["not_required"]} == {old}
        assert manifest["counts"] == {
            "not_required": 1,
            "processed": 2,
            "required": 1,
            "unclassified": 0,
        }
        assert len(manifest["manifest_hash"]) == 64
        assert manifest["snowflake_publication_identity"] == {
            "query_id": "query-snapshot-2",
            "snapshot_hash": manifest["set_hashes"]["snowflake_snapshot"],
        }
        assert reader.snapshot_calls == 2
        assert metrics["retention_manifest_path"] == str(manifest_path)

        p1, p2, p3 = _patched(reader, MagicMock(), MagicMock())
        with p1, p2, p3:
            run_filing_text_sweep(
                context=context,
                db=MagicMock(),
                bookkeeping=MagicMock(),
                sync_run_id="run-manifest-next",
                now=datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
            )

        next_manifest_path = (
            tmp_path
            / "artifacts"
            / "filing_text_retention"
            / "observed_date=2026-09-08"
            / "run_id=run-manifest-next"
            / "manifest.json"
        )
        next_manifest = json.loads(next_manifest_path.read_text(encoding="utf-8"))
        assert next_manifest["previous_manifest_hash"] == manifest["manifest_hash"]
        assert next_manifest["previous_run_id"] == "run-manifest"
        assert (
            next_manifest["not_required"][0]["not_required_since"]
            == "2026-09-07T12:00:00Z"
        )

    def test_required_and_unprocessed_cik_gets_extracted(self) -> None:
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, "0000910001-26-000001")],
            processed_accessions=set(),
            all_processed_rows=[],
        )
        db = MagicMock()
        db.get_filing.return_value = {"cik": 910001}
        submissions_mock = MagicMock(return_value={"raw_writes": []})
        extract_mock = MagicMock(return_value={"accession_number": "0000910001-26-000001"})

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=db, bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC),
            )

        assert metrics["rows_inserted"] == 1
        assert metrics["cik_error_count"] == 0
        submissions_mock.assert_called_once()
        assert submissions_mock.call_args.kwargs["cik"] == 910001
        extract_mock.assert_called_once()
        assert extract_mock.call_args.kwargs["accession_number"] == "0000910001-26-000001"

    def test_manifest_uses_authoritative_post_projection_snowflake_snapshot(
        self, tmp_path
    ) -> None:
        current = "0000910001-26-000001"
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, current)],
            processed_accessions=set(),
            all_processed_rows=[],
            published_after_sweep_rows=[
                {"cik": 910001, "accession_number": current}
            ],
        )
        db = MagicMock()
        db.get_filing.return_value = {"cik": 910001}
        context = SimpleNamespace(storage_root=StorageLocation(str(tmp_path)))

        p1, p2, p3 = _patched(
            reader,
            MagicMock(return_value={"raw_writes": []}),
            MagicMock(return_value={"accession_number": current}),
        )
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=context,
                db=db,
                bookkeeping=MagicMock(),
                sync_run_id="run-published",
                now=datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
            )

        manifest = json.loads(
            Path(metrics["retention_manifest_path"]).read_text(encoding="utf-8")
        )
        assert manifest["status"] == "succeeded"
        assert {row["accession_number"] for row in manifest["processed"]} == {
            current
        }
        assert manifest["snowflake_publication_identity"]["query_id"] == (
            "query-snapshot-2"
        )

    def test_manifest_is_incomplete_until_extracted_row_is_visible_in_snowflake(
        self, tmp_path
    ) -> None:
        current = "0000910001-26-000001"
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, current)],
            processed_accessions=set(),
            all_processed_rows=[],
        )
        db = MagicMock()
        db.get_filing.return_value = {"cik": 910001}
        context = SimpleNamespace(storage_root=StorageLocation(str(tmp_path)))

        p1, p2, p3 = _patched(
            reader,
            MagicMock(return_value={"raw_writes": []}),
            MagicMock(return_value={"accession_number": current}),
        )
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=context,
                db=db,
                bookkeeping=MagicMock(),
                sync_run_id="run-not-yet-published",
                now=datetime(2026, 9, 7, 12, 0, tzinfo=UTC),
            )

        manifest = json.loads(
            Path(metrics["retention_manifest_path"]).read_text(encoding="utf-8")
        )
        assert manifest["status"] == "incomplete"
        assert metrics["retention_unpublished_required_count"] == 1

    def test_already_processed_accession_is_skipped(self) -> None:
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, "0000910001-26-000001")],
            processed_accessions={"0000910001-26-000001"},
            all_processed_rows=[],
        )
        submissions_mock = MagicMock()
        extract_mock = MagicMock()

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=MagicMock(), bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC),
            )

        assert metrics["rows_inserted"] == 0
        submissions_mock.assert_not_called()
        extract_mock.assert_not_called()

    def test_accession_not_found_after_staging_is_skipped_not_an_error(self) -> None:
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, "0000910001-26-000001")],
            processed_accessions=set(),
            all_processed_rows=[],
        )
        db = MagicMock()
        db.get_filing.return_value = None  # staged submissions didn't include this accession
        submissions_mock = MagicMock(return_value={"raw_writes": []})
        extract_mock = MagicMock()

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=db, bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC),
            )

        assert metrics["rows_skipped"] == 1
        assert metrics["rows_inserted"] == 0
        assert metrics["cik_error_count"] == 0
        extract_mock.assert_not_called()

    def test_one_ciks_failure_does_not_abort_the_sweep(self) -> None:
        reader = _StubSnowflakeReader(
            required_rows=[
                _row(910001, "0000910001-26-000001"),
                _row(910002, "0000910002-26-000001"),
            ],
            processed_accessions=set(),
            all_processed_rows=[],
        )
        db = MagicMock()
        db.get_filing.return_value = {"cik": 910001}
        submissions_mock = MagicMock(
            side_effect=[RuntimeError("transient SEC error"), {"raw_writes": []}]
        )
        extract_mock = MagicMock(return_value={"accession_number": "x"})

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=db, bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC),
            )

        assert metrics["cik_error_count"] == 1
        assert metrics["rows_inserted"] == 1
        assert submissions_mock.call_count == 2
        extract_mock.assert_called_once()

    def test_limit_caps_how_many_pending_ciks_are_processed(self) -> None:
        reader = _StubSnowflakeReader(
            required_rows=[
                _row(910001, "0000910001-26-000001"),
                _row(910002, "0000910002-26-000001"),
                _row(910003, "0000910003-26-000001"),
            ],
            processed_accessions=set(),
            all_processed_rows=[],
        )
        db = MagicMock()
        db.get_filing.return_value = {"cik": 910001}
        submissions_mock = MagicMock(return_value={"raw_writes": []})
        extract_mock = MagicMock(return_value={"accession_number": "x"})

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=db, bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC), limit=1,
            )

        assert metrics["rows_inserted"] == 1
        assert submissions_mock.call_count == 1

    def test_cleanup_candidates_are_reported_not_deleted(self) -> None:
        """A CIK with an existing sec_filing_text row that is NOT in the
        required set (e.g. it's an individual, or aged out) must be
        surfaced in metrics -- and this module has no delete path at all
        to accidentally exercise."""
        reader = _StubSnowflakeReader(
            required_rows=[_row(910001, "0000910001-26-000001")],
            processed_accessions={"0000910001-26-000001"},
            all_processed_rows=[
                {"cik": 910001, "accession_number": "0000910001-26-000001"},
                {"cik": 999999, "accession_number": "0000999999-20-000001"},  # not required
            ],
        )
        submissions_mock = MagicMock()
        extract_mock = MagicMock()

        p1, p2, p3 = _patched(reader, submissions_mock, extract_mock)
        with p1, p2, p3:
            _raw_writes, metrics = run_filing_text_sweep(
                context=MagicMock(), db=MagicMock(), bookkeeping=MagicMock(),
                sync_run_id="run-1", now=datetime.now(UTC),
            )

        assert metrics["cleanup_candidate_count"] == 1
        assert reader.closed
