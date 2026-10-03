"""Compose owner-controlled outbox recovery outside the Change Journal core."""

from __future__ import annotations

import json


def _handle(args):
    """Deliver Bookkeeping's own pending control events for one run.

    MDM's publications are not recovered here: rerunning the run's
    `mdm.publish` worker delivers them under the run's lease (to-do 20e).
    """
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine

    engine = get_engine()
    book = configured_bookkeeping()
    try:
        # Delivery only; recovery never silently executes provider work.
        delivered, error = None, None
        try:
            delivered = book.deliver(ChangeJournal(engine), args.run_id, limit=args.limit)
        except (ConnectionError, DBAPIError, ValueError) as exc:
            error = type(exc).__name__
        status = book.status(args.run_id, limit=args.limit)
        result = {"delivered": delivered, "status": status, "delivery_error": error,
                  "pending_deliveries": status["pending_deliveries"]}
    finally:
        book.close()
        engine.dispose()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 3 if result["pending_deliveries"] or result["delivery_error"] else 0


def register(subparsers):
    from edgar_warehouse.change_journal.cli import register as register_core

    commands = register_core(subparsers)
    recovery = commands.add_parser("recover")
    owners = recovery.add_subparsers(dest="owner", required=True)
    book = owners.add_parser("bookkeeping")
    book.add_argument("run_id")
    book.add_argument("--limit", type=int, default=100)
    book.set_defaults(handler=_handle)
