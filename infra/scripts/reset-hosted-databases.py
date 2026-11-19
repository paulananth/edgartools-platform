#!/usr/bin/env python3
"""Drop and create again the platform's databases on a hosted instance, with the owner and the grants each had.

    set -a; . <stores folder>/owner.env; set +a
    python infra/scripts/reset-hosted-databases.py            # lists what it would drop: sizes, no values
    python infra/scripts/reset-hosted-databases.py --words "<the operator's exact words>"  # drops and creates them again

Uses the owner login's connection (DB_URL of owner.env, the instance's administrator), which must be able to
create databases. The roles stay (they belong to the instance), so no password changes and no login is rotated.
Each database's owner and CONNECT list are read before it is dropped and put back after, so the runtime, registration
and any read-only logins reach it as before. Refuses while another session is connected to one of them.
The stores' schemas come next (docs/runbooks/edgar-intelligence/init.md, "Initialize a hosted store", step 3). Prints names and sizes only.

Dropping needs a sign-off: --words is the operator's exact approval of this drop, and the run refuses without it.
The words, the ET time and what was dropped (names and sizes) are appended to reinit-approvals.log in the stores
folder (the folder of the owner.env that was sourced; STORES_FOLDER names it when it cannot be found).
"""
import argparse
import os
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.engine import make_url

DATABASES = ("mdm", "rdm", "rules", "bookkeeping", "change_journal", "silver")
PRIVILEGES = {"C": "CREATE", "T": "TEMPORARY", "c": "CONNECT"}


def grants(acl: list[str], owner: str) -> list[tuple[str, str]]:
    """(grantee, privilege) pairs of an access list other than the owner's own; an empty grantee is PUBLIC."""
    found = []
    for item in acl or []:
        grantee, rest = item.split("=", 1)
        if grantee == owner:
            continue
        for letter in rest.split("/", 1)[0]:
            found.append((grantee or "PUBLIC", PRIVILEGES[letter]))
    return found


def sign_off(path: Path, words: str, dropped: dict) -> None:
    """Append the operator's words, the ET time and what is dropped to the approvals log, private to the owner."""
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps({"at": stamp, "words": words, "dropped": dropped}) + "\n")
    path.chmod(0o600)


def approvals_log() -> Path:
    folder = os.environ.get("STORES_FOLDER") or Path.home() / ".config" / "edgartools" / "hosted"
    return Path(folder) / "reinit-approvals.log"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--words", help="Drop and create them again: the operator's exact words approving this drop "
                                        "(without it, only list them)")
    args = parser.parse_args()
    if args.words is not None and not args.words.strip():
        print("--words must hold the operator's exact approval.", file=sys.stderr)
        return 2
    url = os.environ.get("DB_URL")
    if not url:
        print("Source the stores folder's owner.env first (its DB_URL is the owner login).", file=sys.stderr)
        return 2
    engine = sa.create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    quote = engine.dialect.identifier_preparer.quote
    try:
        with engine.connect() as conn:
            held = {}
            for name in DATABASES:
                row = conn.execute(sa.text(
                    "SELECT pg_get_userbyid(datdba), datacl::text[], pg_size_pretty(pg_database_size(datname)) "
                    "FROM pg_database WHERE datname=:n"), {"n": name}).first()
                if row is None:
                    print(f"{name}: not there; it will be created with the connection login as its owner")
                    held[name] = (conn.scalar(sa.text("SELECT current_user")), [], None)
                    continue
                held[name] = (row[0], row[1], row[2])
                print(f"{name}: {row[2]}, owner {row[0]}, {len(grants(row[1], row[0]))} grants")
            busy = conn.execute(sa.text(
                "SELECT datname, count(*) FROM pg_stat_activity WHERE datname = ANY(:d) AND pid <> pg_backend_pid() GROUP BY 1"),
                {"d": list(DATABASES)}).all()
            for name, count in busy:
                print(f"{name}: {count} other session(s) connected")
            if busy:
                print("Refusing: stop every session on these databases first.", file=sys.stderr)
                return 3
            if args.words is None:
                print("Nothing dropped. A drop needs the operator's sign-off: run again with --words \"<their exact words>\".")
                return 0
            sign_off(approvals_log(), args.words.strip(), {n: held[n][2] for n in held})
            for name, (owner, acl, _) in held.items():
                conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {quote(name)} WITH (FORCE)")
                conn.exec_driver_sql(f"CREATE DATABASE {quote(name)} OWNER {quote(owner)}")
                conn.exec_driver_sql(f"REVOKE ALL ON DATABASE {quote(name)} FROM PUBLIC")
                for grantee, privilege in grants(acl, owner):
                    who = grantee if grantee == "PUBLIC" else quote(grantee)
                    conn.exec_driver_sql(f"GRANT {privilege} ON DATABASE {quote(name)} TO {who}")
                print(f"{name}: created again, {len(grants(acl, owner))} grants put back")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
