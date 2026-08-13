"""Generate idempotent Snowflake DDL for the append-only silver landing zone.

Root cause this exists to prevent (named per the map's standing requirement,
not generic caution): the MDM Snowflake mirror schema was originally
provisioned by a one-off, uncommitted manual shell session -- when the
platform's Snowflake account was later rebuilt for the go-live cutover,
every other piece (gold, source, loader role, dashboards, Neo4j app) had a
committed script to re-run, but that one didn't, and it came back empty
(CLAUDE.md, "MDM Snowflake mirror schema lost on cutover"). This script is
the silver-landing-zone equivalent of `infra/scripts/generate_mdm_mirror_ddl.py`,
written for exactly the same reason before this migration's first real
provisioning step is ever run by hand.

Unlike the MDM mirror, `edgar_warehouse.silver_store`'s schema is not
SQLAlchemy ORM metadata -- it's a raw DuckDB SQL string (`silver_store._DDL`)
-- so there is no `Base.metadata` to reflect the way the MDM script does.
This script gets the same anti-drift guarantee through a different but
equally real mechanism: it executes `_DDL` in an in-memory DuckDB
connection (the same DDL the real silver database is built from) and
reflects columns/types back out via DuckDB's own `information_schema`,
rather than hand-transcribing column lists that could silently drift from
`silver_store.py`.

Scope: the 31 tables in `edgar_warehouse.silver_protection.PROTECTED_TABLE_REGISTRY`
(canonical domain data), minus `pipeline_run_lease` (operational, see
`_EXCLUDED_FROM_LANDING` below), plus `sec_guidance_fact_reject` (real
domain data that registry doesn't cover for an unrelated reason, see
`_INCLUDED_BEYOND_REGISTRY` below) -- 30 tables total. Not the remaining 12
`EXCLUDED_OPERATIONAL_TABLES` (checkpoints, leases, run logs), which are
warehouse-runtime bookkeeping, not part of the Snowflake-native pipeline
(silver-snowflake-migration map, Ticket 01's Answer, "Explicitly out of
scope for this ticket").

Landing tables are append-only by design (silver-snowflake-migration map,
Ticket 01): every parse event is a new row, nothing is ever updated in
place. Each table therefore drops its original DuckDB PRIMARY KEY (which
enforced current-state uniqueness silver_store.py no longer needs here)
and gains one shared, row-level `parse_sequence` column, backed by a single
Snowflake SEQUENCE object (Ticket 02's decision: a row-level SEQUENCE, not a
batch-level CURRENT_TIMESTAMP(), so concurrent writers can never tie).
`parse_sequence` alone is the landing table's own uniqueness guarantee,
regardless of the original business key.

Usage:
    uv run python infra/scripts/generate_silver_landing_ddl.py \
        > infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql

Safe to re-run: every CREATE SCHEMA/SEQUENCE/TABLE is IF NOT EXISTS and
every GRANT is additive (no REVOKE, no DROP, no OWNERSHIP transfer -- see
CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax incident" for why
`GRANT OWNERSHIP ... REVOKE CURRENT GRANTS` silently strips unrelated
grants).

Grants only SELECT + INSERT to the loader role, deliberately narrower than
the MDM mirror's SELECT/INSERT/UPDATE/DELETE: landing is append-only by
design, so UPDATE/DELETE would be a standing capability with no legitimate
caller -- not granting it is a real access-control statement, not an
oversight.
"""
from __future__ import annotations

import re
import sys

import duckdb

from edgar_warehouse import silver_store
from edgar_warehouse.silver_protection import PROTECTED_TABLE_REGISTRY

TARGET_DATABASE = "EDGARTOOLS_PROD"
# Full-prefixed, matching EDGARTOOLS_SOURCE/EDGARTOOLS_GOLD's naming convention
# (terraform/snowflake/accounts/prod/main.tf's source_schema_name), not MDM's
# shorter unprefixed schema name -- silver-snowflake-migration map Ticket 01
# locked this exact name.
TARGET_SCHEMA = "EDGARTOOLS_SILVER_LANDING"
TARGET_ROLE = "EDGARTOOLS_PROD_LOADER"
SEQUENCE_NAME = "PARSE_SEQ"

# pipeline_run_lease is dual-listed in PROTECTED_TABLE_REGISTRY (silver_protection.py),
# but only because it needed to survive the OLD whole-file candidate/canonical merge --
# a mechanism silver-snowflake-migration map Ticket 02 retired outright. It's
# cross-execution lease state (sec_fetch_active), not domain data, and it isn't
# append-only -- a lease's whole point is a mutable current status. It stays exactly
# where it is today (silver_store.py's local DuckDB), unaffected by this migration; it
# does not belong in the landing zone. Excluded here explicitly, not by omission, so a
# future re-run of this generator doesn't silently reintroduce it if the registry changes.
_EXCLUDED_FROM_LANDING = {"pipeline_run_lease"}

# sec_guidance_fact_reject is the mirror-image gap: it's real domain data (a quarantine
# log of rejected guidance-fact candidates) that Ticket 01's Answer explicitly said
# "stays append/log-shaped in silver too" -- but it was never in PROTECTED_TABLE_REGISTRY
# to begin with, because that registry was scoped to the OLD cross-writer whole-file merge
# eligibility (silver_protection.py's own comment: "append-only quarantine log ... no
# natural key, rows accumulate, never conflict" is exactly why it was EXCLUDED from that
# now-retired mechanism, not evidence it should be excluded from landing). Scoping this
# generator strictly by PROTECTED_TABLE_REGISTRY membership silently missed it -- caught
# while building the downstream dbt silver-model generator, added back explicitly here
# rather than left as a carried-forward gap. No parse_sequence-ordered collapse needed for
# it in silver (every row is already final; see the silver-model generator for the
# passthrough-view treatment), but it still needs the same append-only landing table shape
# as everything else, via the same ingest apparatus.
_INCLUDED_BEYOND_REGISTRY = {"sec_guidance_fact_reject"}

# DuckDB information_schema.columns.data_type -> Snowflake column type.
# Faithful port of silver_store.py's existing types -- this script does not
# "fix" any pre-existing schema choice (e.g. CLAUDE.md's SMALLINT-vs-BIGINT
# policy for count-derived columns) as a side effect of generating DDL;
# that's a separate, undecided concern for whichever table it applies to.
_TYPE_MAP = {
    "BIGINT": "BIGINT",
    "INTEGER": "INTEGER",
    "SMALLINT": "SMALLINT",
    "BOOLEAN": "BOOLEAN",
    "DOUBLE": "DOUBLE",
    "DATE": "DATE",
    "VARCHAR": "TEXT",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP_TZ",
    "JSON": "VARIANT",
    "BLOB": "BINARY",
}
_DECIMAL_RE = re.compile(r"^DECIMAL\((\d+),\s*(\d+)\)$")


def _snowflake_type(duckdb_type: str) -> str:
    decimal_match = _DECIMAL_RE.match(duckdb_type)
    if decimal_match:
        precision, scale = decimal_match.groups()
        return f"NUMBER({precision},{scale})"
    try:
        return _TYPE_MAP[duckdb_type]
    except KeyError:
        raise RuntimeError(
            f"No Snowflake mapping for DuckDB type {duckdb_type!r} -- add one to "
            "_TYPE_MAP rather than silently passing it through."
        ) from None


def _reflect_landing_tables() -> dict[str, list[tuple[str, str, bool]]]:
    """Execute silver_store._DDL in-memory and reflect (name, type, nullable) per table."""
    con = duckdb.connect(":memory:")
    con.execute(silver_store._DDL)
    wanted = (set(PROTECTED_TABLE_REGISTRY.keys()) | _INCLUDED_BEYOND_REGISTRY) - _EXCLUDED_FROM_LANDING
    found = {
        r[0]
        for r in con.execute(
            "SELECT DISTINCT table_name FROM information_schema.columns "
            "WHERE table_schema = 'main'"
        ).fetchall()
    }
    missing = wanted - found
    if missing:
        raise RuntimeError(
            f"Landing-scoped tables not found in silver_store._DDL: {sorted(missing)}"
        )

    columns_by_table: dict[str, list[tuple[str, str, bool]]] = {}
    for table in sorted(wanted):
        rows = con.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        columns_by_table[table] = [(name, dtype, is_nullable == "YES") for name, dtype, is_nullable in rows]
    return columns_by_table


def generate() -> str:
    columns_by_table = _reflect_landing_tables()

    lines = [
        "-- Auto-generated by infra/scripts/generate_silver_landing_ddl.py -- do not hand-edit.",
        "-- Reflects edgar_warehouse.silver_store._DDL (via in-memory DuckDB introspection,",
        "-- not SQLAlchemy -- see this generator's module docstring for why) for the tables",
        "-- listed in edgar_warehouse.silver_protection.PROTECTED_TABLE_REGISTRY.",
        "-- Idempotent: every statement is CREATE ... IF NOT EXISTS or an additive GRANT.",
        "",
        "USE ROLE ACCOUNTADMIN;",
        f"USE DATABASE {TARGET_DATABASE};",
        f"CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA};",
        f"USE SCHEMA {TARGET_SCHEMA};",
        "",
        "-- Single shared sequence: row-level parse_sequence assignment, safe under any",
        "-- concurrency (Snowflake's metadata layer coordinates allocation globally --",
        "-- silver-snowflake-migration map, Ticket 02's decision). One sequence across",
        "-- every landing table, not one per table -- the window-function collapse that",
        "-- reads this later partitions by business key per table already, so a single",
        "-- monotonically increasing value remains a valid ordering marker regardless of",
        "-- which table a row belongs to.",
        f"CREATE SEQUENCE IF NOT EXISTS {SEQUENCE_NAME} START = 1 INCREMENT = 1;",
        "",
    ]

    for table, columns in columns_by_table.items():
        column_lines = [
            f"    {name} {_snowflake_type(dtype)}" + ("" if nullable else " NOT NULL")
            for name, dtype, nullable in columns
        ]
        column_lines.append(f"    parse_sequence BIGINT DEFAULT {SEQUENCE_NAME}.NEXTVAL NOT NULL")
        lines.append(f"CREATE TABLE IF NOT EXISTS {table} (")
        lines.append(",\n".join(column_lines))
        lines.append("    , PRIMARY KEY (parse_sequence)")
        lines.append(");")
        lines.append("")

    lines.extend(
        [
            "-- Grant the loader role (the same EDGARTOOLS_PROD_LOADER that already owns",
            "-- gold's 20 dynamic tables, the MDM mirror, and the graph schema -- reused",
            "-- here rather than minting a new role, per silver-snowflake-migration map",
            "-- Ticket 05's decision) SELECT + INSERT only. No UPDATE/DELETE: landing is",
            "-- append-only by design, so granting write-in-place would be a standing",
            "-- capability with no legitimate caller.",
            f"GRANT USAGE ON SCHEMA {TARGET_DATABASE}.{TARGET_SCHEMA} TO ROLE {TARGET_ROLE};",
            f"GRANT USAGE ON SEQUENCE {TARGET_DATABASE}.{TARGET_SCHEMA}.{SEQUENCE_NAME} TO ROLE {TARGET_ROLE};",
            f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA {TARGET_DATABASE}.{TARGET_SCHEMA} TO ROLE {TARGET_ROLE};",
            f"GRANT SELECT, INSERT ON FUTURE TABLES IN SCHEMA {TARGET_DATABASE}.{TARGET_SCHEMA} TO ROLE {TARGET_ROLE};",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.write(generate())
