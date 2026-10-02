"""Compose owner-controlled outbox recovery outside the Change Journal core."""

from __future__ import annotations

import json


def _handle(args):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine

    engine = get_engine()
    journal = ChangeJournal(engine)
    try:
        if args.owner == "bookkeeping":
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

            from edgar_warehouse.mdm.clean.journal_delivery import JournalPublisher

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
    return 3 if result["pending_deliveries"] or result.get("delivery_error") else 0


def register(subparsers):
    from edgar_warehouse.change_journal.cli import register as register_core

    commands = register_core(subparsers)
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
