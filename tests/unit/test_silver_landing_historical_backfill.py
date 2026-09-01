"""Tests for the one-time historical silver-landing backfill
(edgar_warehouse/silver_landing_historical_backfill.py).

Root cause this closes: every merge/upsert method in silver_store.py that
tracks rows into the landing-zone buffer (via @track_landing_rows/
@track_landing_row) only fires when it actually executes -- and most of
those methods are themselves gated by a skip-if-unchanged/skip-if-already-
loaded check (this repo's own "SEC data idempotency" policy). Content
captured before -- or without re-triggering -- that write path never gets a
chance to flow into Snowflake silver. Originally scoped to just company
metadata (duckdb-retirement map); widened here (silver-snowflake-migration
map, Ticket 15) after confirming live that the identical gap affects most
of PARITY_TABLES, not just company metadata: sec_adv_filing and
sec_financial_fact had zero Parquet exports ever land in S3 despite tens of
thousands of DuckDB rows each.

These tests build real shard DuckDB files (via SilverDatabase, not a
hand-rolled stub -- see CLAUDE.md's schema-drift lesson) and exercise the
module against them.
"""
from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from edgar_warehouse.domain.models.command_context import WarehouseCommandContext
from edgar_warehouse.infrastructure.object_storage import StorageLocation
from edgar_warehouse.silver_landing_historical_backfill import (
    _BACKFILL_TABLES,
    run_silver_landing_historical_backfill,
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


def _build_shard(path, *, cik: int, entity_name: str, accession_number: str) -> None:
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
    # Two tables outside the original company-metadata-only scope, proving
    # the widened backfill actually reaches beyond it.
    db._conn.execute(
        "INSERT INTO sec_adv_filing (accession_number, cik, form, adviser_name, last_sync_run_id) "
        "VALUES (?, ?, 'ADV', ?, 'seed')",
        [accession_number, cik, entity_name],
    )
    db._conn.execute(
        "INSERT INTO sec_thirteenf_holding "
        "(cik, accession_number, holding_index, period_of_report, issuer_name) "
        "VALUES (?, ?, 1, '2026-06-30', ?)",
        [cik, accession_number, entity_name],
    )
    db.close()


def test_backfill_requires_landing_export_root(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    context = _context(tmp_path, silver_landing_export_root=None)

    with pytest.raises(WarehouseRuntimeError, match="SILVER_LANDING_EXPORT_ROOT"):
        run_silver_landing_historical_backfill(context, "run-1")


def test_backfill_raises_when_no_shards_found(tmp_path, monkeypatch) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
        lambda ctx: [None, None],
    )

    with pytest.raises(WarehouseRuntimeError, match="No silver shards"):
        run_silver_landing_historical_backfill(context, "run-1")


def test_backfill_table_list_excludes_only_sec_company_ticker() -> None:
    """sec_company_ticker is the one PARITY_TABLES entry deliberately left
    out (its landing shape needs enrichment beyond a raw DuckDB row -- see
    module docstring); everything else PARITY_TABLES tracks should be
    covered, including tables well outside the original company-metadata
    scope."""
    from edgar_warehouse.mdm.silver_parity import PARITY_TABLES

    assert "sec_company_ticker" not in _BACKFILL_TABLES
    assert set(_BACKFILL_TABLES) == set(PARITY_TABLES) - {"sec_company_ticker"}
    # Spot-check a few tables from outside the original four this backfill
    # used to be scoped to.
    for table in ("sec_adv_filing", "sec_thirteenf_holding", "sec_financial_fact", "sec_ownership_non_derivative_txn"):
        assert table in _BACKFILL_TABLES


def test_backfill_unions_rows_across_shards_and_flushes_to_landing_zone(tmp_path, monkeypatch) -> None:
    shard0 = tmp_path / "shard-0.duckdb"
    shard1 = tmp_path / "shard-1.duckdb"
    _build_shard(shard0, cik=320193, entity_name="Apple Inc", accession_number="0000320193-26-000001")
    _build_shard(shard1, cik=789019, entity_name="Microsoft Corp", accession_number="0000789019-26-000001")

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    monkeypatch.setattr(
        "edgar_warehouse.application.warehouse_orchestrator._hydrate_all_shards",
        lambda ctx: [str(shard0), str(shard1)],
    )

    result = run_silver_landing_historical_backfill(context, "backfill-run-1")

    assert result["command"] == "backfill-silver-landing-historical"

    # The two seeded tables (present in both shards) round-trip correctly...
    for table in ("sec_company", "sec_adv_filing", "sec_thirteenf_holding"):
        assert result["source_counts"][table] == 2, table
        assert result["landing_export"][table] == 2, table

    # ...and every other backfill table -- unseeded, genuinely empty in these
    # test shards -- is present as a zero source count and correctly absent
    # from the landing_export payload (write_landing_export's own documented
    # "omit empty tables" behavior), not a crash.
    for table in _BACKFILL_TABLES:
        assert table in result["source_counts"], table
        if table not in ("sec_company", "sec_company_address", "sec_company_former_name",
                          "sec_company_submission_file", "sec_adv_filing", "sec_thirteenf_holding"):
            assert result["source_counts"][table] == 0, table
            assert table not in result["landing_export"], table

    adv_files = list((tmp_path / "silver-landing" / "sec_adv_filing").rglob("*.parquet"))
    assert len(adv_files) == 1
    table = pq.read_table(adv_files[0])
    names = sorted(table.column("adviser_name").to_pylist())
    assert names == ["Apple Inc", "Microsoft Corp"]

    manifest_files = list((tmp_path / "silver-landing" / "manifests").rglob("run_manifest.json"))
    assert len(manifest_files) == 1
    manifest = json.loads(manifest_files[0].read_text())
    assert manifest["workflow_name"] == "backfill_silver_landing_historical"
    written_tables = {entry["table_name"] for entry in manifest["tables"]}
    assert "sec_adv_filing" in written_tables
    assert "sec_thirteenf_holding" in written_tables
    assert written_tables.issubset(set(_BACKFILL_TABLES))


def test_backfill_skips_empty_tables_gracefully(tmp_path, monkeypatch) -> None:
    """A shard with company rows but no former-name (or adv/13F) rows still
    flushes the tables that do have content -- write_landing_export already
    omits empty tables (its own documented behavior); this just proves the
    caller doesn't choke on that across the full widened table list."""
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

    result = run_silver_landing_historical_backfill(context, "backfill-run-2")

    assert result["source_counts"]["sec_company"] == 1
    assert result["source_counts"]["sec_company_former_name"] == 0
    assert result["source_counts"]["sec_adv_filing"] == 0
    assert "sec_company_former_name" not in result["landing_export"]
    assert "sec_adv_filing" not in result["landing_export"]
    assert result["landing_export"]["sec_company"] == 1
