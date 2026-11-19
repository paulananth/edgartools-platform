"""Journal-only initialization, bounded inspection and receipt verification.

Producer outbox recovery is composed by the application CLI, outside this core.
This module also runs independently with python -m edgar_warehouse.change_journal.cli.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _owner_url() -> str:
    """The owner file's `DB_URL` with this store's database (the Journal imports nothing outside itself, so it reads it itself);
    a `DB_URL` that already names a database keeps it."""
    from sqlalchemy.engine import make_url

    value = os.environ.get("DB_URL")
    if not value:
        raise KeyError("DB_URL is not set: source the owner file of the stores folder (its value is never printed)")
    url = make_url(value)
    return (url if url.database else url.set(database="change_journal")).render_as_string(hide_password=False)


def _handle(args):
    from .database import migrate
    from .store import ChangeJournal, get_engine

    if args.journal_command == "init":
        owner = get_engine(_owner_url())
        try:
            result = migrate(owner, runtime_role=args.runtime_role,
                             database_name=args.database_name)
        finally:
            owner.dispose()
    else:
        engine = get_engine()
        journal = ChangeJournal(engine)
        try:
            if args.journal_command == "status":
                result = journal.status(source=args.source, feed=args.feed)
            elif args.journal_command == "events":
                result = journal.list(source=args.source, feed=args.feed,
                                      run_id=args.run_id, limit=args.limit, after=args.after)
            elif args.journal_command == "verify":
                result = journal.verify(json.loads(Path(args.receipt).read_text()))
            else:
                raise ValueError("Unsupported journal-only operation")
        finally:
            engine.dispose()
    print(json.dumps(result, default=str, sort_keys=True, indent=2))
    return 0


def _commands(parser):
    commands = parser.add_subparsers(dest="journal_command", required=True)
    for name in ("init",):
        command = commands.add_parser(name)
        command.add_argument("--runtime-role", required=True)
        command.add_argument("--database-name", default="change_journal", help="The configured isolated Journal database")
        command.set_defaults(handler=_handle)
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
    return commands


def register(subparsers):
    parser = subparsers.add_parser("change-journal", help="Fresh shared decisions and verified outcomes")
    return _commands(parser)


def build_parser():
    parser = argparse.ArgumentParser(prog="edgar-change-journal", description=__doc__)
    _commands(parser)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
