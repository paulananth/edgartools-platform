"""Idempotent provisioning for the bookkeeping store's 11 Postgres tables.

DuckDB Retirement Cutover Ticket 02. Reflects the schema straight from
`edgar_warehouse.bookkeeping.models`' SQLAlchemy models (the same models
BookkeepingStore itself is built from) -- the same "committed, re-runnable
script, not a manual one-off session" pattern
`infra/scripts/generate_mdm_mirror_ddl.py` established for the MDM Snowflake
mirror schema (see CLAUDE.md's "MDM Snowflake mirror schema lost on
cutover" incident for why that pattern exists at all.

**Not the same target dialect as generate_mdm_mirror_ddl.py**, even though
Ticket 02 describes this script as mirroring that one's "shape": that script
emits *Snowflake SQL* because its target is a Snowflake dbt-interface mirror
schema (EDGARTOOLS_PROD.MDM). This store's target is a genuine Postgres
database -- the same kind of target `bootstrap-prod-mdm.sh` provisions for
MDM's own operational store via `mdm migrate`
(edgar_warehouse/mdm/migrations/runtime.py, which issues real Postgres
`CREATE TABLE` statements against a live Postgres DSN, not a generated
Snowflake-flavored script). So this script targets genuine Postgres SQL and
is meant to be called with a real (or local/SQLite-for-testing) SQLAlchemy
engine, not piped through `snow sql`.

Deliberately simpler than MDM's migration runner: this store starts empty at
cutover (see Ticket 02's own "operator-accepted cost" note), so one
idempotent `Base.metadata.create_all()` pass is proportionate -- no
versioned migration sequence, no owner-role-gated privileged DDL.

**What Ticket 04 (live provisioning) still has to decide, not resolved
here:** whether the bookkeeping store lives in a *new* Snowflake Postgres
instance (its own compute/storage/network-policy cost) or a *new schema
within the existing MDM instance* (shared compute, much cheaper, one less
credential set to manage) -- Ticket 02's own text left this open
("or schema within one"). This script is agnostic to that choice: it only
needs a working SQLAlchemy engine pointed at wherever Ticket 04 decides the
target database/schema lives; it issues no `CREATE POSTGRES INSTANCE` or
network-policy DDL itself (see infra/snowflake/postgres/mdm_create_instance.sql
for what that looks like if a new instance is chosen).

Grants: additive only (GRANT ... TO <role>; ALTER DEFAULT PRIVILEGES ... GRANT
... TO <role> for tables created after this runs) -- no REVOKE, no ownership
transfer, matching CLAUDE.md's "Manifest-pipeline ownership" lesson. Which
Postgres role is the right target (a new dedicated role vs. reusing MDM's
`application` role) is also a Ticket 04 decision; `--grant-role` defaults to
None (skip grants entirely) so this script is safe to run standalone against
a database this process itself owns, without guessing a role that doesn't
exist yet.

Usage:
    # Idempotent create against a live Postgres DSN, plus grants:
    uv run python infra/scripts/provision_bookkeeping_schema.py \
        --database-url "$BOOKKEEPING_DATABASE_URL" --grant-role application

    # Create-only, no grants (e.g. this process owns the database):
    uv run python infra/scripts/provision_bookkeeping_schema.py \
        --database-url "$BOOKKEEPING_DATABASE_URL"

Safe to re-run: `create_all` only creates tables that don't already exist;
every GRANT is additive.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text
from sqlalchemy.engine import Engine

from edgar_warehouse.bookkeeping.database import Base, get_engine
from edgar_warehouse.bookkeeping.models import BOOKKEEPING_TABLES


def provision(engine: Engine, *, grant_role: str | None = None) -> None:
    """Create the 11 bookkeeping tables (idempotent) and, if given a role,
    grant it additive DML + future-table access."""
    tables = [Base.metadata.tables[name] for name in BOOKKEEPING_TABLES]
    Base.metadata.create_all(engine, tables=tables, checkfirst=True)

    if grant_role is None:
        return
    if engine.dialect.name != "postgresql":
        # Grants are meaningless (and often unsupported) outside real
        # Postgres -- SQLite has no role/GRANT model. Skip quietly so local/
        # test invocations don't need a role argument at all.
        return

    with engine.begin() as conn:
        conn.execute(
            text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{grant_role}"')
        )
        conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{grant_role}"'
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Postgres DSN; defaults to the BOOKKEEPING_DATABASE_URL env var.",
    )
    parser.add_argument(
        "--grant-role",
        default=None,
        help="Postgres role to grant additive DML + future-table access. Omit to skip grants.",
    )
    args = parser.parse_args(argv)

    engine = get_engine(args.database_url)
    provision(engine, grant_role=args.grant_role)
    sys.stderr.write(
        f"Provisioned {len(BOOKKEEPING_TABLES)} bookkeeping tables"
        + (f"; granted {args.grant_role!r}" if args.grant_role else "")
        + ".\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
