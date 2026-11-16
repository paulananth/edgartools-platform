#!/usr/bin/env python3
"""Drop and create again the platform's databases on a hosted instance, with the owner and the grants each had.

    set -a; . <stores folder>/connection.env; set +a
    python infra/scripts/reset-hosted-databases.py            # lists what it would drop: sizes, no values
    python infra/scripts/reset-hosted-databases.py --confirm  # drops and creates them again, empty

Uses the owner login's connection (MDM_MIGRATION_DATABASE_URL, the instance's administrator), which must be able to
create databases. The roles stay (they belong to the instance), so no password changes and no login is rotated.
Each database's owner and CONNECT list are read before it is dropped and put back after, so the runtime, registration
and any read-only logins reach it as before. Refuses while another session is connected to one of them.
The stores' schemas come next (data-operations RUNBOOK, "Initialize a hosted store", step 3). Prints names and sizes only.
"""
import argparse
import os
import sys

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm", action="store_true", help="Drop and create them again (without it, only list them)")
    args = parser.parse_args()
    url = os.environ.get("MDM_MIGRATION_DATABASE_URL")
    if not url:
        print("Source the stores folder's connection.env first (MDM_MIGRATION_DATABASE_URL is the owner login).", file=sys.stderr)
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
            if not args.confirm:
                print("Nothing dropped. Run again with --confirm to drop and create them again.")
                return 0
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
