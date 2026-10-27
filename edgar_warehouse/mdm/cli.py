"""CLI subcommand: `edgar-warehouse mdm ...`, MDM only.

Commands: migrate, check-connectivity, counts, prepare-clean-company,
prepare-capture, name-census, force-publish, rebuild-name-index and rebuild-detail-lookup. The legacy MDM commands and their tables are
deleted (platform validation slice 2a).
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Callable

from edgar_warehouse.mdm.observability import elapsed_ms, emit_mdm_event


def register_mdm_subparser(subparsers: argparse._SubParsersAction) -> None:
    mdm = subparsers.add_parser("mdm", help="MDM: migration, connectivity, counts, and preparation")
    mdm_sub = mdm.add_subparsers(dest="mdm_command", required=True)

    migrate = mdm_sub.add_parser("migrate", help="Create or upgrade the MDM schema")
    migrate.add_argument("--application-role", default="application")
    migrate.add_argument("--application-host", default="%", help="MySQL runtime account host")
    migrate.add_argument("--prepared-store", action="store_true", default=True,
                         help="Install governed prepared storage on a fresh PostgreSQL or MySQL target")
    migrate.set_defaults(handler=_logged_handler("migrate", _handle_migrate))

    prepare = mdm_sub.add_parser("prepare-clean-company", help="Write the Company mastering target's input manifest for a bounded local sample from a raw SEC capture")
    prepare.add_argument("--capture", required=True, help="An SEC submissions capture folder: receipts.jsonl and bronze/")
    prepare.add_argument("--documents", required=True, help="JSON file: this bundle's main submissions documents by receipt key (at most 512)")
    prepare.add_argument("--population", required=True, help="The population file the Name Census counted")
    prepare.add_argument("--catalog", required=True, help="Receipt key of the SEC exchange ticker catalog")
    prepare.add_argument("--capture-run", required=True, help="Approved capture run ID, bound into every row")
    prepare.add_argument("--catalog-run", required=True, help="Approved ticker catalog run ID")
    prepare.add_argument("--observed-at", required=True, help="When the capture was observed (ISO 8601 instant)")
    prepare.add_argument("--name-census", required=True, help="Name Census file that counted this population (mdm name-census)")
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--as-of", required=True)
    prepare.add_argument("--revision", type=int, required=True)
    prepare.add_argument("--all", action="store_true", help="Name every document, processed or not (a forced run); "
                     "by default only documents the Change Journal does not record as processed under these rules")
    prepare.set_defaults(handler=_logged_handler("prepare-clean-company", _clean("prepare_clean_company")))

    capture = mdm_sub.add_parser("prepare-capture", help="Write a declared target's input manifest for one bundle of "
                                 "captured documents, from the source's Bookkeeping section (version 2)")
    capture.add_argument("--source", required=True, help="The source under rules/sources/")
    capture.add_argument("--target", default="mastering", help="The source's Bookkeeping target (default mastering)")
    capture.add_argument("--capture", required=True, help="A capture folder: receipts.jsonl and bronze/")
    capture.add_argument("--documents", required=True, help="JSON file: this bundle's documents by receipt key (at most 512)")
    capture.add_argument("--capture-run", required=True, help="Approved capture run ID")
    capture.add_argument("--output", required=True)
    capture.add_argument("--as-of", required=True)
    capture.add_argument("--revision", type=int, required=True)
    capture.add_argument("--fact", action="append", help="A run fact the target declares: name=value (repeat)")
    capture.add_argument("--file", action="append", help="A run file the target declares: name=path (repeat)")
    capture.add_argument("--all", action="store_true", help="Name every document, processed or not (a forced run); "
                     "by default only documents the Change Journal does not record as processed under these rules")
    capture.set_defaults(handler=_logged_handler("prepare-capture", _clean("prepare_capture")))

    census = mdm_sub.add_parser("name-census", help="Count an SEC population and one configured full GLEIF Golden Copy "
                                "reading into a Name Census file")
    census.add_argument("--capture", required=True,
                        help="An SEC submissions capture folder: receipts.jsonl and the bronze/ documents it names")
    census.add_argument("--population", required=True,
                        help="JSON file: the receipt keys of the main submissions documents counted, which together "
                             "must be every SEC filer")
    census.add_argument("--gleif-reading", required=True,
                        help="The verified source.read output of rules/sources/gleif/census-complete-stream.yaml "
                             "over a full Golden Copy (its reading.json)")
    census.add_argument("--gleif-reading-sha256", required=True)
    census.add_argument("--gleif-metadata", required=True, help="JSON file: the archive's verified publication metadata")
    census.add_argument("--output", required=True)
    census.add_argument("--cascade", action="store_true",
                        help="Also run the Company rules' matching cascade over both sources (always, once a pass "
                             "is switched on); the census then holds its answers")
    census.add_argument("--catalog", help="The capture's exchange ticker catalog, by receipt key: the cascade reads "
                                          "each filer's tickers, as the Company chain does")
    census.set_defaults(handler=_logged_handler("name-census", _clean("name_census")))

    force = mdm_sub.add_parser("force-publish", help="Publish every current record to one consumer, changed or not "
                               "(forced pages of the current snapshot; changes no master data), and write the "
                               "publish target's input manifest")
    force.add_argument("--consumer", required=True, help="A consumer the current policy requires, not the journal")
    force.add_argument("--output", required=True, help="Folder for the pages' inputs and the manifest")
    force.add_argument("--page-size", type=int, default=10000, help="Records a page, at most 10000")
    force.add_argument("--run-id", help="Run again with the same pages (a stopped command)")
    force.add_argument("--step", default="graph-publication", help="The publish target's step name")
    force.set_defaults(handler=_logged_handler("force-publish", _clean("force_publish")))

    rebuild = mdm_sub.add_parser("rebuild-name-index", help="Owner-only resumable name-index rebuild")
    rebuild.add_argument("--limit", type=int, help="Stop after this many masters; retain resumable progress")
    rebuild.add_argument("--page-size", type=int, default=200, help="Masters per owner transaction (1 to 1000)")
    rebuild.add_argument("--restart", action="store_true", help="Restart overtaken progress from the beginning")
    rebuild.set_defaults(handler=_logged_handler("rebuild-name-index", _clean("rebuild_name_index")))
    detail = mdm_sub.add_parser("rebuild-detail-lookup", help="Owner-only resumable detail-lookup rebuild")
    detail.add_argument("--limit", type=int, help="Stop after this many masters; retain resumable progress")
    detail.add_argument("--page-size", type=int, default=200, help="Masters per owner transaction (1 to 1000)")
    detail.add_argument("--restart", action="store_true", help="Restart overtaken progress from the beginning")
    detail.set_defaults(handler=_logged_handler("rebuild-detail-lookup", _clean("rebuild_detail_lookup")))

    counts = mdm_sub.add_parser("counts", help="Print MDM entity and record counts")
    counts.set_defaults(handler=_logged_handler("counts", _clean("counts")))

    check = mdm_sub.add_parser("check-connectivity", help="Check the MDM database connection and schema")
    check.set_defaults(handler=_logged_handler("check-connectivity", _clean("check_connectivity")))


def _handle_migrate(args: argparse.Namespace) -> int:
    from edgar_warehouse.mdm.clean.connections import engine_from_env
    from edgar_warehouse.mdm.clean.store import migrate

    engine = engine_from_env("MDM_DATABASE_URL", restricted=False)
    try:
        payload = migrate(engine, application_role=args.application_role,
                          application_host=args.application_host,
                          prepared=args.prepared_store)
    finally:
        engine.dispose()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _clean(name: str) -> Callable[[argparse.Namespace], int]:
    """The MDM command function, imported when the command runs."""
    def run(args: argparse.Namespace) -> int:
        from edgar_warehouse.mdm.clean import cli

        return getattr(cli, name)(args)

    return run


def _logged_handler(command_name: str, handler: Callable[[argparse.Namespace], int]) -> Callable[[argparse.Namespace], int]:
    def _wrapped(args: argparse.Namespace) -> int:
        started_at = time.monotonic()
        emit_mdm_event("mdm_command_started", command=command_name, arguments=_safe_arguments(args))
        try:
            exit_code = handler(args)
        except Exception as exc:
            emit_mdm_event(
                "mdm_command_failed",
                command=command_name,
                duration_ms=elapsed_ms(started_at),
                error=exc.__class__.__name__,
            )
            raise
        emit_mdm_event(
            "mdm_command_completed",
            command=command_name,
            duration_ms=elapsed_ms(started_at),
            exit_code=exit_code,
        )
        return exit_code

    return _wrapped


def _safe_arguments(args: argparse.Namespace) -> dict[str, object]:
    safe: dict[str, object] = {}
    blocked_fragments = ("password", "secret", "token", "key")
    for name, value in vars(args).items():
        if name == "handler" or any(fragment in name.lower() for fragment in blocked_fragments):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[name] = value
        elif isinstance(value, (list, tuple)):
            safe[name] = [str(item) for item in value]
        else:
            safe[name] = str(value)
    return safe
