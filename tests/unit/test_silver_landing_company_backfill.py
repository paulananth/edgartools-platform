"""Tests for the duckdb-retirement map's one-time company-metadata backfill
(edgar_warehouse/silver_landing_company_backfill.py).

Root cause this closes: `_stage_submission_locked`'s caller skips
merge_company/merge_addresses/merge_former_names/merge_submission_files
entirely whenever a CIK's submissions.json checksum is unchanged since its
last sync -- so sec_company/sec_company_address/sec_company_former_name/
sec_company_submission_file rows that predate the landing-zone write path
never get tracked into it through the ongoing incremental path. These tests
build real shard DuckDB files (via SilverDatabase, not a hand-rolled stub --
see CLAUDE.md's schema-drift lesson) and exercise the module against them.
"""
from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_landing_company_backfill import (
    _BACKFILL_TABLES,
    run_silver_landing_company_backfill,
)
from edgar_warehouse.silver_store import SilverDatabase


def _context(tmp_path, *, silver_landing_export_root: StorageLocation | None) -> WarehouseCommandContext:
    return WarehouseCommandContext(
        bronze_root=StorageLocation(str(tmp_path / "bronze")),
        storage_root=StorageLocation(str(tmp_path / "warehouse")),
        silver_root=StorageLocation(str(tmp_path / "silver")),
        snowflake_export_root=None,
        environment_name="test",
        identity="EdgarTools Platform test@example.com",
        runtime_mode="bronze_capture",
        silver_landing_export_root=silver_landing_export_root,
    )


def _build_shard(path, *, cik: int, entity_name: str) -> None:
    db = SilverDatabase(str(path))
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_sync_run_id) VALUES (?, ?, 'seed')",
        [cik, entity_name],
    )
    db._conn.execute(
        "INSERT INTO sec_company_address (cik, address_type, city, last_sync_run_id) VALUES (?, 'business', 'Cupertino', 'seed')",
        [cik],
    )
    db._conn.execute(
        "INSERT INTO sec_company_former_name (cik, former_name, ordinal, last_sync_run_id) VALUES (?, 'Old Co', 1, 'seed')",
        [cik],
    )
    db._conn.execute(
        "INSERT INTO sec_company_submission_file (cik, file_name, last_sync_run_id) VALUES (?, 'submissions.json', 'seed')",
        [cik],
    )
    db.close()


def test_backfill_requires_landing_export_root(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    context = _context(tmp_path, silver_landing_export_root=None)

    with pytest.raises(WarehouseRuntimeError, match="SILVER_LANDING_EXPORT_ROOT"):
        run_silver_landing_company_backfill(context, "run-1")


def test_backfill_raises_when_no_shards_found(tmp_path, monkeypatch) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
        lambda ctx: [None, None],
    )

    with pytest.raises(WarehouseRuntimeError, match="No silver shards"):
        run_silver_landing_company_backfill(context, "run-1")


def test_backfill_unions_rows_across_shards_and_flushes_to_landing_zone(tmp_path, monkeypatch) -> None:
    shard0 = tmp_path / "shard-0.duckdb"
    shard1 = tmp_path / "shard-1.duckdb"
    _build_shard(shard0, cik=320193, entity_name="Apple Inc")
    _build_shard(shard1, cik=789019, entity_name="Microsoft Corp")

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
        lambda ctx: [str(shard0), str(shard1)],
    )

    result = run_silver_landing_company_backfill(context, "backfill-run-1")

    assert result["command"] == "backfill-silver-landing-company-metadata"
    for table in _BACKFILL_TABLES:
        assert result["source_counts"][table] == 2, table
        assert result["landing_export"][table] == 2, table

    company_files = list((tmp_path / "silver-landing" / "sec_company").rglob("*.parquet"))
    assert len(company_files) == 1
    table = pq.read_table(company_files[0])
    names = sorted(table.column("entity_name").to_pylist())
    assert names == ["Apple Inc", "Microsoft Corp"]

    manifest_files = list((tmp_path / "silver-landing" / "manifests").rglob("run_manifest.json"))
    assert len(manifest_files) == 1
    manifest = json.loads(manifest_files[0].read_text())
    assert manifest["workflow_name"] == "backfill_silver_landing_company_metadata"
    written_tables = {entry["table_name"] for entry in manifest["tables"]}
    assert written_tables == set(_BACKFILL_TABLES)


def test_backfill_skips_empty_tables_gracefully(tmp_path, monkeypatch) -> None:
    """A shard with company rows but no former-name rows still flushes the
    tables that do have content -- write_landing_export already omits empty
    tables (its own documented behavior); this just proves the caller
    doesn't choke on that."""
    shard0 = tmp_path / "shard-0.duckdb"
    db = SilverDatabase(str(shard0))
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_sync_run_id) VALUES (320193, 'Apple Inc', 'seed')"
    )
    db.close()

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
        lambda ctx: [str(shard0)],
    )

    result = run_silver_landing_company_backfill(context, "backfill-run-2")

    assert result["source_counts"]["sec_company"] == 1
    assert result["source_counts"]["sec_company_former_name"] == 0
    assert "sec_company_former_name" not in result["landing_export"]
    assert result["landing_export"]["sec_company"] == 1
