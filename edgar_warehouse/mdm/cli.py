"""CLI subcommand: `edgar-warehouse mdm ...`, MDM only.

Commands: migrate, check-connectivity, counts,
prepare-capture, name-count, rebuild, rebuild-name-index and rebuild-detail-lookup. The legacy MDM commands and their tables are
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
    capture.set_defaults(handler=_logged_handler("prepare-capture", _command("prepare_capture")))

    name_count = mdm_sub.add_parser("name-count", help="Count an SEC population and one configured full GLEIF Golden Copy "
                                "reading into a Name Count file")
    name_count.add_argument("--capture", required=True,
                        help="An SEC submissions capture folder: receipts.jsonl and the bronze/ documents it names")
    name_count.add_argument("--population", required=True,
                        help="JSON file: the receipt keys of the main submissions documents counted, which together "
                             "must be every SEC filer")
    name_count.add_argument("--gleif-reading", required=True,
                        help="The verified source.read output of rules/sources/gleif/name-count-complete-stream.yaml "
                             "over a full Golden Copy (its reading.json)")
    name_count.add_argument("--gleif-reading-sha256", required=True)
    name_count.add_argument("--gleif-metadata", required=True, help="JSON file: the archive's verified publication metadata")
    name_count.add_argument("--output", required=True)
    name_count.add_argument("--cascade", action="store_true",
                        help="Also run the Company rules' matching cascade over both sources (always, once a pass "
                             "is switched on); the name count then holds its answers")
    name_count.add_argument("--catalog", help="The capture's exchange ticker catalog, by receipt key: the cascade reads "
                                          "each filer's tickers, as the Company chain does")
    name_count.set_defaults(handler=_logged_handler("name-count", _command("name_count")))

    replay = mdm_sub.add_parser("rebuild", help="Replay every stored record into the mastering tables; a stopped replay "
                                "runs again and skips what is done")
    replay.add_argument("--policy-digest", required=True, help="The registered merge rules to replay under")
    replay.add_argument("--check", action="store_true", help="Compare the mastering tables with the old masters, counts only")
    replay.set_defaults(handler=_logged_handler("rebuild", _command("rebuild")))
    lookups = mdm_sub.add_parser("build-lookups", help="Bring the name, detail and cross-reference lookups "
                                 "up to the last load; a stopped build resumes")
    lookups.set_defaults(handler=_logged_handler("build-lookups", _command("build_lookups")))
    rebuild = mdm_sub.add_parser("rebuild-name-index", help="Owner-only resumable name-index rebuild")
    rebuild.add_argument("--limit", type=int, help="Stop after this many masters; retain resumable progress")
    rebuild.add_argument("--page-size", type=int, default=200, help="Masters per owner transaction (1 to 1000)")
    rebuild.add_argument("--restart", action="store_true", help="Restart overtaken progress from the beginning")
    rebuild.set_defaults(handler=_logged_handler("rebuild-name-index", _command("rebuild_name_index")))
    detail = mdm_sub.add_parser("rebuild-detail-lookup", help="Owner-only resumable detail-lookup rebuild")
    detail.add_argument("--limit", type=int, help="Stop after this many masters; retain resumable progress")
    detail.add_argument("--page-size", type=int, default=200, help="Masters per owner transaction (1 to 1000)")
    detail.add_argument("--restart", action="store_true", help="Restart overtaken progress from the beginning")
    detail.set_defaults(handler=_logged_handler("rebuild-detail-lookup", _command("rebuild_detail_lookup")))
    steward = mdm_sub.add_parser("steward", help="Steward decisions on master data")
    steward_sub = steward.add_subparsers(dest="steward_command", required=True)
    split = steward_sub.add_parser("split", help="Split a consolidation a matching rule made: both masters return and "
                                   "the pair becomes a Match Exclusion. Shows what it would do; writes only with --confirm")
    split.add_argument("--merge", required=True, help="The merge decision's id, as `edgar-warehouse context` shows it")
    split.add_argument("--by", required=True, help="Who splits it, recorded on the decision")
    split.add_argument("--reason", required=True, help="Why, in words, recorded on the decision")
    split.add_argument("--policy-digest", required=True, help="The registered merge rules the masters are replayed under")
    split.add_argument("--confirm", action="store_true", help="Write the split (without it, only show it)")
    split.set_defaults(handler=_logged_handler("steward-split", _command("steward_split")))
    resolve = steward_sub.add_parser("resolve", help="Close a `conflicting_identifiers` review: the record reached golden "
                                     "records its identifiers disagree on. `merge`: they are one (the older survives, the "
                                     "record joins it). `exclude`: the record is a different one and gets its own. Shows what "
                                     "it would do; writes only with --confirm")
    resolve.add_argument("--subject", required=True, help="The waiting record's subject, as `edgar-warehouse context` shows it")
    resolve.add_argument("--result", required=True, choices=("merge", "exclude"))
    resolve.add_argument("--by", required=True, help="Who resolves it, recorded on the decisions")
    resolve.add_argument("--reason", required=True, help="Why, in words, recorded on the decisions")
    resolve.add_argument("--policy-digest", required=True, help="The registered merge rules the golden records are written under")
    resolve.add_argument("--confirm", action="store_true", help="Write the resolution (without it, only show it)")
    resolve.set_defaults(handler=_logged_handler("steward-resolve", _command("steward_resolve")))

    clear = mdm_sub.add_parser("clear-source", help="Restart one source from empty: remove its source records and the golden "
                               "records only it made. Shows the counts and rolls back; writes only with --confirm")
    clear.add_argument("--source", required=True, help="The source's dataset code, e.g. openfigi.security.v4")
    clear.add_argument("--confirm", action="store_true", help="Write the clearing (without it, only count it)")
    clear.set_defaults(handler=_logged_handler("clear-source", _command("clear_source")))

    counts = mdm_sub.add_parser("counts", help="Print MDM entity and record counts")
    counts.set_defaults(handler=_logged_handler("counts", _command("counts")))

    check = mdm_sub.add_parser("check-connectivity", help="Check the MDM database connection and schema")
    check.set_defaults(handler=_logged_handler("check-connectivity", _command("check_connectivity")))


def _handle_migrate(args: argparse.Namespace) -> int:
    from edgar_warehouse.mdm.connections import engine_from_env
    from edgar_warehouse.mdm.store import migrate

    engine = engine_from_env("MDM_DATABASE_URL", restricted=False)
    try:
        payload = migrate(engine, application_role=args.application_role,
                          application_host=args.application_host,
                          prepared=args.prepared_store)
    finally:
        engine.dispose()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command(name: str) -> Callable[[argparse.Namespace], int]:
    """The MDM command function, imported when the command runs."""
    def run(args: argparse.Namespace) -> int:
        from edgar_warehouse.mdm import commands

        return getattr(commands, name)(args)

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
