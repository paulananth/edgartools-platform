"""The SQL that creates, changes, checks and retires the managed mirror. It prints text and connects to nothing.

The tables are the ones a dbt project reads (its sources file: each source is named by an exposure layer and lists
tables), bounded by rules/exposure.yaml: a read the exposure list does not name is refused, and each layer gives the
PostgreSQL schema. The target database comes from rules/snowflake.yaml, and the call is the mirror skill's SETUP step 5
with Snowflake-managed storage. Run the output as the mirror operator, after the skill's read-only pre-flight and the
operator's approval:

    python mirror_sql.py create --mirror <name> --instance <instance> --postgres-database <database> \\
        --reads <sources file> --exposure <exposure list> --names <database names file> \\
        --interval <interval> --table-type ICEBERG > create.sql
    snow sql -c <connection> -f create.sql
    python mirror_sql.py alter --mirror <name> --reads <sources file> --exposure <exposure list> \\
        --mirrored <JSON list of the mirrored schema.table names, read back>   # adds and removes the difference
    python mirror_sql.py verify --mirror <name>          # until every table is REPLICATING with equal counts
    python mirror_sql.py retire --mirror <old name>      # TRUE: the target database goes with the mirror
    python mirror_sql.py release --mirror <name> --names <database names file>   # FALSE, then the owner role takes the target
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def tables(reads: dict, exposure: dict) -> list[str]:
    """The PostgreSQL tables the sources file reads; each must be on the exposure list."""
    layers, exposed = exposure["layers"], {(entry["layer"], entry["table"]) for entry in exposure["tables"]}
    wanted = {(source["name"], table["name"]) for source in reads["sources"] for table in source["tables"]}
    if missing := sorted(f"{layer}.{table}" for layer, table in wanted - exposed):
        raise SystemExit(f"read but not on the exposure list: {', '.join(missing)}")
    return sorted(f"{layers[layer]['source_schema']}.{table}" for layer, table in wanted)


def quoted(names: list[str]) -> str:
    return "[" + ", ".join(f"'{name}'" for name in names) + "]" if names else "NULL"


def create(reads: dict, exposure: dict, names: dict, mirror: str, instance: str, postgres_database: str, interval: str,
           table_type: str) -> str:
    listed = ", ".join(f"'{table}'" for table in tables(reads, exposure))
    return (
        "CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(\n"
        f"  mirror_name => '{mirror}',\n  postgres_instance => '{instance}',\n  postgres_database => '{postgres_database}',\n"
        f"  target_database => '{names['mirror']['database']}',\n  postgres_tables => [{listed}],\n  postgres_schemas => NULL,\n"
        f"  refresh_interval => '{interval}',\n  warehouse => NULL,\n  target_table_type => '{table_type}',\n  external_volume => NULL\n);\n"
    )


def alter(reads: dict, exposure: dict, mirror: str, mirrored: list[str]) -> str:
    """Adds the read tables the mirror lacks and removes the mirrored tables nothing reads; empty when they agree."""
    wanted, held = set(tables(reads, exposure)), set(mirrored)
    add, remove = sorted(wanted - held), sorted(held - wanted)
    if not add and not remove:
        return ""
    return (f"CALL SNOWFLAKE.POSTGRES.ALTER_MIRROR(\n  mirror_name => '{mirror}',\n  refresh_interval => NULL,\n"
            f"  add_tables => {quoted(add)},\n  remove_tables => {quoted(remove)}\n);\n")


def verify(mirror: str) -> str:
    return f"CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('{mirror}');\n"


def retire(mirror: str) -> str:
    """Always TRUE: a target left behind by FALSE cannot be dropped by any customer role."""
    return f"CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('{mirror}', TRUE);\n"


def release(mirror: str, names: dict) -> str:
    """Stop the mirror and keep its target, owned by the platform's owner role instead of the Snowflake application.

    A target is owned by the application while its mirror replicates (active or suspended), and CREATE_MIRROR refuses an
    existing database, so ownership moves only here: the mirror operator drops the mirror without the target, then the
    account administrator (a separately approved use) moves ownership, without COPY CURRENT GRANTS, which an
    application-owned object refuses. The data stays but is no longer refreshed.
    """
    target, owner = names["mirror"]["database"], names["owner"]
    return (f"-- as the mirror operator\nCALL SNOWFLAKE.POSTGRES.DROP_MIRROR('{mirror}', FALSE);\n"
            f"-- as the account administrator, on the operator's words\nGRANT OWNERSHIP ON DATABASE {target} TO ROLE {owner};\n"
            f"-- read back: the owner column says {owner}\nSHOW DATABASES LIKE '{target}';\n")


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["create", "alter", "verify", "retire", "release"])
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--instance")
    parser.add_argument("--postgres-database")
    parser.add_argument("--interval", help="the refresh interval (create)")
    parser.add_argument("--table-type", choices=["ICEBERG", "SNOWFLAKE"], help="the target table format (create)")
    parser.add_argument("--reads", type=Path, help="the dbt sources file whose tables are mirrored (create, alter)")
    parser.add_argument("--exposure", type=Path, help="the exposure list that bounds the reads (create, alter)")
    parser.add_argument("--names", type=Path, help="the file naming the mirror database (create)")
    parser.add_argument("--mirrored", type=Path, help="a JSON list of the tables the mirror holds, read back (alter)")
    args = parser.parse_args(argv)
    if args.action == "verify":
        return verify(args.mirror)
    if args.action == "retire":
        return retire(args.mirror)
    load = lambda path: yaml.safe_load(path.read_text(encoding="utf-8"))
    if args.action == "release":
        if not args.names:
            parser.error("release needs --names")
        return release(args.mirror, load(args.names))
    if args.action == "alter":
        if not all((args.reads, args.exposure, args.mirrored)):
            parser.error("alter needs --reads, --exposure and --mirrored")
        return alter(load(args.reads), load(args.exposure), args.mirror, load(args.mirrored))
    if not all((args.instance, args.postgres_database, args.reads, args.exposure, args.names, args.interval, args.table_type)):
        parser.error("create needs --instance, --postgres-database, --reads, --exposure, --names, --interval and --table-type")
    return create(load(args.reads), load(args.exposure), load(args.names), args.mirror, args.instance, args.postgres_database,
                  args.interval, args.table_type)


if __name__ == "__main__":
    sys.stdout.write(main())
