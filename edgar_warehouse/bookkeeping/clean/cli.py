"""Bookkeeping commands: control only, and the task protocol workers pull.

Workers and verifiers are other processes. They call `claim`, `renew`,
`report`, `fail`, `verifications` and `admit` and read the JSON these print;
Bookkeeping never names, imports or starts a worker (mastering to-do 20a).
"""
from __future__ import annotations

import json
import os
import sys


def configured_bookkeeping():
    from .database import get_engine
    from .engine import Bookkeeping
    return Bookkeeping(get_engine())


def _document(path: str) -> dict:
    """An envelope or verification document, from a file or `-` (stdin)."""
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    return json.loads(text)


def _handle(args):
    from sqlalchemy import create_engine
    from .database import migrate
    from .destinations import migrate_guard
    operation = args.bookkeeping_command
    if operation in {"init", "migrate"}:
        owner = create_engine(os.environ["BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL"])
        try:
            result = migrate(
                owner,
                runtime_role=args.runtime_role,
                existing_only=operation == "migrate",
            )
        finally:
            owner.dispose()
    elif operation == "grant-profile":
        from .database import grant_profile
        owner = create_engine(os.environ["BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL"])
        try:
            result = grant_profile(owner, profile=args.profile, worker=args.worker, verifier=args.verifier)
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
            elif operation == "resume":
                result = book.resume(args.run_id)
            elif operation == "claim":
                result = book.tasks(args.run_id, args.profile, limit=args.limit)
            elif operation == "verifications":
                result = book.verifications(args.run_id, args.profile, limit=args.limit)
            elif operation == "renew":
                result = book.renew(_document(args.envelope))
            elif operation == "report":
                result = book.report(_document(args.envelope), {"uri": args.candidate, "sha256": args.sha256},
                                     args.runtime)
            elif operation == "fail":
                book.fail(_document(args.envelope), args.message)
                result = {"failed": True}
            elif operation == "admit":
                result = book.admit(_document(args.verification), {"uri": args.report, "sha256": args.sha256})
            else:  # finalize: deliver control's events, then record the run's checks
                from edgar_warehouse.change_journal.store import ChangeJournal, get_engine as journal_engine
                ledger = journal_engine()
                try:
                    book.deliver(ChangeJournal(ledger), args.run_id, limit=args.limit)
                finally:
                    ledger.dispose()
                result = book.finalize(args.run_id)
        finally:
            book.close()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 3 if operation in ("resume", "finalize") and result["run"]["state"] != "complete" else 0


def register(subparsers):
    parser = subparsers.add_parser("bookkeeping", help="Fresh configured control; never imports legacy checkpoints")
    commands = parser.add_subparsers(dest="bookkeeping_command", required=True)
    for name in ("init", "migrate", "init-guard"):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.set_defaults(handler=_handle)
    grant = commands.add_parser("grant-profile", help="Let one login report a profile's work and another verify it")
    grant.add_argument("--profile", required=True)
    grant.add_argument("--worker", required=True, help="The worker's database login")
    grant.add_argument("--verifier", required=True, help="The verifier's database login (not the worker's)")
    grant.set_defaults(handler=_handle)
    listing = commands.add_parser("runs", help="Find runs after a lost submission acknowledgement")
    listing.add_argument("--state", choices=("running", "waiting", "blocked", "complete"))
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler=_handle)
    for name in ("status", "checks", "leases", "resume", "finalize"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("--limit", type=int, default=100)
        command.set_defaults(handler=_handle)
    for name, help_text in (("claim", "Claim task envelopes for a worker profile"),
                            ("verifications", "List reported candidates for a verifier")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("run_id")
        command.add_argument("--profile", required=True)
        command.add_argument("--limit", type=int, default=10)
        command.set_defaults(handler=_handle)
    renew = commands.add_parser("renew", help="Renew a task envelope's lease")
    renew.add_argument("--envelope", required=True, help="The envelope file, or - for stdin")
    renew.set_defaults(handler=_handle)
    report = commands.add_parser("report", help="Report a worker's candidate output")
    report.add_argument("--envelope", required=True)
    report.add_argument("--candidate", required=True, help="The candidate's URI")
    report.add_argument("--sha256", required=True)
    report.add_argument("--runtime", required=True, help="The worker runtime's digest")
    report.set_defaults(handler=_handle)
    fail = commands.add_parser("fail", help="Give up a task attempt")
    fail.add_argument("--envelope", required=True)
    fail.add_argument("--message", required=True)
    fail.set_defaults(handler=_handle)
    admit = commands.add_parser("admit", help="Admit a verifier's report and complete the unit")
    admit.add_argument("--verification", required=True)
    admit.add_argument("--report", required=True, help="The verification report's URI")
    admit.add_argument("--sha256", required=True)
    admit.set_defaults(handler=_handle)


def main(argv=None) -> int:
    """`edgar-bookkeeping`: the control commands alone, for the control-only
    package; `edgar-warehouse bookkeeping` reaches the same commands."""
    import argparse
    parser = argparse.ArgumentParser(prog="edgar-bookkeeping")
    commands = parser.add_subparsers(dest="command", required=True)
    register(commands)
    args = parser.parse_args(["bookkeeping", *(sys.argv[1:] if argv is None else argv)])
    return args.handler(args)
