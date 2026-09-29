"""Fresh Bookkeeping operator inspection and bounded recovery commands."""
from __future__ import annotations

import json
import os

def configured_bookkeeping():
    from .capabilities import standard_registry
    from .database import get_engine
    from .engine import Bookkeeping
    book = Bookkeeping(get_engine(), standard_registry())
    if os.environ.get("CHANGE_JOURNAL_DATABASE_URL"):
        from edgar_warehouse.change_journal.capture import register_capture
        from edgar_warehouse.change_journal.store import ChangeJournal, get_engine as journal_engine
        journal = journal_engine()
        book.additional_engines.append(journal)
        register_capture(book.registry, ChangeJournal(journal))
    from edgar_warehouse.change_journal.source_evidence import register_source_evidence
    register_source_evidence(book.registry)
    from .company import register_company_expansion, register_company_silver, register_company_mdm_preparation
    register_company_expansion(book.registry)
    register_company_silver(book.registry)
    register_company_mdm_preparation(book.registry)
    if os.environ.get("MDM_DATABASE_URL"):
        from sqlalchemy import create_engine
        from urllib.parse import unquote, urlparse
        from edgar_warehouse.mdm.clean.publication import LocalContractSink
        from edgar_warehouse.change_journal.publication import JournalPublisher
        from edgar_warehouse.change_journal.store import ChangeJournal, get_engine as journal_engine
        from .mdm_capabilities import register_mdm
        from .config import Blocked

        mdm = create_engine(os.environ["MDM_DATABASE_URL"], pool_pre_ping=True)
        book.additional_engines.append(mdm)
        publishers = {}

        def publisher(spec):
            key = (spec["consumer"], spec["destination"])
            if key in publishers:
                return publishers[key]
            if spec["consumer"] == "journal" and spec["destination"] == "change-journal":
                journal = journal_engine()
                book.additional_engines.append(journal)
                publishers[key] = JournalPublisher(ChangeJournal(journal), mdm, book)
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
    from .destinations import migrate_guard
    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine as journal_engine
    from .runner import run
    operation = args.bookkeeping_command
    if operation == "prepare":
        from .company import FEED, SOURCE, prepare_company
        from .config import Blocked
        if (args.source, args.feed) != (SOURCE, FEED):
            raise Blocked("Only SEC Company submissions preparation is active")
        result = prepare_company(
            scope_ref={"uri": args.scope_manifest, "sha256": args.scope_sha256},
            support_ref={"uri": args.support_manifest, "sha256": args.support_sha256},
            output_root=args.output_root)
    elif operation in {"init", "migrate"}:
        owner = create_engine(os.environ["BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(
                owner,
                runtime_role=args.runtime_role,
                existing_only=operation == "migrate",
            )
        finally:
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
                ledger_engine = journal_engine()
                try:
                    result = run(book, args.run_id, ChangeJournal(ledger_engine), limit=args.limit)
                finally:
                    ledger_engine.dispose()
        finally:
            book.close()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 3 if operation == "resume" and result["run"]["state"] != "complete" else 0


def register(subparsers):
    parser = subparsers.add_parser("bookkeeping", help="Fresh configured control; never imports legacy checkpoints")
    commands = parser.add_subparsers(dest="bookkeeping_command", required=True)
    for name in ("init", "migrate", "init-guard"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.set_defaults(handler=_handle)
    prepare = commands.add_parser("prepare", help="Pin a bounded Company input without requesting SEC or starting a run")
    for name in ("source", "feed", "scope-manifest", "scope-sha256", "support-manifest",
                 "support-sha256", "output-root"):
        prepare.add_argument("--" + name, required=True)
    prepare.set_defaults(handler=_handle)
    listing = commands.add_parser("runs", help="Find runs after a lost submission acknowledgement")
    listing.add_argument("--state", choices=("running", "waiting", "blocked", "complete"))
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler=_handle)
    for name in ("status", "checks", "leases", "resume"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=_handle)
