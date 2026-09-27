#!/usr/bin/env python3
"""Create fresh local control stores; never import or reset legacy state.

Run with uv run --extra mdm infra/scripts/provision-clean-bookkeeping.py.
BOOKKEEPING_CLEAN_ADMIN_DATABASE_URL names the admin connection (postgres DB),
BOOKKEEPING_CLEAN_RUNTIME_PASSWORD supplies the new runtime login's password.
Optional --rules also uses RULES_AGENT_PASSWORD. No versions are activated.
"""
from __future__ import annotations

import argparse
import json
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from edgar_warehouse.bookkeeping.clean.database import migrate
from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules.db import migrate as migrate_rules


def provision(admin_url: str, *, rules: bool = False):
    admin = create_engine(admin_url, hide_parameters=True)
    requested = [("bookkeeping_clean", "bookkeeping_clean_owner", "bookkeeping_clean_runtime", "BOOKKEEPING_CLEAN_RUNTIME_PASSWORD")]
    if rules:
        requested.append(("rules", "rules_owner", "rules_agent", "RULES_AGENT_PASSWORD"))
    quote = admin.dialect.identifier_preparer.quote
    result = {}
    try:
        # Resolve inputs before creating anything; credentials are never printed.
        passwords = {env: os.environ[env] for _, _, _, env in requested}
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if int(conn.scalar(text("SHOW server_version_num"))) // 10000 != 16:
                raise Blocked("Local control provisioning requires PostgreSQL 16")
            for database, owner, runtime, env in requested:
                for role, login in ((owner, False), (runtime, True)):
                    exists = conn.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolcanlogin FROM pg_roles WHERE rolname=:r"), {"r": role}).first()
                    if exists:
                        if any(exists[:3]) or exists[3] != login:
                            raise Blocked("An existing control role has incompatible privileges")
                        continue
                    if login:
                        conn.execute(text(f"CREATE ROLE {quote(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :pw"), {"pw": passwords[env]})
                    else:
                        conn.exec_driver_sql(f"CREATE ROLE {quote(role)} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
                existing_owner = conn.scalar(text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=:d"), {"d": database})
                if existing_owner is not None and existing_owner != owner:
                    raise Blocked(f"Existing {database} database has another owner; refusing to adopt it")
                if existing_owner is None:
                    conn.exec_driver_sql(f"CREATE DATABASE {quote(database)} OWNER {quote(owner)}")
            if rules and not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='rules_approver')")):
                conn.exec_driver_sql("CREATE ROLE rules_approver NOLOGIN")
        for database, owner, runtime, _ in requested:
            engine = create_engine(make_url(admin_url).set(database=database), hide_parameters=True)

            @event.listens_for(engine, "connect")
            def owner_role(connection, _, selected=owner):
                with connection.cursor() as cursor:
                    cursor.execute(f"SET ROLE {quote(selected)}")
                connection.commit()

            try:
                result[database] = migrate(engine, runtime_role=runtime) if database == "bookkeeping_clean" else migrate_rules(engine, agent_role=runtime)
            finally:
                engine.dispose()
    finally:
        admin.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", action="store_true", help="Also create the one-table Rules store, without activating any version")
    args = parser.parse_args()
    result = provision(os.environ["BOOKKEEPING_CLEAN_ADMIN_DATABASE_URL"], rules=args.rules)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
