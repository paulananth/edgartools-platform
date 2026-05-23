"""Wave 0 test scaffolds for Phase 9 silver storage sharding (STORE-01 through STORE-04).

These stubs define the four behavior contracts that later plans will implement.
Plans 02 and 04 convert them to passing tests.
"""

from __future__ import annotations

import pytest
import duckdb


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

DEV_MANIFEST = {
    "shard_count": 4,
    "schema_version": "1",
    "created_at": "2026-05-21T00:00:00Z",
    "bands": [
        {"shard_index": 0, "cik_min": 0, "cik_max": 1053917},
        {"shard_index": 1, "cik_min": 1053918, "cik_max": 1523562},
        {"shard_index": 2, "cik_min": 1523563, "cik_max": 1819990},
        {"shard_index": 3, "cik_min": 1819991, "cik_max": 9999999},
    ],
    "checksums": {"0": "abc", "1": "def", "2": "ghi", "3": "jkl"},
}


# ---------------------------------------------------------------------------
# STORE-01: shard file size limit (Plan 04 implements)
# ---------------------------------------------------------------------------


def test_shard_file_size_within_limit(tmp_path) -> None:
    """STORE-01: each shard DuckDB file is at most 200 MB after migration."""
    from edgar_warehouse.application.commands.migrate_silver_shards import run_migration
    from edgar_warehouse.silver_store import SilverDatabase

    # Build a tiny synthetic monolith with full schema
    monolith_path = tmp_path / "silver.duckdb"
    db = SilverDatabase(str(monolith_path))
    conn = db._conn
    conn.execute("INSERT INTO sec_company (cik, entity_name) VALUES (500000, 'TinyComp')")
    db.close()

    output_dir = tmp_path / "shards"
    output_dir.mkdir()

    bands = [
        {"shard_index": 0, "cik_min": 0, "cik_max": 1053917},
        {"shard_index": 1, "cik_min": 1053918, "cik_max": 1523562},
        {"shard_index": 2, "cik_min": 1523563, "cik_max": 1819990},
        {"shard_index": 3, "cik_min": 1819991, "cik_max": 9999999},
    ]
    run_migration(str(monolith_path), str(output_dir), bands)

    max_size = 200 * 1024 * 1024  # 200 MB
    for i in range(4):
        shard_file = output_dir / f"shard-{i}.duckdb"
        assert shard_file.exists(), f"shard-{i}.duckdb not found"
        size = shard_file.stat().st_size
        assert size < max_size, f"shard-{i}.duckdb is {size} bytes, exceeds 200 MB limit"


# ---------------------------------------------------------------------------
# STORE-02: overlapping shard hydration (Plan 02 implements)
# ---------------------------------------------------------------------------


def test_hydrate_downloads_only_overlapping_shard() -> None:
    """STORE-02: bootstrap task downloads only the shard(s) whose CIK band overlaps its window."""
    from unittest.mock import MagicMock, patch

    from edgar_warehouse.application.warehouse_orchestrator import _hydrate_shard_for_window

    # Build a minimal context with remote storage and local silver root
    storage_root = MagicMock()
    storage_root.is_remote = True
    storage_root.join.side_effect = lambda *parts: "s3://bucket/" + "/".join(parts)

    silver_root = MagicMock()
    silver_root.is_remote = False
    silver_root.join.side_effect = lambda *parts: "/tmp/silver/" + "/".join(parts)

    context = MagicMock()
    context.storage_root = storage_root
    context.silver_root = silver_root

    fake_bytes = b"fake-shard-content"

    with patch(
        "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
        return_value=fake_bytes,
    ) as mock_read:
        result = _hydrate_shard_for_window(context, shard_index=1)

    # Must have called read_bytes exactly once
    assert mock_read.call_count == 1
    # The path used must reference shard-1.duckdb, not shard-0.duckdb or silver.duckdb
    called_path: str = mock_read.call_args[0][0]
    assert "shard-1.duckdb" in called_path, f"Expected shard-1.duckdb in path, got: {called_path}"
    assert "shard-0.duckdb" not in called_path
    assert "silver.duckdb" not in called_path


# ---------------------------------------------------------------------------
# STORE-03: deterministic band resolution (Plan 02 implements)
# ---------------------------------------------------------------------------


def test_band_resolution_is_deterministic() -> None:
    """STORE-03: same CIK always maps to same shard regardless of input ordering."""
    from edgar_warehouse.application.sharding.shard_manifest import band_for_cik, shards_for_window

    manifest = DEV_MANIFEST

    # Point lookups: boundary ownership
    assert band_for_cik(manifest, 1053917) == 0
    assert band_for_cik(manifest, 1053918) == 1

    # Window crossing shard-2/shard-3 boundary
    assert shards_for_window(manifest, 1_800_000, 1_900_000) == [2, 3]

    # Determinism: calling twice returns identical results
    first = shards_for_window(manifest, 1_800_000, 1_900_000)
    second = shards_for_window(manifest, 1_800_000, 1_900_000)
    assert first == second


# ---------------------------------------------------------------------------
# STORE-04: migration row count parity (Plan 04 implements)
# ---------------------------------------------------------------------------


def test_migration_row_counts_match_monolith(tmp_path) -> None:
    """STORE-04: per-table row counts across all shards equal the monolith totals after migration.

    Uses a synthetic monolith with:
    - 8 sec_company rows spanning all 4 CIK bands
    - 2 sec_company_filing rows (to support accession-join routing)
    - 1 sec_ownership_reporting_owner row whose owner_cik is in shard-3 but
      whose issuer cik (via sec_company_filing) is in shard-1 (critical routing test)
    - 1 global row in sec_sync_run (should appear in all 4 shards)
    """
    import duckdb as _duckdb

    from edgar_warehouse.application.commands.migrate_silver_shards import run_migration
    from edgar_warehouse.silver_store import SilverDatabase

    # Build synthetic monolith with full schema
    monolith_path = tmp_path / "silver.duckdb"
    db = SilverDatabase(str(monolith_path))
    conn = db._conn

    # 8 sec_company rows, 2 per CIK band
    companies = [
        (100000, "Alpha"),
        (500000, "Beta"),         # shard-0 (0–1053917)
        (1100000, "Gamma"),
        (1400000, "Delta"),       # shard-1 (1053918–1523562)
        (1600000, "Epsilon"),
        (1700000, "Zeta"),        # shard-2 (1523563–1819990)
        (2000000, "Eta"),
        (2100000, "Theta"),       # shard-3 (1819991–9999999)
    ]
    for cik, name in companies:
        conn.execute(
            "INSERT INTO sec_company (cik, entity_name) VALUES (?, ?)", [cik, name]
        )

    # 2 sec_company_filing rows with issuer CIKs in shard-1 and shard-3
    conn.execute(
        """
        INSERT INTO sec_company_filing
            (cik, accession_number, form, filing_date, report_date)
        VALUES
            (1100000, '0000001100000-26-000001', '4', '2026-01-01', '2026-01-01'),
            (2000000, '0000002000000-26-000001', '4', '2026-01-01', '2026-01-01')
        """
    )

    # sec_ownership_reporting_owner: owner_cik is in shard-3 (2000000), but
    # accession maps to issuer cik 1100000 (shard-1). Row MUST land in shard-1.
    conn.execute(
        """
        INSERT INTO sec_ownership_reporting_owner
            (accession_number, owner_index, owner_cik, owner_name, is_director, is_officer,
             is_ten_percent_owner, is_other)
        VALUES ('0000001100000-26-000001', 0, 2000000, 'Insider Person', 1, 0, 0, 0)
        """
    )

    # 1 global sec_sync_run row (should be replicated to all 4 shards)
    conn.execute(
        """
        INSERT INTO sec_sync_run
            (sync_run_id, sync_mode, scope_type, started_at, status)
        VALUES ('run-test-001', 'bootstrap', 'full', CURRENT_TIMESTAMP, 'succeeded')
        """
    )

    db.close()

    bands = [
        {"shard_index": 0, "cik_min": 0, "cik_max": 1053917},
        {"shard_index": 1, "cik_min": 1053918, "cik_max": 1523562},
        {"shard_index": 2, "cik_min": 1523563, "cik_max": 1819990},
        {"shard_index": 3, "cik_min": 1819991, "cik_max": 9999999},
    ]

    output_dir = tmp_path / "shards"
    output_dir.mkdir()
    run_migration(str(monolith_path), str(output_dir), bands)

    # --- Verification ---
    # 1. Total sec_company rows across shards == 8
    total_company_rows = 0
    for i in range(4):
        sc = _duckdb.connect(str(output_dir / f"shard-{i}.duckdb"), read_only=True)
        count = sc.execute("SELECT COUNT(*) FROM sec_company").fetchone()[0]
        total_company_rows += count
        sc.close()

    assert total_company_rows == 8, (
        f"Expected 8 sec_company rows across shards, got {total_company_rows}"
    )

    # 2. Each shard only contains sec_company rows in its CIK band
    for i, band in enumerate(bands):
        sc = _duckdb.connect(str(output_dir / f"shard-{i}.duckdb"), read_only=True)
        out_of_band = sc.execute(
            "SELECT COUNT(*) FROM sec_company WHERE cik < ? OR cik > ?",
            [band["cik_min"], band["cik_max"]],
        ).fetchone()[0]
        sc.close()
        assert out_of_band == 0, (
            f"shard-{i} has {out_of_band} rows outside its band {band}"
        )

    # 3. CRITICAL: sec_ownership_reporting_owner row must be in shard-1 (issuer cik=1100000),
    #    NOT in shard-3 (owner_cik=2000000). This validates that we route by issuer, not owner.
    shard1 = _duckdb.connect(str(output_dir / "shard-1.duckdb"), read_only=True)
    ownership_in_shard1 = shard1.execute(
        "SELECT COUNT(*) FROM sec_ownership_reporting_owner"
    ).fetchone()[0]
    shard1.close()
    assert ownership_in_shard1 == 1, (
        f"Expected ownership row in shard-1 (issuer shard), got {ownership_in_shard1}. "
        "This indicates routing by owner_cik instead of issuer cik."
    )

    shard3 = _duckdb.connect(str(output_dir / "shard-3.duckdb"), read_only=True)
    ownership_in_shard3 = shard3.execute(
        "SELECT COUNT(*) FROM sec_ownership_reporting_owner"
    ).fetchone()[0]
    shard3.close()
    assert ownership_in_shard3 == 0, (
        f"Found ownership row in shard-3 (owner_cik shard), expected 0. "
        "This indicates routing by owner_cik instead of issuer cik."
    )

    # 4. Global sec_sync_run row replicated to ALL 4 shards
    for i in range(4):
        sc = _duckdb.connect(str(output_dir / f"shard-{i}.duckdb"), read_only=True)
        sync_count = sc.execute("SELECT COUNT(*) FROM sec_sync_run").fetchone()[0]
        sc.close()
        assert sync_count == 1, (
            f"Expected sec_sync_run replicated to shard-{i}, got {sync_count} rows"
        )

    # 5. shard-manifest.json must exist
    manifest_path = output_dir / "shard-manifest.json"
    assert manifest_path.exists(), "shard-manifest.json not written"


# ---------------------------------------------------------------------------
# Plan 03: Wire bootstrap chunk path to shard-aware hydrate (STORE-02)
# ---------------------------------------------------------------------------


def test_bootstrap_chunk_uses_shard_aware_hydrate() -> None:
    """STORE-02: _execute_warehouse_bronze_capture picks the shard-aware hydrate path
    (not _hydrate_silver_database_from_storage) for bootstrap-batch with remote storage."""
    import json
    from unittest.mock import MagicMock, call, patch

    from edgar_warehouse.application.warehouse_orchestrator import (
        _execute_warehouse_bronze_capture,
    )

    # CIKs for this chunk: both fall in shard-1 (1053918–1523562 per DEV_MANIFEST)
    chunk_ciks = [1_100_000, 1_200_000]

    # Remote storage root
    storage_root = MagicMock()
    storage_root.is_remote = True
    storage_root.root = "s3://bucket"
    storage_root.join.side_effect = lambda *parts: "s3://bucket/" + "/".join(parts)

    # Local silver root
    silver_root = MagicMock()
    silver_root.is_remote = False
    silver_root.join.side_effect = lambda *parts: "/tmp/silver/" + "/".join(parts)

    context = MagicMock()
    context.storage_root = storage_root
    context.silver_root = silver_root
    context.snowflake_export_root = None  # no gold build for bootstrap-batch
    context.runtime_mode = "bronze_capture"
    context.environment_name = "test"

    manifest_bytes = json.dumps(DEV_MANIFEST).encode()
    local_shard_path = "/tmp/silver/sec/shards/shard-1.duckdb"

    # Patch everything that touches external I/O
    with (
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.read_bytes",
            side_effect=[manifest_bytes, b"shard-content"],
        ) as mock_read_bytes,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._hydrate_silver_database_from_storage",
        ) as mock_monolith_hydrate,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator.open_silver_shard",
        ) as mock_open_shard,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_shard_if_remote",
            return_value=None,
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._publish_silver_database_if_remote",
        ) as mock_monolith_publish,
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._capture_bronze_raw",
            return_value=([], {"rows_inserted": 0, "rows_skipped": 0, "sync_status": "succeeded"}),
        ),
        patch(
            "edgar_warehouse.application.warehouse_orchestrator._planned_writes",
            return_value={},
        ),
        patch("edgar_warehouse.application.warehouse_orchestrator._emit_pipeline_event"),
        patch("edgar_warehouse.application.warehouse_orchestrator._resolve_run_id", return_value="run-1"),
    ):
        # open_silver_shard must return a mock DB with all SilverDatabase methods
        mock_db = MagicMock()
        mock_db.get_table_counts.return_value = {}
        mock_open_shard.return_value = mock_db

        _execute_warehouse_bronze_capture(
            context=context,
            command_name="bootstrap-batch",
            arguments={"cik_list": chunk_ciks},
        )

    # Monolith hydrate must NOT have been called
    mock_monolith_hydrate.assert_not_called()
    # Monolith publish must NOT have been called
    mock_monolith_publish.assert_not_called()
    # open_silver_shard was called (shard path, not monolith)
    mock_open_shard.assert_called_once()
    called_path: str = mock_open_shard.call_args[0][0]
    assert "shard-" in called_path, f"Expected shard path, got: {called_path}"
    assert "silver.duckdb" not in called_path, (
        f"Expected shard path (not monolith), got: {called_path}"
    )


# ---------------------------------------------------------------------------
# Plan 03: ShardedSilverReader multi-shard ATTACH union (Plan 03 implements)
# ---------------------------------------------------------------------------


def test_sharded_silver_reader_unions_shards(tmp_path) -> None:
    """ShardedSilverReader ATTACHes two shard files and exposes a UNION ALL view over sec_company."""
    from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader
    from edgar_warehouse.silver_support.access import get_connection

    # Create two minimal shard DuckDB files with a sec_company table
    shard0 = tmp_path / "shard-0.duckdb"
    shard1 = tmp_path / "shard-1.duckdb"

    conn0 = duckdb.connect(str(shard0))
    conn0.execute("CREATE TABLE sec_company (cik INT, company_name TEXT)")
    conn0.execute("INSERT INTO sec_company VALUES (1, 'Alpha')")
    conn0.close()

    conn1 = duckdb.connect(str(shard1))
    conn1.execute("CREATE TABLE sec_company (cik INT, company_name TEXT)")
    conn1.execute("INSERT INTO sec_company VALUES (2, 'Beta')")
    conn1.close()

    # Construct ShardedSilverReader — both shard connections are closed above
    reader = ShardedSilverReader([str(shard0), str(shard1)])

    try:
        # get_connection() must return the in-memory DuckDB connection via duck typing
        conn = get_connection(reader)
        rows = conn.execute("SELECT cik FROM sec_company ORDER BY cik").fetchall()
        assert rows == [(1,), (2,)], f"Expected [(1,), (2,)], got: {rows}"
    finally:
        reader.close()
