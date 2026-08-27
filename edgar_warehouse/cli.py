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


def _parse_source_name_list(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise argparse.ArgumentTypeError("expected at least one source name")
    return items


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
        "--ownership-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Form 3/4/5 history to fetch/parse (default: 2). "
            "Also bounds Item 5.02 8-K selection unless "
            "--item-502-lookback-years is set. Use 0 for full history. "
            "Also settable via WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS."
        ),
    )
    parser.add_argument(
        "--item-502-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Item 5.02 8-K history to fetch/parse (default: 2, or "
            "ownership lookback when that is set). Use 0 for full history. "
            "Also settable via WAREHOUSE_ITEM_502_LOOKBACK_YEARS."
        ),
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
    if args.recurring_index_lookback_days is None:
        args.recurring_index_lookback_days = (
            0 if args.start_date is not None or args.end_date is not None else 7
        )
    return run_command("daily-incremental", args)


def _handle_capture_filing_artifact(args: argparse.Namespace) -> int:
    return run_command("capture-filing-artifact", args)


def _handle_drive_filing_discovery_for_date(args: argparse.Namespace) -> int:
    return run_command("drive-filing-discovery-for-date", args)


def _handle_drive_adv_filing_discovery_for_date(args: argparse.Namespace) -> int:
    return run_command("drive-adv-filing-discovery-for-date", args)


def _handle_drive_submissions_discovery(args: argparse.Namespace) -> int:
    return run_command("drive-submissions-discovery", args)


def _handle_drive_company_facts_discovery(args: argparse.Namespace) -> int:
    return run_command("drive-company-facts-discovery", args)


def _handle_drive_reference_catalog_discovery(args: argparse.Namespace) -> int:
    return run_command("drive-reference-catalog-discovery", args)


def _handle_drive_adv_bulk_dataset_discovery(args: argparse.Namespace) -> int:
    return run_command("drive-adv-bulk-dataset-discovery", args)


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


def _handle_compute_remaining_batches(args: argparse.Namespace) -> int:
    return run_command("compute-remaining-batches", args)


def _handle_ingest_relationship_sources(args: argparse.Namespace) -> int:
    return run_command("ingest-relationship-sources", args)


def _handle_fetch_adv_bulk(args: argparse.Namespace) -> int:
    return run_command("fetch-adv-bulk", args)


def _handle_fetch_firm_roster(args: argparse.Namespace) -> int:
    return run_command("fetch-firm-roster", args)


def _handle_reconcile_relationship_release(args: argparse.Namespace) -> int:
    return run_command("reconcile-relationship-release", args)


def _handle_bootstrap_next(args: argparse.Namespace) -> int:
    return run_command("bootstrap-next", args)


def _handle_gold_refresh(args: argparse.Namespace) -> int:
    return run_command("gold-refresh", args)


def _handle_backfill_mdm_entity_ids(args: argparse.Namespace) -> int:
    return run_command("backfill-mdm-entity-ids", args)


def _handle_backfill_silver_landing_company_metadata(args: argparse.Namespace) -> int:
    return run_command("backfill-silver-landing-company-metadata", args)


def _handle_gold_verify_live(args: argparse.Namespace) -> int:
    import json
    import sys

    from edgar_warehouse.mdm.export import SnowflakeConnectionSettings
    from edgar_warehouse.serving.gold_verify import verify_gold_live

    settings = SnowflakeConnectionSettings.from_env()
    connection = settings.connect()
    try:
        result = verify_gold_live(connection, database=settings.database)
    finally:
        connection.close()

    print(json.dumps(result.payload, indent=2, sort_keys=True))
    if not result.passed:
        print(
            f"gold-verify-live: {len(result.empty_tables)} of {len(result.row_counts)} "
            "expected EDGARTOOLS_GOLD tables are empty or unreachable: "
            + ", ".join(result.empty_tables),
            file=sys.stderr,
        )
        return 1
    return 0


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


def _handle_compute_identity_refresh_window(args: argparse.Namespace) -> int:
    return run_command("compute-identity-refresh-window", args)


def _handle_acquire_identity_refresh_lease(args: argparse.Namespace) -> int:
    return run_command("acquire-identity-refresh-lease", args)


def _handle_release_identity_refresh_lease(args: argparse.Namespace) -> int:
    return run_command("release-identity-refresh-lease", args)


def _handle_acquire_sec_fetch_lease(args: argparse.Namespace) -> int:
    return run_command("acquire-sec-fetch-lease", args)


def _handle_release_sec_fetch_lease(args: argparse.Namespace) -> int:
    return run_command("release-sec-fetch-lease", args)


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


def _handle_reduce_identity_refresh(args: argparse.Namespace) -> int:
    return run_command("reduce-identity-refresh", args)


def _handle_verify_pipeline_run(args: argparse.Namespace) -> int:
    return run_command("verify-pipeline-run", args)


def _handle_validate_data_quality(args: argparse.Namespace) -> int:
    return run_command("validate-data-quality", args)


def _handle_resolve_snowflake_env(args: argparse.Namespace) -> int:
    """Print `export KEY=VALUE` shell lines for a Snowflake connection.

    Reuses SnowflakeConnectionSettings.from_env() -- the same resolution chain
    already trusted by `mdm export`/`mdm sync-graph` -- instead of a second,
    independent password-parsing implementation.

    The resolved password DOES appear in this command's stdout -- there is no
    other way to hand a secret across a process boundary to a caller's shell.
    What keeps it off a human's screen is refusing to write that stdout to an
    interactive terminal at all: the intended usage is
    `eval "$(edgar-warehouse resolve-snowflake-env ...)"` or
    `source <(edgar-warehouse resolve-snowflake-env ...)`, where stdout is a
    pipe, not a tty. A bare interactive invocation is refused below.
    """
    import os
    import shlex
    import sys

    from edgar_warehouse.mdm.export import SnowflakeConnectionSettings

    if sys.stdout.isatty():
        print(
            "error: refusing to print resolved Snowflake credentials to an interactive "
            "terminal. Run this via `eval \"$(edgar-warehouse resolve-snowflake-env "
            "--connection <name>)\"` (or `source <(...)`) so the output is consumed by "
            "the shell, not displayed on screen.",
            file=sys.stderr,
        )
        return 2

    previous_connection = os.environ.get("SNOWFLAKE_CONNECTION")
    if args.connection:
        os.environ["SNOWFLAKE_CONNECTION"] = args.connection

    try:
        settings = SnowflakeConnectionSettings.from_env()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        # Resolution only needs SNOWFLAKE_CONNECTION for the instant of the
        # from_env() call above -- restore it so this command never leaves a
        # process-wide env mutation behind for whatever runs next.
        if args.connection:
            if previous_connection is None:
                os.environ.pop("SNOWFLAKE_CONNECTION", None)
            else:
                os.environ["SNOWFLAKE_CONNECTION"] = previous_connection

    lines = [
        f"export DBT_SNOWFLAKE_ACCOUNT={shlex.quote(settings.account)}",
        f"export DBT_SNOWFLAKE_USER={shlex.quote(settings.user)}",
        f"export DBT_SNOWFLAKE_PASSWORD={shlex.quote(settings.password)}",
        f"export DBT_SNOWFLAKE_DATABASE={shlex.quote(settings.database)}",
        f"export DBT_SNOWFLAKE_WAREHOUSE={shlex.quote(settings.warehouse)}",
        f"export TF_VAR_snowflake_password={shlex.quote(settings.password)}",
    ]
    if settings.role:
        lines.append(f"export DBT_SNOWFLAKE_ROLE={shlex.quote(settings.role)}")

    print("\n".join(lines))
    connection_label = args.connection or previous_connection or "(default)"
    print(f"resolved Snowflake credentials for connection '{connection_label}'", file=sys.stderr)
    return 0


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
        "--recurring-index-lookback-days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Force the trailing N calendar days of SEC daily indexes and constrain "
            "artifact discovery to their exact accession union. Defaults to 7 for an "
            "ordinary daily run; an explicit --start-date/--end-date range preserves "
            "historical discovery unless this option is also supplied."
        ),
    )
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
        "--ownership-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Form 3/4/5 history to fetch/parse (default: 2). "
            "Also bounds Item 5.02 8-K selection unless "
            "--item-502-lookback-years is set. Use 0 for full history. "
            "Also settable via WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS."
        ),
    )
    daily_incremental.add_argument(
        "--item-502-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Item 5.02 8-K history to fetch/parse (default: 2, or "
            "ownership lookback when that is set). Use 0 for full history. "
            "Also settable via WAREHOUSE_ITEM_502_LOOKBACK_YEARS."
        ),
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
    daily_incremental.add_argument(
        "--enable-filing-artifact-gated-capture",
        dest="enable_filing_artifact_gated_capture",
        action="store_true",
        default=False,
        help=(
            "Ticket 46 (change-propagation map): also run filing_artifact's "
            "ledger-gated discovery/capture in-process for this run's final "
            "business date, alongside the legacy artifact-fetch path, for "
            "Ticket 10 Decision 2's side-by-side verification window. Off by "
            "default. A failure here never fails this command -- but a "
            "successful run is NOT passive observation: it advances the "
            "Source Family Registry's real catch-up progress for "
            "filing_artifact, the same signal Ticket 27's removal-evidence "
            "bullets gate on."
        ),
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

    capture_filing_artifact = subparsers.add_parser(
        "capture-filing-artifact",
        help="Carry one operator-authorized SEC filing-artifact request through "
        "the ledger-gated acquisition Facade into verified Bronze evidence.",
    )
    capture_filing_artifact.add_argument(
        "--candidate-id",
        required=True,
        help="Stable identity for this fetch candidate (idempotency key)",
    )
    capture_filing_artifact.add_argument(
        "--logical-source-key",
        required=True,
        help="Logical source key, e.g. <cik>/<accession>/<document-name>",
    )
    capture_filing_artifact.add_argument(
        "--source-url",
        required=True,
        help="Canonical SEC archival URL for the filing artifact",
    )
    capture_filing_artifact.add_argument(
        "--cause-reference",
        required=True,
        help="Operator-supplied reason for this explicit fetch request",
    )
    capture_filing_artifact.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    capture_filing_artifact.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    _add_run_id_arg(capture_filing_artifact)
    capture_filing_artifact.set_defaults(handler=_handle_capture_filing_artifact)

    drive_filing_discovery_for_date = subparsers.add_parser(
        "drive-filing-discovery-for-date",
        help="Seal one business date's already-captured SEC daily index into a "
        "Discovery Manifest and drive each in-scope filing candidate through "
        "the ledger-gated acquisition Facade.",
    )
    drive_filing_discovery_for_date.add_argument(
        "business_date", help="Business date in YYYY-MM-DD format"
    )
    drive_filing_discovery_for_date.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_filing_discovery_for_date.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_filing_discovery_for_date.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: filing_artifact-v1)",
    )
    _add_run_id_arg(drive_filing_discovery_for_date)
    drive_filing_discovery_for_date.set_defaults(
        handler=_handle_drive_filing_discovery_for_date
    )

    drive_adv_filing_discovery_for_date = subparsers.add_parser(
        "drive-adv-filing-discovery-for-date",
        help="Seal one business date's already-captured SEC daily index into a "
        "Discovery Manifest and drive each in-scope ADV filing candidate "
        "(Form ADV and its siblings) through the ledger-gated acquisition "
        "Facade -- the adv_filing sibling of drive-filing-discovery-for-date.",
    )
    drive_adv_filing_discovery_for_date.add_argument(
        "business_date", help="Business date in YYYY-MM-DD format"
    )
    drive_adv_filing_discovery_for_date.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_adv_filing_discovery_for_date.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_adv_filing_discovery_for_date.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: adv_filing-v1)",
    )
    _add_run_id_arg(drive_adv_filing_discovery_for_date)
    drive_adv_filing_discovery_for_date.set_defaults(
        handler=_handle_drive_adv_filing_discovery_for_date
    )

    drive_submissions_discovery = subparsers.add_parser(
        "drive-submissions-discovery",
        help="Drive a bounded CIK universe's submissions main snapshot + "
        "pagination-file capture through the ledger-gated acquisition Facade.",
    )
    drive_submissions_discovery.add_argument(
        "--cik-list", type=_parse_cik_list, help="Comma-separated CIK list"
    )
    drive_submissions_discovery.add_argument(
        "--tracking-status-filter",
        default="active",
        help="Tracked universe status filter (default: active)",
    )
    drive_submissions_discovery.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of CIKs to drive this run",
    )
    drive_submissions_discovery.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_submissions_discovery.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_submissions_discovery.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: submissions-v1)",
    )
    _add_run_id_arg(drive_submissions_discovery)
    drive_submissions_discovery.set_defaults(
        handler=_handle_drive_submissions_discovery
    )

    drive_company_facts_discovery = subparsers.add_parser(
        "drive-company-facts-discovery",
        help="Drive a bounded CIK universe's company-facts snapshot capture "
        "through the ledger-gated acquisition Facade.",
    )
    drive_company_facts_discovery.add_argument(
        "--cik-list", type=_parse_cik_list, help="Comma-separated CIK list"
    )
    drive_company_facts_discovery.add_argument(
        "--tracking-status-filter",
        default="active",
        help="Tracked universe status filter (default: active)",
    )
    drive_company_facts_discovery.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of CIKs to drive this run",
    )
    drive_company_facts_discovery.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_company_facts_discovery.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_company_facts_discovery.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: company-facts-v1)",
    )
    _add_run_id_arg(drive_company_facts_discovery)
    drive_company_facts_discovery.set_defaults(
        handler=_handle_drive_company_facts_discovery
    )

    drive_reference_catalog_discovery = subparsers.add_parser(
        "drive-reference-catalog-discovery",
        help="Drive the fixed SEC reference-catalog source-name set through "
        "the ledger-gated acquisition Facade.",
    )
    drive_reference_catalog_discovery.add_argument(
        "--source-names",
        type=_parse_source_name_list,
        default=None,
        help="Comma-separated source-name override (default: both supported "
        "ticker catalogs)",
    )
    drive_reference_catalog_discovery.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_reference_catalog_discovery.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_reference_catalog_discovery.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: reference-catalog-v1)",
    )
    _add_run_id_arg(drive_reference_catalog_discovery)
    drive_reference_catalog_discovery.set_defaults(
        handler=_handle_drive_reference_catalog_discovery
    )

    drive_adv_bulk_dataset_discovery = subparsers.add_parser(
        "drive-adv-bulk-dataset-discovery",
        help="Resolve and drive the rolling window of ADV bulk archives plus "
        "the latest Firm Roster archives through the ledger-gated "
        "acquisition Facade.",
    )
    drive_adv_bulk_dataset_discovery.add_argument(
        "--window-months",
        type=int,
        default=None,
        help="Trailing months of ADV bulk periods to consider (default: 13)",
    )
    drive_adv_bulk_dataset_discovery.add_argument(
        "--worker-id",
        default=None,
        help="Fencing worker identity; defaults to a process-derived value",
    )
    drive_adv_bulk_dataset_discovery.add_argument(
        "--lease-seconds",
        type=int,
        default=None,
        help="Fetch-work lease duration in seconds (default: 300)",
    )
    drive_adv_bulk_dataset_discovery.add_argument(
        "--registry-version",
        default=None,
        help="Source Family Registry version tied to issued decisions "
        "(default: adv-bulk-dataset-v1)",
    )
    _add_run_id_arg(drive_adv_bulk_dataset_discovery)
    drive_adv_bulk_dataset_discovery.set_defaults(
        handler=_handle_drive_adv_bulk_dataset_discovery
    )

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
            "Used by silver_mdm_gold to reprocess silver → MDM → graph (Snowflake-hosted "
            "Neo4j Graph Analytics Native App) → Snowflake without re-downloading bronze "
            "from SEC."
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
            "Idempotent — skips accessions already in sec_ownership_reporting_owner. "
            "Default lookback is the past 2 years of Form 3/4/5 filings."
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
    parse_ownership_bronze.add_argument(
        "--ownership-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Form 3/4/5 history to parse (default: 2). "
            "Use 0 for full history. Also settable via "
            "WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS."
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
        "--ownership-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Form 3/4/5 history to fetch/parse (default: 2). "
            "Also bounds Item 5.02 8-K selection unless "
            "--item-502-lookback-years is set. Use 0 for full history. "
            "Also settable via WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS."
        ),
    )
    bootstrap_batch.add_argument(
        "--item-502-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Item 5.02 8-K history to fetch/parse (default: 2, or "
            "ownership lookback when that is set). Use 0 for full history. "
            "Also settable via WAREHOUSE_ITEM_502_LOOKBACK_YEARS."
        ),
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
    bootstrap_batch.add_argument(
        "--resume-ledger-run-id",
        default=None,
        help=(
            "Namespace for this batch's default-path done marker (pipeline-"
            "resumability ticket 02). Defaults to --run-id when omitted, so "
            "every run writes markers under its own id; a resumed execution "
            "passes the ORIGINAL run's id here to accumulate against the "
            "same ledger instead of starting a fresh, empty one."
        ),
    )
    _add_run_id_arg(bootstrap_batch)
    bootstrap_batch.set_defaults(handler=_handle_bootstrap_batch)

    compute_remaining_batches = subparsers.add_parser(
        "compute-remaining-batches",
        help=(
            "pipeline-resumability ticket 02: filter a prior run's frozen "
            "cik_batches.jsonl down to batches with no default-path done "
            "marker yet, and write the result as this run's own "
            "cik_batches.jsonl. Fails closed if --resume-ledger-run-id has "
            "no readable, non-empty manifest."
        ),
    )
    compute_remaining_batches.add_argument(
        "--resume-ledger-run-id",
        required=True,
        help="The ORIGINAL run id whose frozen cik_batches.jsonl and done markers to resume from",
    )
    _add_run_id_arg(compute_remaining_batches)
    compute_remaining_batches.set_defaults(handler=_handle_compute_remaining_batches)

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

    fetch_adv_bulk = subparsers.add_parser(
        "fetch-adv-bulk",
        help=(
            "Fetch new SEC/IAPD advFilingData monthly archives not yet in silver "
            "and stage a source manifest for ingest-relationship-sources."
        ),
    )
    fetch_adv_bulk.add_argument(
        "--dataset-period",
        help=(
            "Force a specific YYYY-MM period instead of auto-detecting the rolling "
            "window. Manual repair/backfill only -- the normal path auto-detects."
        ),
    )
    fetch_adv_bulk.add_argument(
        "--force",
        action="store_true",
        help="Allow re-fetching a period already ingested (requires --dataset-period).",
    )
    _add_run_id_arg(fetch_adv_bulk)
    fetch_adv_bulk.set_defaults(handler=_handle_fetch_adv_bulk)

    fetch_firm_roster = subparsers.add_parser(
        "fetch-firm-roster",
        help=(
            "Fetch the latest SEC Firm Roster CSV archive not yet in silver "
            "and stage a source manifest for ingest-relationship-sources."
        ),
    )
    fetch_firm_roster.add_argument(
        "--dataset-period",
        help=(
            "Force a specific YYYY-MM period instead of auto-detecting the latest "
            "published one. Manual repair/backfill only -- the normal path auto-detects."
        ),
    )
    fetch_firm_roster.add_argument(
        "--force",
        action="store_true",
        help="Allow re-fetching a period already ingested (requires --dataset-period).",
    )
    _add_run_id_arg(fetch_firm_roster)
    fetch_firm_roster.set_defaults(handler=_handle_fetch_firm_roster)

    reconcile_relationship_release = subparsers.add_parser(
        "reconcile-relationship-release",
        help="Fan in strict distributed batch ledgers and prove exact candidate completion.",
    )
    reconcile_relationship_release.add_argument(
        "--candidate-manifest", required=True,
        help="Local or S3 frozen relationship candidate manifest",
    )
    reconcile_relationship_release.add_argument(
        "--attestations-json",
        required=True,
        help=(
            "JSON object with five named Ticket 20 gate attestations: "
            "warehouse, mdm, graph, release_data_operator, release_owner"
        ),
    )
    reconcile_relationship_release.add_argument(
        "--execution-arn",
        default=None,
        help="Optional Step Functions execution ARN bound into the evidence artifact",
    )
    reconcile_relationship_release.add_argument(
        "--image-digest",
        default=None,
        help="Optional warehouse image digest bound into the evidence artifact",
    )
    reconcile_relationship_release.add_argument(
        "--insider-coverage",
        default=None,
        help=(
            "Optional path/URI to the insider_coverage JSON produced by "
            "'mdm verify-insider-coverage --output ...' (Ticket 21). When "
            "provided, evidence fail-closes on any unresolved insider."
        ),
    )
    _add_run_id_arg(reconcile_relationship_release)
    reconcile_relationship_release.set_defaults(handler=_handle_reconcile_relationship_release)

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
        "--ownership-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Form 3/4/5 history to fetch/parse (default: 2). "
            "Also bounds Item 5.02 8-K selection unless "
            "--item-502-lookback-years is set. Use 0 for full history. "
            "Also settable via WAREHOUSE_OWNERSHIP_LOOKBACK_YEARS."
        ),
    )
    bootstrap_next.add_argument(
        "--item-502-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of Item 5.02 8-K history to fetch/parse (default: 2, or "
            "ownership lookback when that is set). Use 0 for full history. "
            "Also settable via WAREHOUSE_ITEM_502_LOOKBACK_YEARS."
        ),
    )
    bootstrap_next.add_argument(
        "--filing-lookback-years",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Years of general filing history (10-K/10-Q/8-K/DEF 14A/13F/ADV/"
            "etc) to bronze-discover at all -- unlike --ownership-lookback-"
            "years/--item-502-lookback-years, which only bound which "
            "already-discovered filings get artifact-fetched/parsed, this "
            "bounds sec_company_filing itself: filings older than the "
            "window are never written. Default: 0 (disabled, full history) "
            "-- opt in explicitly. Also settable via "
            "WAREHOUSE_FILING_LOOKBACK_YEARS."
        ),
    )
    bootstrap_next.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force re-fetch even if already loaded",
    )
    bootstrap_next.add_argument(
        "--silver-only",
        action="store_true",
        default=False,
        help=(
            "Publish Bronze/Silver only and skip the inline gold build and "
            "Snowflake export. Used by phased workflows that run one final "
            "gold-refresh after all windows complete."
        ),
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

    backfill_mdm_entity_ids = subparsers.add_parser(
        "backfill-mdm-entity-ids",
        help="Sweep the EDGARTOOLS_SILVER Snowflake tables and backfill mdm_entity_id on rows "
             "left NULL at parse time, from MDM's already-resolved MdmSourceRef rows. Read-only "
             "against MDM -- does not trigger entity resolution. Snowflake-only (no DuckDB "
             "read or write, no sec_fetch_active lease needed -- see "
             "edgar_warehouse/mdm_entity_backfill.py).",
    )
    _add_run_id_arg(backfill_mdm_entity_ids)
    backfill_mdm_entity_ids.set_defaults(handler=_handle_backfill_mdm_entity_ids)

    backfill_silver_landing_company_metadata = subparsers.add_parser(
        "backfill-silver-landing-company-metadata",
        help="One-time seed of sec_company/sec_company_address/sec_company_former_name/"
             "sec_company_submission_file into the Snowflake landing zone from DuckDB "
             "canonical silver, for rows whose company metadata predates the landing-zone "
             "write path and will never reach it through the checksum-gated incremental "
             "path (see edgar_warehouse/silver_landing_company_backfill.py). Safe to re-run.",
    )
    _add_run_id_arg(backfill_silver_landing_company_metadata)
    backfill_silver_landing_company_metadata.set_defaults(
        handler=_handle_backfill_silver_landing_company_metadata
    )

    gold_verify_live = subparsers.add_parser(
        "gold-verify-live",
        help="Query row counts across every EDGARTOOLS_GOLD dynamic table via a direct Snowflake "
             "connection and fail (non-zero exit) if any expected table is empty. Independent of "
             "the bronze/silver/manifest pipeline -- run any time after gold-refresh to confirm "
             "gold actually populated, not just that the dynamic tables compile.",
    )
    gold_verify_live.set_defaults(handler=_handle_gold_verify_live)

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

    compute_identity_refresh_window = subparsers.add_parser(
        "compute-identity-refresh-window",
        help=(
            "Build the scheduled company-identity CIK batches. Daily mode "
            "force-rechecks trailing SEC daily indexes and intersects impacted "
            "CIKs with the active company-eligible universe; backstop mode emits "
            "the complete active company-eligible universe."
        ),
    )
    compute_identity_refresh_window.add_argument(
        "--mode",
        choices=["daily", "backstop"],
        default="daily",
        help="Scheduled identity refresh mode (default: daily).",
    )
    compute_identity_refresh_window.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of trailing calendar days to force-recheck and union (default: 7).",
    )
    compute_identity_refresh_window.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of CIKs per batch line in the output JSONL (default: 500).",
    )
    _add_run_id_arg(compute_identity_refresh_window)
    compute_identity_refresh_window.set_defaults(handler=_handle_compute_identity_refresh_window)

    reduce_identity_refresh = subparsers.add_parser(
        "reduce-identity-refresh",
        help="Fail-closed reducer: merge one completed Daily Identity Refresh run and publish canonical silver once.",
    )
    _add_run_id_arg(reduce_identity_refresh)
    reduce_identity_refresh.add_argument(
        "--max-attempts", type=int, default=3,
        help="Bounded reducer-only retry count for an ETag promotion conflict (default: 3).",
    )
    reduce_identity_refresh.set_defaults(handler=_handle_reduce_identity_refresh)

    acquire_identity_refresh_lease = subparsers.add_parser(
        "acquire-identity-refresh-lease",
        help=(
            "Atomically acquire the run-level lease shared by the Daily Identity Refresh and "
            "the Identity Backstop Sweep (release-readiness ticket 45/49), so only one of the "
            "two ever runs at a time."
        ),
    )
    acquire_identity_refresh_lease.add_argument(
        "--mode",
        choices=["daily", "backstop"],
        required=True,
        help="Which refresh mode is attempting to acquire the lease.",
    )
    _add_run_id_arg(acquire_identity_refresh_lease)
    acquire_identity_refresh_lease.set_defaults(handler=_handle_acquire_identity_refresh_lease)

    release_identity_refresh_lease = subparsers.add_parser(
        "release-identity-refresh-lease",
        help="Release the Daily Identity Refresh / Identity Backstop Sweep run-level lease.",
    )
    _add_run_id_arg(release_identity_refresh_lease)
    release_identity_refresh_lease.set_defaults(handler=_handle_release_identity_refresh_lease)

    acquire_sec_fetch_lease = subparsers.add_parser(
        "acquire-sec-fetch-lease",
        help=(
            "Atomically acquire the cross-command SEC-fetch lease (release-readiness "
            "ticket 80), so only one of the five SEC-fetching commands runs its "
            "fetch-heavy phase at a time platform-wide."
        ),
    )
    _add_run_id_arg(acquire_sec_fetch_lease)
    acquire_sec_fetch_lease.set_defaults(handler=_handle_acquire_sec_fetch_lease)

    release_sec_fetch_lease = subparsers.add_parser(
        "release-sec-fetch-lease",
        help="Release the cross-command SEC-fetch lease.",
    )
    _add_run_id_arg(release_sec_fetch_lease)
    release_sec_fetch_lease.set_defaults(handler=_handle_release_sec_fetch_lease)

    write_run_summary = subparsers.add_parser(
        "write-run-summary",
        help=(
            "Write run-summary.json to S3 at the end of a windowed bootstrap run. "
            "Derives window_count and cik_count from the S3 cik_windows.jsonl and "
            "cik_snapshot.jsonl manifests written by compute-windows, resolving both "
            "keys internally from --run-id (the canonical path resolver, not a "
            "caller-supplied key)."
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
            "thirteenf (13F INFORMATION TABLE), company-identity (master "
            "identity, no ownership/ADV touched). Writes to the unified SEC "
            "silver database."
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
        choices=["per-filing", "entity-facts", "thirteenf", "company-identity"],
        default="per-filing",
        help=(
            "Processing mode: "
            "per-filing = 8-K earnings + DEF 14A proxy (per-accession dispatch); "
            "entity-facts = SEC companyfacts API (CIK-level, writes sec_financial_fact); "
            "thirteenf = 13F INFORMATION TABLE XML (writes sec_thirteenf_holding); "
            "company-identity = company master identity (reference tickers + "
            "per-CIK submissions metadata), no ownership/ADV artifact fetch or "
            "parse. Default: per-filing"
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
    bootstrap_fundamentals.add_argument(
        "--identity-refresh-run-id",
        default=None,
        help=(
            "Daily Identity Refresh only: persist this explicit company-identity CIK batch as an "
            "immutable delta; do not publish canonical silver. Must equal --run-id."
        ),
    )
    bootstrap_fundamentals.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Force re-fetch of companyfacts (entity-facts mode) even when silver "
            "already has facts at the current facts_parser_version"
        ),
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

    resolve_snowflake_env = subparsers.add_parser(
        "resolve-snowflake-env",
        help="Resolve Snowflake connection settings for a named connection and print "
             "'export KEY=VALUE' shell lines (DBT_SNOWFLAKE_*, TF_VAR_snowflake_password). "
             "Reuses the same resolution chain as `mdm export`/`mdm sync-graph`: individual "
             "MDM_SNOWFLAKE_*/DBT_SNOWFLAKE_* env vars first, then the "
             "MDM_SNOWFLAKE_SECRET_JSON/DBT_SNOWFLAKE_SECRET_JSON blob, then SnowCLI's "
             "~/.snowflake/connections.toml. Output is shell code meant for eval \"$(...)\" -- "
             "never print it directly to a terminal a human will read.",
    )
    resolve_snowflake_env.add_argument(
        "--connection",
        help="SnowCLI connection name to resolve (sets SNOWFLAKE_CONNECTION for this process "
             "only). Defaults to the SNOWFLAKE_CONNECTION env var, then config.toml's "
             "default_connection_name, then 'snowconn'.",
    )
    resolve_snowflake_env.set_defaults(handler=_handle_resolve_snowflake_env)

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
