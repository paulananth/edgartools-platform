"""Tests for the seed-bronze-batches CIK-discovery helper.

seed-bronze-batches discovers CIKs by listing S3/local bronze directly
(`submissions/sec/cik={cik}/...`), unlike seed-silver-batches which queries
silver DuckDB's own bookkeeping tables. This means it works even when silver
is empty — e.g. bronze was copied in from another environment and silver has
never been built — with zero new SEC calls.
"""
from __future__ import annotations

from edgar_warehouse.application.warehouse_orchestrator import _list_bronze_submission_ciks
from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation


def _context(tmp_path) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="dev@example.com",
        runtime_mode="bronze_capture",
    )


def test_lists_distinct_ciks_from_bronze_directories(tmp_path):
    context = _context(tmp_path)
    bronze_base = tmp_path / "bronze" / "submissions" / "sec"
    (bronze_base / "cik=320193" / "main" / "2026" / "01" / "01").mkdir(parents=True)
    (bronze_base / "cik=789019" / "pagination" / "2026" / "01" / "01").mkdir(parents=True)

    ciks = _list_bronze_submission_ciks(context)

    assert ciks == ["320193", "789019"]


def test_returns_empty_list_when_bronze_has_no_submissions(tmp_path):
    context = _context(tmp_path)

    assert _list_bronze_submission_ciks(context) == []


def test_ignores_non_cik_entries(tmp_path):
    context = _context(tmp_path)
    bronze_base = tmp_path / "bronze" / "submissions" / "sec"
    bronze_base.mkdir(parents=True)
    (bronze_base / "cik=99780").mkdir()
    (bronze_base / "_tmp_upload").mkdir()
    (bronze_base / "cik=notanumber").mkdir()

    ciks = _list_bronze_submission_ciks(context)

    assert ciks == ["99780"]


def test_sorts_ciks_numerically_not_lexicographically(tmp_path):
    context = _context(tmp_path)
    bronze_base = tmp_path / "bronze" / "submissions" / "sec"
    for cik in ("2", "100", "20"):
        (bronze_base / f"cik={cik}").mkdir(parents=True)

    assert _list_bronze_submission_ciks(context) == ["2", "20", "100"]
