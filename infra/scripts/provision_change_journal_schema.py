"""Provision only the fresh journal, never legacy ledger tables or history."""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine

from edgar_warehouse.change_journal.database import migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-role", required=True)
    args = parser.parse_args()
    owner = create_engine(os.environ["CHANGE_JOURNAL_MIGRATION_DATABASE_URL"])
    try:
        print(
            json.dumps(migrate(owner, runtime_role=args.runtime_role), sort_keys=True)
        )
    finally:
        owner.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
