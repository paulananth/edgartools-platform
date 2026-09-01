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

**Second, real bug found running the widened backfill live against prod
(2026-09-01):** the original implementation (a) hydrated from
`_hydrate_all_shards`, which reads the CIK-sharded `shard-*.duckdb` files
DuckDB Retirement Ticket 06 already retired as a write target -- live prod
still has these files sitting in S3, 12+ days stale, silently pointing this
backfill at stale data instead of the current canonical monolith
`silver.duckdb`; and (b) buffered every table's rows as Python dicts in
memory (`LandingExportBuffer`/`.fetch()`) before writing anything, which
OOM-killed a real prod run at 8192MB (the largest task profile available)
on `sec_thirteenf_holding` alone (~6.8M rows). Both fixed here: the module
now hydrates the current monolith directly, and streams each table straight
from DuckDB to a local Parquet file via `COPY (SELECT ...) TO ... (FORMAT
PARQUET)` -- which DuckDB executes internally without ever materializing
the result set as Python objects -- then uploads that file with
`StorageLocation.upload_file` (a real chunked stream, not an in-memory
buffer).

These tests build a real monolith DuckDB file (via SilverDatabase, not a
hand-rolled stub -- see CLAUDE.md's schema-drift lesson) at the exact local
path the streaming hydration step checks, and exercise the module against
it.
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


def _monolith_path(tmp_path):
    # Mirrors the exact relative layout _hydrate_silver_database_from_storage
    # downloads canonical silver.duckdb to -- context.silver_root.join(
    # "silver", "sec", "silver.duckdb") -- so the code under test finds it
    # already present and skips the (no-op-in-tests) hydration attempt.
    path = tmp_path / "silver" / "silver" / "sec" / "silver.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _seed_two_companies(path) -> None:
    db = SilverDatabase(str(path))
    for cik, name, accession in (
        (320193, "Apple Inc", "0000320193-26-000001"),
        (789019, "Microsoft Corp", "0000789019-26-000001"),
    ):
        db._conn.execute(
            "INSERT INTO sec_company (cik, entity_name, last_sync_run_id) VALUES (?, ?, 'seed')",
            [cik, name],
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
        # Two tables outside the original company-metadata-only scope,
        # proving the widened backfill actually reaches beyond it.
        db._conn.execute(
            "INSERT INTO sec_adv_filing (accession_number, cik, form, adviser_name, last_sync_run_id) "
            "VALUES (?, ?, 'ADV', ?, 'seed')",
            [accession, cik, name],
        )
        db._conn.execute(
            "INSERT INTO sec_thirteenf_holding "
            "(cik, accession_number, holding_index, period_of_report, issuer_name) "
            "VALUES (?, ?, 1, '2026-06-30', ?)",
            [cik, accession, name],
        )
    db.close()


def test_backfill_requires_landing_export_root(tmp_path) -> None:
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    context = _context(tmp_path, silver_landing_export_root=None)

    with pytest.raises(WarehouseRuntimeError, match="SILVER_LANDING_EXPORT_ROOT"):
        run_silver_landing_historical_backfill(context, "run-1")


def test_backfill_raises_when_no_monolith_found(tmp_path) -> None:
    """No silver.duckdb present anywhere (local storage_root, so hydration
    is a genuine no-op, not just untriggered) -- must fail loud, not
    silently proceed against nothing."""
    from edgar_warehouse.application.warehouse_orchestrator import WarehouseRuntimeError

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    with pytest.raises(WarehouseRuntimeError, match="No canonical silver.duckdb"):
        run_silver_landing_historical_backfill(context, "run-1")


def test_backfill_reads_the_current_monolith_not_a_stale_shard(tmp_path) -> None:
    """The actual bug this fix closes: the old implementation hydrated from
    the CIK-sharded shard-*.duckdb files DuckDB Retirement Ticket 06 already
    retired -- live prod still has stale (12+ day old) shard files sitting
    in S3 that would have silently been read instead of the current
    canonical monolith. Confirm the fixed code path reads the monolith path
    specifically: seed data only there, assert it round-trips, and confirm
    no shard-manifest/shard-*.duckdb lookup is attempted at all (no
    monkeypatch of _hydrate_all_shards is installed in this test -- if the
    code under test still called it, this test would fail with a real
    network/filesystem error, not silently pass)."""
    monolith = _monolith_path(tmp_path)
    _seed_two_companies(monolith)

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    result = run_silver_landing_historical_backfill(context, "backfill-run-monolith")

    assert result["source_counts"]["sec_company"] == 2
    assert result["landing_export"]["sec_company"] == 2


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


def test_backfill_streams_rows_and_flushes_to_landing_zone(tmp_path) -> None:
    monolith = _monolith_path(tmp_path)
    _seed_two_companies(monolith)

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    result = run_silver_landing_historical_backfill(context, "backfill-run-1")

    assert result["command"] == "backfill-silver-landing-historical"

    # The two seeded tables round-trip correctly...
    for table in ("sec_company", "sec_adv_filing", "sec_thirteenf_holding"):
        assert result["source_counts"][table] == 2, table
        assert result["landing_export"][table] == 2, table

    # ...and every other backfill table -- unseeded, genuinely empty in this
    # test monolith -- is present as a zero source count and correctly
    # absent from the landing_export payload, not a crash.
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


def test_backfill_skips_empty_tables_gracefully(tmp_path) -> None:
    """A monolith with company rows but no former-name (or adv/13F) rows
    still flushes the tables that do have content, and correctly omits
    genuinely-empty tables from both the manifest and the landing_export
    payload rather than writing a zero-row Parquet file for each of the
    ~24 unseeded tables."""
    monolith = _monolith_path(tmp_path)
    db = SilverDatabase(str(monolith))
    db._conn.execute(
        "INSERT INTO sec_company (cik, entity_name, last_sync_run_id) VALUES (320193, 'Apple Inc', 'seed')"
    )
    db.close()

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    result = run_silver_landing_historical_backfill(context, "backfill-run-2")

    assert result["source_counts"]["sec_company"] == 1
    assert result["source_counts"]["sec_company_former_name"] == 0
    assert result["source_counts"]["sec_adv_filing"] == 0
    assert "sec_company_former_name" not in result["landing_export"]
    assert "sec_adv_filing" not in result["landing_export"]
    assert result["landing_export"]["sec_company"] == 1

    # No Parquet file at all for a genuinely-empty table.
    empty_table_files = list((tmp_path / "silver-landing" / "sec_company_former_name").rglob("*.parquet"))
    assert empty_table_files == []


def test_backfill_never_materializes_a_full_table_as_python_rows(tmp_path, monkeypatch) -> None:
    """The actual OOM bug this fix closes: the old implementation called
    reader.fetch("SELECT * FROM {table}") per table, pulling the entire
    result set into a Python list of dicts before writing anything -- which
    OOM-killed a real prod run at 8192MB on a ~6.8M-row table alone. Prove
    the fixed code path never calls .fetch() with a bare "SELECT * FROM
    <table>" shape (only the bounded COUNT(*) probe) by asserting on every
    SQL string the reader's .fetch() actually receives during a real run."""
    monolith = _monolith_path(tmp_path)
    _seed_two_companies(monolith)

    landing_root = StorageLocation(str(tmp_path / "silver-landing"))
    context = _context(tmp_path, silver_landing_export_root=landing_root)

    from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader

    observed_fetch_sql: list[str] = []
    original_fetch = ShardedSilverReader.fetch

    def _tracking_fetch(self, sql, params=None):
        observed_fetch_sql.append(sql)
        return original_fetch(self, sql, params)

    monkeypatch.setattr(ShardedSilverReader, "fetch", _tracking_fetch)

    run_silver_landing_historical_backfill(context, "backfill-run-3")

    assert observed_fetch_sql, "expected at least one .fetch() call (the COUNT(*) probes)"
    for sql in observed_fetch_sql:
        assert "SELECT *" not in sql.upper(), (
            f"a bare SELECT * over a whole table was issued through .fetch() "
            f"(would materialize the full result set as Python dicts): {sql!r}"
        )
        assert "COUNT(*)" in sql.upper(), f"expected only bounded COUNT(*) probes through .fetch(): {sql!r}"
