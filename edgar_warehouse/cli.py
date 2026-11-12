"""The command line: Rules, Bookkeeping, Change Journal, MDM, RDM, silver and agent context."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar-warehouse",
        description="Configured Rules, Bookkeeping, Change Journal, and MDM operations.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    from edgar_warehouse.bookkeeping.clean.cli import register as register_bookkeeping
    from edgar_warehouse.application.journal_recovery import register as register_journal
    from edgar_warehouse.bundle import register as register_bundle
    from edgar_warehouse.context import register as register_context
    from edgar_warehouse.mdm.cli import register_mdm_subparser
    from edgar_warehouse.rdm.cli import register as register_rdm
    from edgar_warehouse.silver_writer.cli import register as register_silver
    from edgar_warehouse.rules.cli import register as register_rules
    from edgar_warehouse.rules.loading import register as register_load
    from edgar_warehouse.application.plan_cli import register as register_plan
    from edgar_warehouse.workers.cli import arguments as worker_arguments

    register_mdm_subparser(subparsers)
    register_bookkeeping(subparsers)
    register_rules(subparsers)
    register_load(subparsers)
    register_journal(subparsers)
    worker_arguments(subparsers.add_parser("workers", help="Run a worker for one profile and run"))
    register_plan(subparsers)
    register_context(subparsers)
    register_rdm(subparsers)
    register_silver(subparsers)
    register_bundle(subparsers, parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["bookkeeping"]:
        # Control starts alone: building the full parser would import MDM and
        # the other domains, which Bookkeeping must never load (to-do 20a).
        from edgar_warehouse.bookkeeping.clean.cli import main as bookkeeping
        return bookkeeping(argv[1:])
    else:
        args = build_parser().parse_args(argv)
    return args.handler(args)
