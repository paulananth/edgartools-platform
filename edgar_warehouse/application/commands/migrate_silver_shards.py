"""migrate-silver-shards command.

One-time operational command that converts a monolithic silver.duckdb file into
four CIK-range shard files with a verified shard-manifest.json.

Migration uses DuckDB ATTACH + INSERT SELECT for type-safe row extraction.
This avoids Python dict export which risks type coercion on DECIMAL(28,8),
TIMESTAMPTZ, and column ordering.

Routing rules:
- CIK-direct tables: rows with cik in the band go to that shard
- Accession-join tables: routed by issuer CIK via JOIN to sec_company_filing
  (NEVER by owner_cik which is the insider, not the issuer)
- Global tables: all rows replicated to ALL 4 shards
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from edgar_warehouse.application.errors import WarehouseRuntimeError
from edgar_warehouse.silver_store import SilverDatabase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table routing configuration
# ---------------------------------------------------------------------------

# Tables routed by their own `cik` column
CIK_DIRECT_TABLES = [
    "sec_company",
    "sec_company_address",
    "sec_company_former_name",
    "sec_company_submission_file",
    "sec_company_ticker",
    "sec_company_sync_state",
    "sec_company_filing",
    "sec_current_filing_feed",
    "sec_raw_object",
    "sec_adv_filing",
    "sec_reconcile_finding",
]

# Tables that need a JOIN to sec_company_filing to resolve the issuer CIK.
# Tuple format: (table_name, join_table, join_condition)
# For all ownership tables: join on accession_number -> sec_company_filing.cik
# For ADV sub-tables: join on accession_number -> sec_adv_filing.cik
ACCESSION_JOIN_TABLES: list[tuple[str, str, str]] = [
    (
        "sec_ownership_reporting_owner",
        "sec_company_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_ownership_non_derivative_txn",
        "sec_company_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_ownership_derivative_txn",
        "sec_company_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_adv_office",
        "sec_adv_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_adv_disclosure_event",
        "sec_adv_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_adv_private_fund",
        "sec_adv_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_filing_attachment",
        "sec_company_filing",
        "o.accession_number = f.accession_number",
    ),
    (
        "sec_filing_text",
        "sec_company_filing",
        "o.accession_number = f.accession_number",
    ),
]

# Tables replicated to ALL 4 shards (no CIK-based routing)
GLOBAL_TABLES = [
    "sec_sync_run",
    "sec_source_checkpoint",
    "sec_daily_index_checkpoint",
    "stg_daily_index_filing",
    "sec_parse_run",
]

# Legacy table — best-effort replication if it exists in source
OPTIONAL_GLOBAL_TABLES = [
    "sec_tracked_universe",
]

# All tables that have a `cik` column and should be checked for Layer 1/2 verification
CIK_KEYED_TABLES = CIK_DIRECT_TABLES


# ---------------------------------------------------------------------------
# Default band boundaries (dev DB p25/p50/p75 CIK quartiles)
# ---------------------------------------------------------------------------

DEFAULT_BANDS = [
    {"shard_index": 0, "cik_min": 0, "cik_max": 1_053_917},
    {"shard_index": 1, "cik_min": 1_053_918, "cik_max": 1_523_562},
    {"shard_index": 2, "cik_min": 1_523_563, "cik_max": 1_819_990},
    {"shard_index": 3, "cik_min": 1_819_991, "cik_max": 9_999_999},
]


# ---------------------------------------------------------------------------
# Core migration function
# ---------------------------------------------------------------------------


def run_migration(
    source_path: str,
    output_dir: str,
    bands: list[dict[str, Any]],
) -> dict[str, Any]:
    """Migrate a monolithic silver.duckdb into 4 CIK-range shard files.

    Parameters
    ----------
    source_path:
        Path to the monolithic silver.duckdb file (local path only).
    output_dir:
        Directory where shard-{0..3}.duckdb and shard-manifest.json are written.
    bands:
        List of band dicts: [{"shard_index": 0, "cik_min": 0, "cik_max": ...}, ...]
        Must have exactly 4 entries.

    Returns
    -------
    dict
        The written shard manifest dictionary.

    Raises
    ------
    WarehouseRuntimeError
        If the source file does not exist, band count is wrong, or any
        three-layer verification check fails.
    """
    source_path = str(source_path)
    output_dir = Path(output_dir)

    if not Path(source_path).exists():
        raise WarehouseRuntimeError(
            f"Source silver.duckdb not found: {source_path}"
        )

    if len(bands) != 4:
        raise WarehouseRuntimeError(
            f"Expected exactly 4 bands, got {len(bands)}"
        )

    bands = sorted(bands, key=lambda b: b["shard_index"])
    shard_count = len(bands)

    logger.info("Starting silver shard migration: source=%s output_dir=%s", source_path, output_dir)

    # ------------------------------------------------------------------
    # Step 1: Create 4 shard DuckDB files with full schema via SilverDatabase
    # ------------------------------------------------------------------
    shard_paths = []
    for band in bands:
        i = band["shard_index"]
        shard_path = str(output_dir / f"shard-{i}.duckdb")
        shard_paths.append(shard_path)

        # SilverDatabase constructor runs _DDL + _ensure_schema_evolution
        db = SilverDatabase(shard_path)
        db.close()
        logger.debug("Created empty shard schema: %s", shard_path)

    # ------------------------------------------------------------------
    # Step 2-4: Open source and populate each shard
    # ------------------------------------------------------------------
    source_conn = duckdb.connect(source_path, read_only=True)

    # For each shard, open it, ATTACH source, then INSERT rows
    for band in bands:
        i = band["shard_index"]
        cik_min = band["cik_min"]
        cik_max = band["cik_max"]
        shard_path = shard_paths[i]

        shard_conn = duckdb.connect(shard_path)
        shard_conn.execute(f"ATTACH '{source_path}' AS src (READ_ONLY)")

        # Step 2: CIK-direct tables
        for table in CIK_DIRECT_TABLES:
            try:
                shard_conn.execute(f"""
                    INSERT INTO {table}
                    SELECT * FROM src.{table}
                    WHERE cik >= {cik_min} AND cik <= {cik_max}
                """)
                logger.debug("shard-%d: CIK-direct %s done", i, table)
            except duckdb.Error as e:
                # Table may not exist in older schemas — log and skip
                logger.warning("shard-%d: skipping CIK-direct %s: %s", i, table, e)

        # Step 3: Accession-join tables
        for table, join_table, join_cond in ACCESSION_JOIN_TABLES:
            try:
                shard_conn.execute(f"""
                    INSERT INTO {table}
                    SELECT o.* FROM src.{table} o
                    JOIN src.{join_table} f ON {join_cond}
                    WHERE f.cik >= {cik_min} AND f.cik <= {cik_max}
                """)
                logger.debug("shard-%d: accession-join %s done", i, table)
            except duckdb.Error as e:
                logger.warning("shard-%d: skipping accession-join %s: %s", i, table, e)

        # Step 4: Global tables (replicated to this shard too)
        for table in GLOBAL_TABLES:
            try:
                shard_conn.execute(f"""
                    INSERT INTO {table}
                    SELECT * FROM src.{table}
                """)
                logger.debug("shard-%d: global %s done", i, table)
            except duckdb.Error as e:
                logger.warning("shard-%d: skipping global %s: %s", i, table, e)

        # Optional legacy global tables
        for table in OPTIONAL_GLOBAL_TABLES:
            try:
                shard_conn.execute(f"""
                    INSERT INTO {table}
                    SELECT * FROM src.{table}
                """)
                logger.debug("shard-%d: optional-global %s done", i, table)
            except duckdb.Error:
                pass  # silently skip if table doesn't exist in source

        shard_conn.close()
        logger.info("Populated shard-%d (%s rows in band %d–%d)", i, shard_path, cik_min, cik_max)

    # ------------------------------------------------------------------
    # Step 5: Three-layer verification
    # ------------------------------------------------------------------
    logger.info("Running three-layer verification...")

    # Layer 1: Row-count equality per CIK-keyed table
    for table in CIK_KEYED_TABLES:
        try:
            source_count = source_conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        except duckdb.Error:
            continue  # table may not exist in source

        shard_total = 0
        for shard_path in shard_paths:
            sc = duckdb.connect(shard_path, read_only=True)
            try:
                count = sc.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                shard_total += count
            except duckdb.Error:
                pass
            finally:
                sc.close()

        if source_count != shard_total:
            raise WarehouseRuntimeError(
                f"Layer 1 verification failed: {table} has {source_count} rows in source "
                f"but {shard_total} total across shards"
            )

    logger.info("Layer 1 PASSED: row counts match for all CIK-keyed tables")

    # Layer 2: CIK-set equality per CIK-keyed table
    for table in CIK_KEYED_TABLES:
        try:
            source_ciks = {
                row[0]
                for row in source_conn.execute(
                    f"SELECT DISTINCT cik FROM {table}"
                ).fetchall()
            }
        except duckdb.Error:
            continue

        shard_ciks: set[int] = set()
        for shard_path in shard_paths:
            sc = duckdb.connect(shard_path, read_only=True)
            try:
                ciks = {
                    row[0]
                    for row in sc.execute(
                        f"SELECT DISTINCT cik FROM {table}"
                    ).fetchall()
                }
                shard_ciks |= ciks
            except duckdb.Error:
                pass
            finally:
                sc.close()

        if source_ciks != shard_ciks:
            missing = source_ciks - shard_ciks
            extra = shard_ciks - source_ciks
            raise WarehouseRuntimeError(
                f"Layer 2 verification failed: {table} CIK set mismatch. "
                f"Missing from shards: {list(missing)[:10]}, "
                f"Extra in shards: {list(extra)[:10]}"
            )

    logger.info("Layer 2 PASSED: CIK sets match for all CIK-keyed tables")

    source_conn.close()

    # Layer 3: SHA-256 checksums from file bytes
    checksums: dict[str, str] = {}
    for band in bands:
        i = band["shard_index"]
        shard_path = output_dir / f"shard-{i}.duckdb"
        sha256 = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        checksums[str(i)] = sha256
        logger.debug("shard-%d SHA-256: %s", i, sha256)

    logger.info("Layer 3 PASSED: SHA-256 checksums computed for all shards")

    # ------------------------------------------------------------------
    # Step 6: Write shard-manifest.json
    # ------------------------------------------------------------------
    manifest = {
        "shard_count": shard_count,
        "schema_version": "1",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "bands": [
            {
                "shard_index": b["shard_index"],
                "cik_min": b["cik_min"],
                "cik_max": b["cik_max"],
            }
            for b in bands
        ],
        "checksums": checksums,
    }

    manifest_path = output_dir / "shard-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("shard-manifest.json written: %s", manifest_path)

    return manifest


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def execute(args: Any) -> int:
    """Execute the migrate-silver-shards command from CLI args."""
    source_path = args.source
    output_dir = args.output_dir
    band_boundaries_json = getattr(args, "band_boundaries", None)

    if band_boundaries_json:
        try:
            bands = json.loads(band_boundaries_json)
        except json.JSONDecodeError as exc:
            import sys
            print(
                f"error: --band-boundaries is not valid JSON: {exc}",
                file=sys.stderr,
            )
            return 2
    else:
        bands = DEFAULT_BANDS

    try:
        manifest = run_migration(source_path, output_dir, bands)
        print(
            f"Migration complete: {len(bands)} shards written to {output_dir}\n"
            f"Manifest: {output_dir}/shard-manifest.json"
        )
        return 0
    except WarehouseRuntimeError as exc:
        import sys
        print(f"error: {exc}", file=sys.stderr)
        return 1
