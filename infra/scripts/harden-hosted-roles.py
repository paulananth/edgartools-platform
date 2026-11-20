#!/usr/bin/env python3
"""Put the access guards on the hosted instance's login roles: a connection limit, timeouts, a memory ceiling and the audit classes.

    set -a; . <stores folder>/owner.env; set +a
    python infra/scripts/harden-hosted-roles.py            # lists what differs: role and setting names, no values of the data
    python infra/scripts/harden-hosted-roles.py --confirm  # applies the differences

It also gives Snowflake's mirror login (snowflake_system) CONNECT on each mirrored store, which PUBLIC does not hold.
Each guard is one control of the access audit (skills/access-audit): DB-05 a connection limit on every login, TMO a bound on
statements and idle transactions, LOG the audit classes for the logins that change schemas, policy or approvals. It uses the
owner login (the owner file), changes only roles that exist, and is safe to run again: a role already at its guard
is left alone. The loader's work_mem is a ceiling per sort or hash step and session, so ten merge workers with several steps
each cannot ask for more than the instance holds. A setting the platform refuses to a non-superuser is reported by name and
the run exits 1; nothing is worked around with a superuser.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import sqlalchemy as sa
from sqlalchemy.engine import make_url

WRITER = {"write", "ddl", "role"}
GUARDS = {
    "edgar_loader": {"limit": 300, "settings": {"work_mem": "64MB", "statement_timeout": "4h", "idle_in_transaction_session_timeout": "10min",
                                                 "pgaudit.log": "ddl,role"}},
    "governance": {"limit": 10, "settings": {"statement_timeout": "5min", "idle_in_transaction_session_timeout": "5min",
                                              "pgaudit.log": "write,ddl,role"}},
    "ops_reader": {"limit": 10, "settings": {"statement_timeout": "60s", "idle_in_transaction_session_timeout": "60s"}},
    # The catalog reader (auto-ontology's catalog-readers.py): SELECT on the exposed tables, nothing else.
    "discovery_reader": {"limit": 10, "settings": {"statement_timeout": "60s", "idle_in_transaction_session_timeout": "60s"}},
}
VALUE = re.compile(r"^[0-9A-Za-z,. ]+$")
# The stores a managed Snowflake mirror reads, and the system login Snowflake's mirror connects as. PUBLIC holds no CONNECT on
# the stores, so without this grant a mirror fails with "permission denied for database".
MIRRORED = ("data",)  # the data database: mdm, rdm and silver, each in its schema
MIRROR_LOGIN = "snowflake_system"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def plan(limits: dict[str, int], settings: dict[str, dict[str, str]], guards: dict = GUARDS) -> list[tuple[str, str, str]]:
    """(role, what, sql) for each guard a role does not hold yet. A role that does not exist is skipped."""
    steps = []
    for role, guard in guards.items():
        if role not in limits:
            continue
        if limits[role] != guard["limit"]:
            steps.append((role, "connection limit", f"ALTER ROLE {quote(role)} CONNECTION LIMIT {int(guard['limit'])}"))
        for key, value in guard["settings"].items():
            if not VALUE.match(value):
                raise ValueError(f"unsafe value for {key}")
            if settings.get(role, {}).get(key) != value:
                steps.append((role, key, f"ALTER ROLE {quote(role)} SET {key} = '{value}'"))
    return steps


def mirror_access(acls: dict[str, list[str] | None], login: str = MIRROR_LOGIN) -> list[tuple[str, str, str]]:
    """(login, what, sql) for each mirrored database whose access list does not give the mirror's login CONNECT."""
    steps = []
    for database in MIRRORED:
        if database not in acls:
            continue
        held = [item.split("/")[0] for item in acls[database] or []]
        if not any(entry.split("=")[0] == login and "c" in entry.split("=")[1] for entry in held):
            steps.append((login, f"connect on {database}", f"GRANT CONNECT ON DATABASE {quote(database)} TO {quote(login)}"))
    return steps


def read(conn) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    limits = {r[0]: r[1] for r in conn.execute(sa.text("select rolname, rolconnlimit from pg_roles where rolcanlogin"))}
    settings: dict[str, dict[str, str]] = {}
    for role, config in conn.execute(sa.text("select r.rolname, s.setconfig from pg_db_role_setting s join pg_roles r on r.oid = s.setrole "
                                             "where s.setdatabase = 0")):
        settings[role] = dict(item.split("=", 1) for item in config)
    return limits, settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--confirm", action="store_true", help="Apply the differences (without it, only list them)")
    args = parser.parse_args(argv)
    from edgar_warehouse.database_connections import instance_url

    try:
        url = instance_url()
    except KeyError as missing:
        sys.exit(f"{missing.args[0]} (source the stores folder's owner.env)")
    engine = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    failed = 0
    with engine.connect() as conn:
        steps = plan(*read(conn))
        roles = {r[0] for r in conn.execute(sa.text("select rolname from pg_roles"))}
        if MIRROR_LOGIN in roles:
            acls = dict(conn.execute(sa.text("select datname, datacl::text[] from pg_database")).all())
            steps += mirror_access(acls)
        for role, what, sql in steps:
            if not args.confirm:
                print(f"would set {role}: {what}")
                continue
            try:
                conn.execute(sa.text(sql))
                print(f"set {role}: {what}")
            except sa.exc.DBAPIError as exc:
                failed += 1
                print(f"refused {role}: {what} ({getattr(exc.orig, 'pgcode', 'error')})")
    print(f"{len(steps)} guards {'applied' if args.confirm else 'to apply'}, {failed} refused" if steps else "every login role holds its guards")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
