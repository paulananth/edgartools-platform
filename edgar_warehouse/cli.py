"""CLI surface for warehouse operations."""

from __future__ import annotations

import argparse

from edgar_warehouse.runtime import run_command


def _parse_cik_list(value: str) -> list[int]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise argparse.ArgumentTypeError("expected at least one CIK")
    try:
        return [int(item) for item in items]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("CIKs must be comma-separated integers") from exc


def _parse_adv_artifact(value: str) -> dict[str, object]:
    parts = [part.strip() for part in value.split(",", 3)]
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError("expected ACCESSION,FORM,STORAGE_PATH[,CIK]")

    accession_number, form, storage_path = parts[:3]
    if not accession_number:
        raise argparse.ArgumentTypeError("artifact accession number is required")
    if not form:
        raise argparse.ArgumentTypeError("artifact form is required")
    if not storage_path:
        raise argparse.ArgumentTypeError("artifact storage path is required")

    artifact: dict[str, object] = {
        "accession_number": accession_number,
        "form": form,
        "storage_path": storage_path,
    }
    if len(parts) == 4 and parts[3]:
        try:
            artifact["cik"] = int(parts[3])
        except ValueError as exc:
            raise argparse.ArgumentTypeError("artifact CIK must be an integer") from exc
    return artifact


def _add_common_bootstrap_args(parser: argparse.ArgumentParser, include_recent_limit: bool) -> None:
    parser.add_argument("--cik-list", type=_parse_cik_list, help="Comma-separated CIK list")
    parser.add_argument(
        "--tracking-status-filter",
        default="active",
        help="Tracked universe status filter",
    )
    parser.add_argument(
        "--include-reference-refresh",
        dest="include_reference_refresh",
        action="store_true",
        default=True,
        help="Refresh SEC reference files before loading",
    )
    parser.add_argument(
        "--no-include-reference-refresh",
        dest="include_reference_refresh",
        action="store_false",
        help="Skip SEC reference refresh",
    )
    if include_recent_limit:
        parser.add_argument(
            "--recent-limit",
            type=int,
            default=10,
            help="Maximum number of recent filings to include per company",
        )
    parser.add_argument(
        "--artifact-policy",
        default="all_attachments",
        help="Artifact fetch policy",
    )
    parser.add_argument(
        "--parser-policy",
        default="configured_forms",
        help="Parser execution policy",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-fetch and rebuild of the selected scope",
    )
    parser.add_argument(
        "--cik-limit",
        type=int,
        default=None,
        help="Window size for CIK chunking (number of CIKs to process); None = no limit",
    )
    parser.add_argument(
        "--cik-offset",
        type=int,
        default=0,
        help="0-based offset into the ordered CIK list for windowed chunking",
    )


def _add_run_id_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--run-id",
        help="Optional stable workflow run identifier passed by the orchestrator",
    )


def _handle_bootstrap_full(args: argparse.Namespace) -> int:
    return run_command("bootstrap-full", args)


def _handle_bootstrap(args: argparse.Namespace) -> int:
    return run_command("bootstrap", args)


def _handle_daily_incremental(args: argparse.Namespace) -> int:
    return run_command("daily-incremental", args)


def _handle_load_daily_form_index_for_date(args: argparse.Namespace) -> int:
    return run_command("load-daily-form-index-for-date", args)


def _handle_catch_up_daily_form_index(args: argparse.Namespace) -> int:
    return run_command("catch-up-daily-form-index", args)


def _handle_targeted_resync(args: argparse.Namespace) -> int:
    return run_command("targeted-resync", args)


def _handle_full_reconcile(args: argparse.Namespace) -> int:
    return run_command("full-reconcile", args)


def _handle_seed_universe(args: argparse.Namespace) -> int:
    return run_command("seed-universe", args)


def _handle_bootstrap_batch(args: argparse.Namespace) -> int:
    return run_command("bootstrap-batch", args)


def _handle_ingest_relationship_sources(args: argparse.Namespace) -> int:
    return run_command("ingest-relationship-sources", args)


def _handle_bootstrap_next(args: argparse.Namespace) -> int:
    return run_command("bootstrap-next", args)


def _handle_gold_refresh(args: argparse.Namespace) -> int:
    return run_command("gold-refresh", args)


def _handle_compute_windows(args: argparse.Namespace) -> int:
    if getattr(args, "window_size", None) is not None and args.window_size <= 0:
        import sys
        print(f"error: --window-size must be a positive integer, got {args.window_size}", file=sys.stderr)
        return 2
    total_cik_limit = getattr(args, "total_cik_limit", None)
    # 0 is a valid sentinel meaning "no limit" (matches the Step Functions default-injection
    # contract in write_load_history_definition, where an omitted $.total_cik_limit is
    # defaulted to 0 before ComputeWindows always receives an explicit --total-cik-limit
    # value). Only negative values are rejected.
    if total_cik_limit is not None and total_cik_limit < 0:
        import sys
        print(f"error: --total-cik-limit must be a non-negative integer, got {total_cik_limit}", file=sys.stderr)
        return 2
    return run_command("compute-windows", args)


def _handle_write_run_summary(args: argparse.Namespace) -> int:
    return run_command("write-run-summary", args)


def _handle_seed_silver_batches(args: argparse.Namespace) -> int:
    return run_command("seed-silver-batches", args)


def _handle_seed_bronze_batches(args: argparse.Namespace) -> int:
    return run_command("seed-bronze-batches", args)


def _handle_parse_ownership_bronze(args: argparse.Namespace) -> int:
    return run_command("parse-ownership-bronze", args)


def _handle_parse_adv_bronze(args: argparse.Namespace) -> int:
    return run_command("parse-adv-bronze", args)


def _handle_migrate_silver_shards(args: argparse.Namespace) -> int:
    return run_command("migrate-silver-shards", args)


def _handle_bootstrap_fundamentals(args: argparse.Namespace) -> int:
    return run_command("bootstrap-fundamentals", args)


def _handle_verify_pipeline_run(args: argparse.Namespace) -> int:
    return run_command("verify-pipeline-run", args)


def _handle_validate_data_quality(args: argparse.Namespace) -> int:
    return run_command("validate-data-quality", args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-warehouse",
        description="Warehouse operations for SEC EDGAR bronze, silver, and gold layers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_full = subparsers.add_parser(
        "bootstrap-full",
        help="Load full filing history for tracked companies.",
    )
    _add_common_bootstrap_args(bootstrap_full, include_recent_limit=False)
    _add_run_id_arg(bootstrap_full)
    bootstrap_full.set_defaults(handler=_handle_bootstrap_full)

    bootstrap = subparsers.add_parser(
        "bootstrap",
        help="Load only the most recent filings for tracked companies.",
    )
    _add_common_bootstrap_args(bootstrap, include_recent_limit=True)
    _add_run_id_arg(bootstrap)
    bootstrap.set_defaults(handler=_handle_bootstrap)

    daily_incremental = subparsers.add_parser(
        "daily-incremental",
        help="Load impacted company scope from SEC daily form indexes.",
    )
    daily_incremental.add_argument("--start-date", help="Inclusive start business date in YYYY-MM-DD format")
    daily_incremental.add_argument("--end-date", help="Inclusive end business date in YYYY-MM-DD format")
    daily_incremental.add_argument(
        "--include-reference-refresh",
        dest="include_reference_refresh",
        action="store_true",
        default=False,
        help="Refresh SEC reference files before loading",
    )
    daily_incremental.add_argument(
        "--tracking-status-filter",
        default="active",
        help="Tracked universe status filter",
    )
    daily_incremental.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-fetch and rebuild of the selected date range",
    )
    daily_incremental.add_argument(
        "--cik-limit",
        type=int,
        default=None,
        help="Window size for CIK chunking (number of CIKs to process); None = no limit",
    )
    daily_incremental.add_argument(
        "--cik-offset",
        type=int,
        default=0,
        help="0-based offset into the ordered CIK list for windowed chunking",
    )
    _add_run_id_arg(daily_incremental)
    daily_incremental.set_defaults(handler=_handle_daily_incremental)

    daily_index_for_date = subparsers.add_parser(
        "load-daily-form-index-for-date",
        help="Load one SEC daily form index by business date.",
    )
    daily_index_for_date.add_argument("target_date", help="Business date in YYYY-MM-DD format")
    daily_index_for_date.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force a refetch even if the checkpoint already exists",
    )
    _add_run_id_arg(daily_index_for_date)
    daily_index_for_date.set_defaults(handler=_handle_load_daily_form_index_for_date)

    catch_up_daily = subparsers.add_parser(
        "catch-up-daily-form-index",
        help="Load missing SEC daily form indexes up to an optional end date.",
    )
    catch_up_daily.add_argument("--end-date", help="Inclusive end business date in YYYY-MM-DD format")
    catch_up_daily.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force refetch for already-loaded business dates",
    )
    _add_run_id_arg(catch_up_daily)
    catch_up_daily.set_defaults(handler=_handle_catch_up_daily_form_index)

    targeted_resync = subparsers.add_parser(
        "targeted-resync",
        help="Refresh one reference, CIK, or accession scope.",
    )
    targeted_resync.add_argument(
        "--scope-type",
        choices=["reference", "cik", "accession"],
        required=True,
        help="Scope type to refresh",
    )
    targeted_resync.add_argument("--scope-key", required=True, help="Reference name, CIK, or accession number")
    targeted_resync.add_argument(
        "--include-artifacts",
        dest="include_artifacts",
        action="store_true",
        default=True,
        help="Refresh filing artifacts",
    )
    targeted_resync.add_argument(
        "--no-include-artifacts",
        dest="include_artifacts",
        action="store_false",
        help="Skip artifact refresh",
    )
    targeted_resync.add_argument(
        "--include-text",
        dest="include_text",
        action="store_true",
        default=True,
        help="Refresh extracted text artifacts",
    )
    targeted_resync.add_argument(
        "--no-include-text",
        dest="include_text",
        action="store_false",
        help="Skip text refresh",
    )
    targeted_resync.add_argument(
        "--include-parsers",
        dest="include_parsers",
        action="store_true",
        default=True,
        help="Re-run configured parsers",
    )
    targeted_resync.add_argument(
        "--no-include-parsers",
        dest="include_parsers",
        action="store_false",
        help="Skip parser execution",
    )
    targeted_resync.add_argument(
        "--force",
        dest="force",
        action="store_true",
        default=False,
        help="Force re-fetch even if the selected SEC files are already loaded",
    )
    targeted_resync.add_argument(
        "--no-force",
        dest="force",
        action="store_false",
        help="Deprecated no-op; targeted resync skips already loaded SEC files by default",
    )
    _add_run_id_arg(targeted_resync)
    targeted_resync.set_defaults(handler=_handle_targeted_resync)

    full_reconcile = subparsers.add_parser(
        "full-reconcile",
        help="Compare live SEC truth to warehouse state and optionally auto-heal drift.",
    )
    full_reconcile.add_argument("--cik-list", type=_parse_cik_list, help="Comma-separated CIK list")
    full_reconcile.add_argument("--sample-limit", type=int, help="Limit the number of tracked companies")
    full_reconcile.add_argument(
        "--include-reference-refresh",
        dest="include_reference_refresh",
        action="store_true",
        default=True,
        help="Refresh SEC reference files before reconciliation",
    )
    full_reconcile.add_argument(
        "--no-include-reference-refresh",
        dest="include_reference_refresh",
        action="store_false",
        help="Skip SEC reference refresh",
    )
    full_reconcile.add_argument(
        "--no-auto-heal",
        dest="auto_heal",
        action="store_false",
        default=True,
        help="Detect drift without launching targeted resync",
    )
    _add_run_id_arg(full_reconcile)
    full_reconcile.set_defaults(handler=_handle_full_reconcile)

    seed_universe = subparsers.add_parser(
        "seed-universe",
        help="Fetch company_tickers_exchange.json and write CIK universe to S3 as pre-batched JSON Lines.",
    )
    seed_universe.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of companies seeded into sec_tracked_universe (default: all)",
    )
    _add_run_id_arg(seed_universe)
    seed_universe.set_defaults(handler=_handle_seed_universe)

    seed_silver_batches = subparsers.add_parser(
        "seed-silver-batches",
        help=(
            "Write a CIK batch file from companies already in silver (bronze already loaded). "
            "Used by silver_mdm_gold to reprocess silver → MDM → Neo4j → Snowflake "
            "without re-downloading bronze from SEC."
        ),
    )
    seed_silver_batches.add_argument(
        "--tracking-status-filter",
        default="all",
        help=(
            "Which companies to include: 'all' (any status with bronze checkpoint), "
            "'active', or 'bootstrap_pending'. Default: all."
        ),
    )
    seed_silver_batches.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Companies per batch (default: 100).",
    )
    _add_run_id_arg(seed_silver_batches)
    seed_silver_batches.set_defaults(handler=_handle_seed_silver_batches)

    seed_bronze_batches = subparsers.add_parser(
        "seed-bronze-batches",
        help=(
            "Write a CIK batch file by listing CIKs that actually have bronze data "
            "in S3, with zero SEC calls. Used by bronze_seed_silver_gold to stand up "
            "silver/MDM/gold from an existing bronze snapshot (e.g. one copied in "
            "from another environment) without re-fetching from SEC."
        ),
    )
    seed_bronze_batches.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Companies per batch (default: 100).",
    )
    _add_run_id_arg(seed_bronze_batches)
    seed_bronze_batches.set_defaults(handler=_handle_seed_bronze_batches)

    parse_ownership_bronze = subparsers.add_parser(
        "parse-ownership-bronze",
        help=(
            "Parse Form 3/4/5 ownership XMLs already in S3 bronze into silver. "
            "Uses edgartools (Ownership.from_xml). No SEC API calls. "
            "Idempotent — skips accessions already in sec_ownership_reporting_owner."
        ),
    )
    parse_ownership_bronze.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of accessions to process (default: all).",
    )
    parse_ownership_bronze.add_argument(
        "--accession-list",
        type=lambda s: [a.strip() for a in s.split(",") if a.strip()],
        default=None,
        metavar="ACCESSIONS",
        help=(
            "Comma-separated accession numbers to process. "
            "When supplied, only these accessions are parsed (default: all Forms 3/4/5)."
        ),
    )
    _add_run_id_arg(parse_ownership_bronze)
    parse_ownership_bronze.set_defaults(handler=_handle_parse_ownership_bronze)

    parse_adv_bronze = subparsers.add_parser(
        "parse-adv-bronze",
        help=(
            "Parse ADV-family filings already in S3 bronze into silver ADV tables. "
            "Uses the local ADV parser. No SEC API calls. "
            "Idempotent — skips accessions already in sec_adv_filing."
        ),
    )
    parse_adv_bronze.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of not-yet-parsed ADV accessions to process (default: all).",
    )
    parse_adv_bronze.add_argument(
        "--accession-list",
        type=lambda s: [a.strip() for a in s.split(",") if a.strip()],
        default=None,
        metavar="ACCESSIONS",
        help=(
            "Comma-separated accession numbers to process. "
            "When supplied, only these accessions are parsed (default: all ADV-family forms)."
        ),
    )
    parse_adv_bronze.add_argument(
        "--artifact",
        action="append",
        default=[],
        dest="artifacts",
        metavar="ACCESSION,FORM,STORAGE_PATH[,CIK]",
        type=_parse_adv_artifact,
        help=(
            "Explicit already-captured ADV artifact to parse. "
            "Repeatable. Format: ACCESSION,FORM,STORAGE_PATH[,CIK]."
        ),
    )
    _add_run_id_arg(parse_adv_bronze)
    parse_adv_bronze.set_defaults(handler=_handle_parse_adv_bronze)

    bootstrap_batch = subparsers.add_parser(
        "bootstrap-batch",
        help="Bootstrap a specific batch of CIKs (one Distributed Map iteration).",
    )
    bootstrap_batch.add_argument(
        "--cik-list",
        type=_parse_cik_list,
        required=True,
        help="Comma-separated CIK integers for this batch",
    )
    bootstrap_batch.add_argument(
        "--include-pagination",
        dest="include_pagination",
        action="store_true",
        default=True,
        help="Fetch full filing history including pagination files",
    )
    bootstrap_batch.add_argument(
        "--no-include-pagination",
        dest="include_pagination",
        action="store_false",
        help="Skip pagination files (recent filings only)",
    )
    bootstrap_batch.add_argument(
        "--artifact-policy",
        default="all_attachments",
        help="Artifact fetch policy",
    )
    bootstrap_batch.add_argument(
        "--parser-policy",
        default="configured_forms",
        help="Parser execution policy",
    )
    bootstrap_batch.add_argument(
        "--release-mode",
        action="store_true",
        help="Fail closed on the bounded required relationship candidate manifest",
    )
    bootstrap_batch.add_argument(
        "--candidate-manifest",
        default=None,
        help="Local or S3 JSON manifest containing required relationship candidates",
    )
    bootstrap_batch.add_argument(
        "--repair-manifest",
        default=None,
        help="Local or S3 JSON manifest bounding accessions allowed for --force repair",
    )
    bootstrap_batch.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch only accessions authorized by --repair-manifest in release mode",
    )
    _add_run_id_arg(bootstrap_batch)
    bootstrap_batch.set_defaults(handler=_handle_bootstrap_batch)

    ingest_relationship_sources = subparsers.add_parser(
        "ingest-relationship-sources",
        help="Import immutable ADV, subsidiary, and auditor evidence from a release manifest.",
    )
    ingest_relationship_sources.add_argument(
        "--source-manifest", required=True,
        help="Local or S3 JSON manifest of immutable relationship source artifacts",
    )
    _add_run_id_arg(ingest_relationship_sources)
    ingest_relationship_sources.set_defaults(handler=_handle_ingest_relationship_sources)

    bootstrap_next = subparsers.add_parser(
        "bootstrap-next",
        help="Bootstrap the next N pending companies (tracking_status=bootstrap_pending).",
    )
    bootstrap_next.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of companies to bootstrap in this run (default: 100)",
    )
    bootstrap_next.add_argument(
        "--tracking-status-filter",
        default="bootstrap_pending",
        help="Tracked universe status filter (default: bootstrap_pending)",
    )
    bootstrap_next.add_argument(
        "--artifact-policy",
        default="all_attachments",
        help="Artifact fetch policy",
    )
    bootstrap_next.add_argument(
        "--parser-policy",
        default="configured_forms",
        help="Parser execution policy",
    )
    bootstrap_next.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-fetch even if already loaded",
    )
    bootstrap_next.add_argument(
        "--cik-limit",
        type=int,
        default=None,
        help="Window size for CIK chunking (number of CIKs to process); None = no limit",
    )
    bootstrap_next.add_argument(
        "--cik-offset",
        type=int,
        default=0,
        help="0-based offset into the ordered CIK list for windowed chunking",
    )
    _add_run_id_arg(bootstrap_next)
    bootstrap_next.set_defaults(handler=_handle_bootstrap_next)

    gold_refresh = subparsers.add_parser(
        "gold-refresh",
        help="Build gold tables and write Snowflake export manifests from current silver state. "
             "Run once after bootstrap-batch (phased pipeline) completes all batches.",
    )
    _add_run_id_arg(gold_refresh)
    gold_refresh.set_defaults(handler=_handle_gold_refresh)

    compute_windows = subparsers.add_parser(
        "compute-windows",
        help=(
            "Query silver tracking state for ordered CIKs and write cik_windows.jsonl + "
            "cik_snapshot.jsonl to S3 under the run prefix. Pre-Map step consumed by "
            "the windowed bootstrap SM ItemReader."
        ),
    )
    compute_windows.add_argument(
        "--window-size",
        type=int,
        default=500,
        help="Number of CIKs per window (default: 500). Must be > 0.",
    )
    compute_windows.add_argument(
        "--total-cik-limit",
        type=int,
        default=None,
        help=(
            "Cap the total number of tracked CIKs (across all windows, ordered ascending "
            "by CIK) this run processes. Omit, or pass 0, for no limit (process the full "
            "tracked active/bootstrap_pending universe). Used to bound ad-hoc/investigative "
            "load_history runs to a small company sample without mutating MDM "
            "tracking_status. Must be a non-negative integer."
        ),
    )
    _add_run_id_arg(compute_windows)
    compute_windows.set_defaults(handler=_handle_compute_windows)

    write_run_summary = subparsers.add_parser(
        "write-run-summary",
        help=(
            "Write run-summary.json to S3 at the end of a windowed bootstrap run. "
            "Derives window_count and cik_count from the S3 cik_windows.jsonl and "
            "cik_snapshot.jsonl manifests written by compute-windows."
        ),
    )
    write_run_summary.add_argument(
        "--from-windows-key",
        type=str,
        required=True,
        help=(
            "S3 key of the cik_windows.jsonl manifest for this run "
            "(e.g. reference/cik_universe/runs/{run_id}/cik_windows.jsonl)."
        ),
    )
    _add_run_id_arg(write_run_summary)
    write_run_summary.set_defaults(handler=_handle_write_run_summary)

    migrate_silver_shards = subparsers.add_parser(
        "migrate-silver-shards",
        help=(
            "One-time migration: convert a monolithic silver.duckdb into 4 CIK-range shard files "
            "with a verified shard-manifest.json. Run the production CIK percentile query first "
            "(see docs/runbook.md) to verify band boundaries before executing on prod data."
        ),
    )
    migrate_silver_shards.add_argument(
        "--source",
        required=True,
        help="Path to the monolithic silver.duckdb file (local path).",
    )
    migrate_silver_shards.add_argument(
        "--output-dir",
        required=True,
        help="Directory to write shard-{0..3}.duckdb and shard-manifest.json.",
    )
    migrate_silver_shards.add_argument(
        "--band-boundaries",
        default=None,
        help=(
            "JSON array of custom band boundaries, e.g. "
            "'[{\"shard_index\":0,\"cik_min\":0,\"cik_max\":1053917}, ...]'. "
            "Defaults to dev DB quartiles (p25=1053917, p50=1523562, p75=1819990). "
            "Run the prod CIK percentile query first to compute production quartiles."
        ),
    )
    migrate_silver_shards.set_defaults(handler=_handle_migrate_silver_shards)

    bootstrap_fundamentals = subparsers.add_parser(
        "bootstrap-fundamentals",
        help=(
            "Branch B bootstrap: ingest fundamentals silver from bronze. "
            "Runs after Branch A in load-history Step Functions because both "
            "paths publish the unified SEC silver database. "
            "Modes: per-filing (8-K/DEF 14A), entity-facts (XBRL companyfacts), "
            "thirteenf (13F INFORMATION TABLE). Writes to the unified SEC silver database."
        ),
    )
    bootstrap_fundamentals.add_argument(
        "--cik-list",
        type=_parse_cik_list,
        default=None,
        help=(
            "Comma-separated CIK integers for this batch. "
            "Optional: when omitted, the batch is resolved from silver tracking "
            "state (same ordered source as Branch A bootstrap-next) and "
            "windowed by --cik-offset/--cik-limit."
        ),
    )
    bootstrap_fundamentals.add_argument(
        "--cik-limit",
        type=int,
        default=None,
        help="Window size for CIK chunking (number of CIKs to process); None = no limit",
    )
    bootstrap_fundamentals.add_argument(
        "--cik-offset",
        type=int,
        default=0,
        help="0-based offset into the ordered CIK list for windowed chunking",
    )
    bootstrap_fundamentals.add_argument(
        "--mode",
        choices=["per-filing", "entity-facts", "thirteenf"],
        default="per-filing",
        help=(
            "Processing mode: "
            "per-filing = 8-K earnings + DEF 14A proxy (per-accession dispatch); "
            "entity-facts = SEC companyfacts API (CIK-level, writes sec_financial_fact); "
            "thirteenf = 13F INFORMATION TABLE XML (writes sec_thirteenf_holding). "
            "Default: per-filing"
        ),
    )
    bootstrap_fundamentals.add_argument(
        "--silver-root",
        default=None,
        help=(
            "Local root for the unified SEC silver database. Defaults to "
            "$WAREHOUSE_SILVER_ROOT, a local WAREHOUSE_STORAGE_ROOT, or "
            "/tmp/edgar-warehouse-silver for remote storage."
        ),
    )
    bootstrap_fundamentals.add_argument(
        "--release-mode",
        action="store_true",
        help="Fail closed on every required candidate failure; requires --candidate-manifest",
    )
    bootstrap_fundamentals.add_argument(
        "--candidate-manifest",
        default=None,
        help="Local or S3 JSON manifest containing the bounded release candidate accessions",
    )
    _add_run_id_arg(bootstrap_fundamentals)
    bootstrap_fundamentals.set_defaults(handler=_handle_bootstrap_fundamentals)

    verify_pipeline_run = subparsers.add_parser(
        "verify-pipeline-run",
        help="Verify a recorded pipeline run by rechecking stored artifact hashes.",
    )
    verify_pipeline_run.add_argument(
        "--run-id",
        required=True,
        help="Pipeline run id to verify.",
    )
    verify_pipeline_run.set_defaults(handler=_handle_verify_pipeline_run)

    validate_data_quality = subparsers.add_parser(
        "validate-data-quality",
        help="Validate silver/gold data quality and emit a JSON report.",
    )
    validate_data_quality.set_defaults(handler=_handle_validate_data_quality)

    try:
        from edgar_warehouse.mdm.cli import register_mdm_subparser
        register_mdm_subparser(subparsers)
    except ImportError:
        pass  # MDM extras not installed (pipelines image)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)
