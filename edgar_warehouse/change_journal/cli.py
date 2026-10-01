"""Bounded journal inspection and owner-delegated delivery recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _handle(args):
    from sqlalchemy import create_engine
    from sqlalchemy.exc import DBAPIError

    from .database import migrate
    from .store import ChangeJournal, get_engine

    if args.journal_command in {"init", "migrate"}:
        owner = create_engine(os.environ["CHANGE_JOURNAL_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(
                owner,
                runtime_role=args.runtime_role,
                existing_only=args.journal_command == "migrate",
            )
        finally:
            owner.dispose()
    else:
        engine = get_engine()
        journal = ChangeJournal(engine)
        try:
            if args.journal_command == "status":
                result = journal.status(source=args.source, feed=args.feed)
            elif args.journal_command == "events":
                result = journal.list(
                    source=args.source,
                    feed=args.feed,
                    run_id=args.run_id,
                    limit=args.limit,
                    after=args.after,
                )
            elif args.journal_command == "verify":
                result = journal.verify(json.loads(Path(args.receipt).read_text()))
            elif args.owner == "bookkeeping":
                from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping

                book = configured_bookkeeping()
                try:
                    # Delivery only; recovery never silently executes provider work.
                    delivered = None
                    error = None
                    try:
                        delivered = book.deliver(journal, args.run_id, limit=args.limit)
                    except (ConnectionError, DBAPIError, ValueError) as exc:
                        error = type(exc).__name__
                    status = book.status(args.run_id, limit=args.limit)
                    result = {
                        "delivered": delivered,
                        "status": status,
                        "delivery_error": error,
                    }
                    result["pending_deliveries"] = result["status"][
                        "pending_deliveries"
                    ]
                finally:
                    book.close()
            else:
                from edgar_warehouse.mdm.clean.cli import engine_from_env
                from edgar_warehouse.mdm.clean.store import Store

                from .publication import JournalPublisher

                mdm = engine_from_env("MDM_DATABASE_URL")
                from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping

                book = configured_bookkeeping()
                try:
                    store = Store(mdm)
                    publisher = JournalPublisher(journal, mdm, book)
                    publisher.validate_batch(args.batch_id)
                    delivered = 0
                    # A specific batch retains the owning publication fence and
                    # original key. Never enumerate or redirect legacy backlog.
                    if store.deliver_one(
                        "journal", args.worker, publisher, batch_id=args.batch_id
                    ):
                        delivered = 1
                    with mdm.connect() as conn:
                        from sqlalchemy import text

                        pending = conn.scalar(
                            text(
                                "SELECT count(*) FROM mdm.outbox WHERE batch_id=:b AND consumer='journal' AND verified_at IS NULL"
                            ),
                            {"b": args.batch_id},
                        )
                    result = {
                        "delivered": delivered,
                        "batch_id": args.batch_id,
                        "pending_deliveries": pending,
                    }
                finally:
                    book.close()
                    mdm.dispose()
        finally:
            engine.dispose()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return (
        3
        if args.journal_command == "recover"
        and (result["pending_deliveries"] or result.get("delivery_error"))
        else 0
    )


def register(subparsers):
    parser = subparsers.add_parser(
        "change-journal", help="Fresh shared decisions and verified outcomes"
    )
    commands = parser.add_subparsers(dest="journal_command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--runtime-role", required=True)
    init.set_defaults(handler=_handle)
    migration = commands.add_parser("migrate")
    migration.add_argument("--runtime-role", required=True)
    migration.set_defaults(handler=_handle)
    for name in ("status", "events"):
        command = commands.add_parser(name)
        command.add_argument("--source")
        command.add_argument("--feed")
        if name == "events":
            command.add_argument("--run-id")
            command.add_argument("--limit", type=int, default=100)
            command.add_argument("--after", type=int, default=0)
        command.set_defaults(handler=_handle)
    verify = commands.add_parser("verify")
    verify.add_argument("receipt", help="Retained JSON receipt")
    verify.set_defaults(handler=_handle)
    recovery = commands.add_parser("recover")
    owners = recovery.add_subparsers(dest="owner", required=True)
    book = owners.add_parser("bookkeeping")
    book.add_argument("run_id")
    book.add_argument("--limit", type=int, default=100)
    book.set_defaults(handler=_handle)
    mdm = owners.add_parser("mdm")
    mdm.add_argument("batch_id")
    mdm.add_argument("--worker", required=True)
    mdm.set_defaults(handler=_handle)
