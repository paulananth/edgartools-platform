"""Fresh Bookkeeping operator inspection and bounded recovery commands."""
from __future__ import annotations

import json
import os

def configured_bookkeeping():
    from .capabilities import standard_registry
    from .database import get_engine
    from .engine import Bookkeeping
    book = Bookkeeping(get_engine(), standard_registry())
    if os.environ.get("MDM_DATABASE_URL"):
        from sqlalchemy import create_engine
        from urllib.parse import unquote, urlparse
        from edgar_warehouse.mdm.clean.publication import LocalContractSink, JournalMirror
        from .mdm_capabilities import register_mdm
        from .config import Blocked

        mdm = create_engine(os.environ["MDM_DATABASE_URL"], pool_pre_ping=True)
        book.additional_engines.append(mdm)
        publishers = {}

        def publisher(spec):
            key = (spec["consumer"], spec["destination"])
            if key in publishers:
                return publishers[key]
            if spec["consumer"] == "journal" and spec["destination"] == "change-ledger":
                ledger = create_engine(os.environ["CHANGE_LEDGER_DATABASE_URL"], pool_pre_ping=True)
                book.additional_engines.append(ledger)
                publishers[key] = JournalMirror(ledger)
                return publishers[key]
            parsed = urlparse(spec["destination"])
            if spec["consumer"] in {"export", "graph"} and parsed.scheme == "file" and not parsed.netloc:
                publishers[key] = LocalContractSink(unquote(parsed.path))
                return publishers[key]
            raise Blocked("No registered hosted adapter for this publication destination")

        register_mdm(book.registry, mdm, publisher_factory=publisher)
    return book


def _handle(args):
    from sqlalchemy import create_engine
    from .database import migrate
    from .destinations import ChangeLedger, migrate_ledger, migrate_guard
    from .runner import run
    operation = args.bookkeeping_command
    if operation == "init":
        owner = create_engine(os.environ["BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL"])
        result = migrate(owner, runtime_role=args.runtime_role)
        owner.dispose()
    elif operation == "init-ledger":
        owner = create_engine(os.environ["CHANGE_LEDGER_MIGRATION_DATABASE_URL"])
        result = migrate_ledger(owner, runtime_role=args.runtime_role)
        owner.dispose()
    elif operation == "init-guard":
        owner = create_engine(os.environ["DESTINATION_MIGRATION_DATABASE_URL"])
        result = migrate_guard(owner, runtime_role=args.runtime_role)
        owner.dispose()
    else:
        book = configured_bookkeeping()
        try:
            if operation == "runs":
                result = book.runs(limit=args.limit, state=args.state)
            elif operation == "status":
                result = book.status(args.run_id, limit=args.limit)
            elif operation == "checks":
                result = book.check(args.run_id)
            elif operation == "leases":
                result = book.status(args.run_id, limit=args.limit)["leases"]
            else:
                book.resume(args.run_id)
                ledger_engine = create_engine(os.environ["CHANGE_LEDGER_DATABASE_URL"])
                try:
                    result = run(book, args.run_id, ChangeLedger(ledger_engine), limit=args.limit)
                finally:
                    ledger_engine.dispose()
        finally:
            book.close()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 3 if operation == "resume" and result["run"]["state"] != "complete" else 0


def register(subparsers):
    parser = subparsers.add_parser("bookkeeping", help="Fresh configured control; never imports legacy checkpoints")
    commands = parser.add_subparsers(dest="bookkeeping_command", required=True)
    for name in ("init", "init-ledger", "init-guard"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.set_defaults(handler=_handle)
    listing = commands.add_parser("runs", help="Find runs after a lost submission acknowledgement")
    listing.add_argument("--state", choices=("running", "waiting", "blocked", "complete"))
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler=_handle)
    for name in ("status", "checks", "leases", "resume"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=_handle)
