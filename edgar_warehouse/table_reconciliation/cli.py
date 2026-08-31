"""``edgar-warehouse table-reconcile`` command handler.

The ``execute()`` handler deliberately bypasses ``run_command``/
``_execute_warehouse`` (the generic bronze-capture command dispatcher, with
its pipeline_run bookkeeping and planned-writes validation machinery) --
this is a read-only report command with nothing to write, so it has no
business going through a write-path dispatcher. Mirrors
``_handle_gold_verify_live``'s self-contained handler-body pattern
(``edgar_warehouse/cli.py``) instead: build the connections directly,
produce the report, print it, translate PASS/FAIL to an exit code.

Registration is a separate concern from the handler body above: this
module exposes ``register_subparser`` and is wired into ``build_parser()``
via a deferred import, mirroring the ``mdm`` subsystem's
``register_mdm_subparser`` precedent (not ``gold-verify-live``, which
registers its subparser inline in ``cli.py`` itself).
"""
from __future__ import annotations

import argparse
import json


def execute(args: argparse.Namespace) -> int:
    from edgar_warehouse.application.command_context_factory import build_warehouse_context
    from edgar_warehouse.application.warehouse_orchestrator import (
        _hydrate_silver_database_from_storage,
    )
    from edgar_warehouse.silver_support.session import open_silver_database
    from edgar_warehouse.silver_support.snowflake_reader import SnowflakeSilverReader
    from edgar_warehouse.table_reconciliation.report import (
        build_report,
        compare_to_previous,
        render_report_json,
    )

    table_names = None
    tables_arg = getattr(args, "tables", None)
    if tables_arg:
        table_names = [name.strip() for name in tables_arg.split(",") if name.strip()]

    context = build_warehouse_context("table-reconcile")
    _hydrate_silver_database_from_storage(context)
    duckdb_reader = open_silver_database(context.silver_root)
    snowflake_reader = SnowflakeSilverReader.connect()
    try:
        report = build_report(
            duckdb_reader,
            snowflake_reader,
            cohort_size=getattr(args, "cohort_size", None) or 500,
            table_names=table_names,
        )
    finally:
        duckdb_reader.close()
        snowflake_reader.close()

    compare_to = getattr(args, "compare_to", None)
    if compare_to:
        with open(compare_to, encoding="utf-8") as fh:
            previous = json.load(fh)
        report["no_op_rerun_check"] = compare_to_previous(report, previous)

    rendered = render_report_json(report)
    output_path = getattr(args, "output", None)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(rendered)
            fh.write("\n")

    print(rendered)

    if report["overall_status"] != "pass":
        return 1
    if compare_to and report.get("no_op_rerun_check", {}).get("status") != "pass":
        return 1
    return 0


def register_subparser(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "table-reconcile",
        help=(
            "DuckDB Retirement Cutover Ticket 08: for every SEC-content table, prove "
            "bronze-to-silver key expectations, declared primary-key uniqueness, "
            "required-parent integrity, and a canonical semantic-content digest match "
            "between DuckDB canonical and Snowflake EDGARTOOLS_SILVER. Emits a "
            "fail-closed PASS/FAIL JSON report; non-zero exit on any table FAIL."
        ),
    )
    parser.add_argument(
        "--tables",
        help="Comma-separated table names to restrict the run to (default: every "
        "table in TABLE_CONTRACTS).",
    )
    parser.add_argument(
        "--cohort-size",
        type=int,
        help="Max keys sampled per table for the semantic-content digest check "
        "(default: 500). The other three checks always run full-table.",
    )
    parser.add_argument(
        "--output",
        help="Optional file path to also write the JSON report to (in addition to stdout).",
    )
    parser.add_argument(
        "--compare-to",
        help="Path to a prior report.json -- when given, also checks this run's "
        "digests against it (the no-op/rerun-idempotency case) and fails closed on drift.",
    )
    parser.set_defaults(handler=execute)
