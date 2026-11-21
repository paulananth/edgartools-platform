"""The SQL that creates, changes, checks and retires the managed mirror. It prints text and connects to nothing.

The tables are the ones sources/managed-mirror.yaml lists, the system of record for the mirror; each must be on
rules/exposure.yaml, whose layers give the PostgreSQL schemas. The mirror's name, database, refresh interval and table
format come from the same record, the target database from rules/snowflake.yaml, and the call is the mirror skill's SETUP
step 5 with Snowflake-managed storage. Run the output as the mirror operator, after the skill's read-only pre-flight and
the operator's approval:

    python mirror_sql.py create --instance <instance> > create.sql      # the record, the exposure list and the names file
    snow sql -c <connection> -f create.sql
    python mirror_sql.py alter --mirrored <JSON list of the mirrored schema.table names, read back>   # adds and removes the difference
    python mirror_sql.py verify                  # until every table is REPLICATING with equal counts
    python mirror_sql.py check --reads <sources file>   # fails when Gold reads a table the record does not list
    python mirror_sql.py retire                  # TRUE: the target database goes with the mirror
    python mirror_sql.py release                 # FALSE, then the owner role takes the target
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

RULES = Path(__file__).resolve().parents[4] / "rules"
SOURCES = RULES.parent / "sources"  # the managed mirror record is part of the source mapping


def tables(managed: dict, exposure: dict) -> list[str]:
    """The PostgreSQL tables the managed mirror record lists; each must be on the exposure list."""
    layers, exposed = exposure["layers"], {(entry["layer"], entry["table"]) for entry in exposure["tables"]}
    wanted = {(entry["layer"], entry["table"]) for entry in managed["tables"]}
    if missing := sorted(f"{layer}.{table}" for layer, table in wanted - exposed):
        raise SystemExit(f"listed in the managed mirror but not on the exposure list: {', '.join(missing)}")
    return sorted(f"{layers[layer]['source_schema']}.{table}" for layer, table in wanted)


def unmirrored_reads(reads: dict, managed: dict) -> list[str]:
    """The tables a dbt sources file reads that the managed mirror record does not list."""
    listed = {(entry["layer"], entry["table"]) for entry in managed["tables"]}
    wanted = {(source["name"], table["name"]) for source in reads["sources"] for table in source["tables"]}
    return sorted(f"{layer}.{table}" for layer, table in wanted - listed)


def quoted(names: list[str]) -> str:
    return "[" + ", ".join(f"'{name}'" for name in names) + "]" if names else "NULL"


def create(managed: dict, exposure: dict, names: dict, instance: str) -> str:
    listed = ", ".join(f"'{table}'" for table in tables(managed, exposure))
    return (
        "CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(\n"
        f"  mirror_name => '{managed['mirror']}',\n  postgres_instance => '{instance}',\n"
        f"  postgres_database => '{managed['postgres_database']}',\n"
        f"  target_database => '{names['mirror']['database']}',\n  postgres_tables => [{listed}],\n  postgres_schemas => NULL,\n"
        f"  refresh_interval => '{managed['refresh_interval']}',\n  warehouse => NULL,\n"
        f"  target_table_type => '{managed['target_table_type']}',\n  external_volume => NULL\n);\n"
    )


def alter(managed: dict, exposure: dict, mirrored: list[str]) -> str:
    """Adds the listed tables the mirror lacks and removes the mirrored tables the record does not list; empty when they agree."""
    wanted, held = set(tables(managed, exposure)), set(mirrored)
    add, remove = sorted(wanted - held), sorted(held - wanted)
    if not add and not remove:
        return ""
    return (f"CALL SNOWFLAKE.POSTGRES.ALTER_MIRROR(\n  mirror_name => '{managed['mirror']}',\n  refresh_interval => NULL,\n"
            f"  add_tables => {quoted(add)},\n  remove_tables => {quoted(remove)}\n);\n")


def verify(managed: dict) -> str:
    return f"CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('{managed['mirror']}');\n"


def retire(managed: dict) -> str:
    """Always TRUE: a target left behind by FALSE has no mirror to drop it."""
    return f"CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('{managed['mirror']}', TRUE);\n"


def release(managed: dict, names: dict) -> str:
    """Stop the mirror and keep its target, owned by the platform's owner role instead of the Snowflake application.

    A target is owned by the application while its mirror replicates (active or suspended), and CREATE_MIRROR refuses an
    existing database, so ownership moves only here: the mirror operator drops the mirror without the target, then the
    account administrator (a separately approved use) moves ownership, without COPY CURRENT GRANTS, which an
    application-owned object refuses. The data stays but is no longer refreshed.
    """
    target, owner = names["mirror"]["database"], names["owner"]
    return (f"-- as the mirror operator\nCALL SNOWFLAKE.POSTGRES.DROP_MIRROR('{managed['mirror']}', FALSE);\n"
            f"-- as the account administrator, on the operator's words\nGRANT OWNERSHIP ON DATABASE {target} TO ROLE {owner};\n"
            f"-- read back: the owner column says {owner}\nSHOW DATABASES LIKE '{target}';\n")


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["create", "alter", "verify", "check", "retire", "release"])
    parser.add_argument("--managed", type=Path, default=SOURCES / "managed-mirror.yaml", help="the managed mirror record")
    parser.add_argument("--exposure", type=Path, default=RULES / "exposure.yaml", help="the exposure list that bounds the record")
    parser.add_argument("--names", type=Path, default=RULES / "snowflake.yaml", help="the file naming the mirror database")
    parser.add_argument("--instance", help="the Postgres instance (create)")
    parser.add_argument("--reads", type=Path, help="the dbt sources file Gold reads (check)")
    parser.add_argument("--mirrored", type=Path, help="a JSON list of the tables the mirror holds, read back (alter)")
    args = parser.parse_args(argv)
    load = lambda path: yaml.safe_load(path.read_text(encoding="utf-8"))
    managed = load(args.managed)
    if args.action == "verify":
        return verify(managed)
    if args.action == "retire":
        return retire(managed)
    if args.action == "release":
        return release(managed, load(args.names))
    if args.action == "check":
        if not args.reads:
            parser.error("check needs --reads")
        if missing := unmirrored_reads(load(args.reads), managed):
            raise SystemExit(f"read but not in the managed mirror: {', '.join(missing)}")
        tables(managed, load(args.exposure))
        return "every table read is in the managed mirror, and every one in it is exposable\n"
    if args.action == "alter":
        if not args.mirrored:
            parser.error("alter needs --mirrored")
        return alter(managed, load(args.exposure), load(args.mirrored))
    if not args.instance:
        parser.error("create needs --instance")
    return create(managed, load(args.exposure), load(args.names), args.instance)


if __name__ == "__main__":
    sys.stdout.write(main())
