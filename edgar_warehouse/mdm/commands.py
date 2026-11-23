"""MDM command handlers: preparation, queries and publication requests."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from sqlalchemy import text

from .connections import mdm_engine


def prepare_capture(args) -> int:
    from .target_manifest import run_arguments, write_manifest

    facts, run_files = run_arguments(args.fact, args.file)
    report = write_manifest(
        facts=facts,
        run_files=run_files,
        source=args.source,
        target=args.target,
        capture=args.capture,
        documents=args.documents,
        capture_run=args.capture_run,
        output=args.output,
        as_of=args.as_of,
        revision=args.revision,
        force=args.all,
    )
    print(json.dumps(report, sort_keys=True))
    return 0


def steward_split(args) -> int:
    """Split a consolidation a rule made (ticket 142): previews unless `--confirm`."""
    from functools import cache

    from edgar_warehouse.mastering import steward
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.rules import registry
    from edgar_warehouse.workers.mastering_merge import _settings

    at = datetime.now(timezone.utc).isoformat()
    engine = mdm_engine(restricted=True)
    rules = registry.engine()
    db = open_store(engine)
    manifest = {"policy_digest": args.policy_digest, "as_of": at}
    try:
        report = steward.split(db, cache(lambda kind: _settings(rules, manifest, kind)), merge_id=args.merge,
                               actor=args.by, reason=args.reason, at=at, confirm=args.confirm)
    finally:
        db.close()
        engine.dispose()
        rules.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def steward_resolve(args) -> int:
    """Close a `conflicting_identifiers` review (ticket 207): previews unless `--confirm`."""
    from functools import cache

    from edgar_warehouse.mastering import steward
    from edgar_warehouse.mastering.store import open_store
    from edgar_warehouse.rules import registry
    from edgar_warehouse.workers.mastering_merge import _settings

    at = datetime.now(timezone.utc).isoformat()
    engine = mdm_engine(restricted=True)
    rules = registry.engine()
    db = open_store(engine)
    manifest = {"policy_digest": args.policy_digest, "as_of": at}
    try:
        report = steward.resolve(db, cache(lambda kind: _settings(rules, manifest, kind)), subject=args.subject,
                                 result=args.result, actor=args.by, reason=args.reason, at=at, confirm=args.confirm)
    finally:
        db.close()
        engine.dispose()
        rules.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def open_mastering_runs() -> list[str]:
    """The Bookkeeping runs of a mastering target that are running. A worker between two merge transactions holds no kind lock,
    so the store's own quiet check cannot see that a load goes on: this is the other half of it."""
    from edgar_warehouse.bookkeeping.clean import cli as bookkeeping

    book = bookkeeping.configured_bookkeeping()
    try:
        return [row["run_id"] for row in book.runs(limit=1000, state="running") if row.get("target") == "mastering"]
    finally:
        book.close()


def _refuse_while_loading(action: str) -> bool:
    if open := open_mastering_runs():
        print(f"{action} stopped: a mastering load is running ({len(open)} open run{'s' if len(open) != 1 else ''}: "
              f"{', '.join(open[:3])}); wait for the loads to end", file=sys.stderr)
        return True
    return False


def clear_source(args) -> int:
    """Restart one source from empty (the `data-operations` skill): previews unless `--confirm`."""
    if _refuse_while_loading("Clearing"):
        return 1
    from edgar_warehouse.mastering import clear
    from edgar_warehouse.mastering.store import open_store

    # The owner login: the runtime role may not delete decisions, which are the record of what was decided.
    from edgar_warehouse.database_connections import owner_engine

    from edgar_warehouse.mastering.store import NotQuiet

    engine = owner_engine("mdm")
    db = open_store(engine)
    try:
        report = clear.clear(db, args.source, confirm=args.confirm)
    except (ValueError, NotQuiet) as refused:
        print(f"Clearing stopped: {refused}", file=sys.stderr)
        return 1
    finally:
        db.close()
        engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def _print_mdm_report(read) -> int:
    """Run one read on the MDM database as the application role and print it."""
    mdm = mdm_engine()
    try:
        with mdm.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
            report = read(conn)
    finally:
        mdm.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


def check_connectivity(args) -> int:
    def report(conn):
        return {"sql": conn.scalar(text("SELECT 1")) == 1,
                "migrations": conn.scalar(text("SELECT count(*) FROM mdm.migration"))}

    return _print_mdm_report(report)


def build_lookups(args) -> int:
    from edgar_warehouse.mastering import lookups
    from edgar_warehouse.mastering.store import NotQuiet, open_store

    if _refuse_while_loading("Building the lookups"):
        return 1
    engine = mdm_engine(restricted=True)
    db = open_store(engine)
    try:
        report = lookups.build(db, lambda built: print(json.dumps({"masters": built}), file=sys.stderr, flush=True))
    except NotQuiet as refused:
        print(f"Building the lookups stopped: {refused}", file=sys.stderr)
        return 1
    finally:
        db.close()
        engine.dispose()
    print(json.dumps(report, sort_keys=True))
    return 0


