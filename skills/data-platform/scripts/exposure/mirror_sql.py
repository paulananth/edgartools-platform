"""The SQL that creates, checks and retires the managed mirror of the exposure list. It prints text and connects to nothing.

The tables come from rules/exposure.yaml (each table's layer gives its PostgreSQL schema), the target database from
rules/snowflake.yaml, and the call is the mirror skill's SETUP step 5 with Snowflake-managed storage. Run the
output as the mirror operator, after the skill's read-only pre-flight and the operator's approval:

    python mirror_sql.py create --mirror <name> --instance <instance> --postgres-database <database> \\
        --exposure <exposure list> --names <database names file> --interval <interval> --table-type ICEBERG > create.sql
    snow sql -c <connection> -f create.sql
    python mirror_sql.py verify --mirror <name>          # until every table is REPLICATING with equal counts
    python mirror_sql.py retire --mirror <old name>      # TRUE: the target database goes with the mirror
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


def tables(exposure: dict) -> list[str]:
    layers = exposure["layers"]
    return sorted(f"{layers[entry['layer']]['source_schema']}.{entry['table']}" for entry in exposure["tables"])


def create(exposure: dict, names: dict, mirror: str, instance: str, postgres_database: str, interval: str, table_type: str) -> str:
    listed = ", ".join(f"'{table}'" for table in tables(exposure))
    return (
        "CALL SNOWFLAKE.POSTGRES.CREATE_MIRROR(\n"
        f"  mirror_name => '{mirror}',\n  postgres_instance => '{instance}',\n  postgres_database => '{postgres_database}',\n"
        f"  target_database => '{names['mirror']['database']}',\n  postgres_tables => [{listed}],\n  postgres_schemas => NULL,\n"
        f"  refresh_interval => '{interval}',\n  warehouse => NULL,\n  target_table_type => '{table_type}',\n  external_volume => NULL\n);\n"
    )


def verify(mirror: str) -> str:
    return f"CALL SNOWFLAKE.POSTGRES.LIST_MIRRORED_TABLES('{mirror}');\n"


def retire(mirror: str) -> str:
    """Always TRUE: a target left behind by FALSE cannot be dropped by any customer role."""
    return f"CALL SNOWFLAKE.POSTGRES.DROP_MIRROR('{mirror}', TRUE);\n"


def main(argv: list[str] | None = None) -> str:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=["create", "verify", "retire"])
    parser.add_argument("--mirror", required=True)
    parser.add_argument("--instance")
    parser.add_argument("--postgres-database")
    parser.add_argument("--interval", help="the refresh interval (create)")
    parser.add_argument("--table-type", choices=["ICEBERG", "SNOWFLAKE"], help="the target table format (create)")
    parser.add_argument("--exposure", type=Path, help="the exposure list (create)")
    parser.add_argument("--names", type=Path, help="the file naming the mirror database (create)")
    args = parser.parse_args(argv)
    if args.action == "verify":
        return verify(args.mirror)
    if args.action == "retire":
        return retire(args.mirror)
    if not all((args.instance, args.postgres_database, args.exposure, args.names, args.interval, args.table_type)):
        parser.error("create needs --instance, --postgres-database, --exposure, --names, --interval and --table-type")
    load = lambda path: yaml.safe_load(path.read_text(encoding="utf-8"))
    return create(load(args.exposure), load(args.names), args.mirror, args.instance, args.postgres_database, args.interval, args.table_type)


if __name__ == "__main__":
    sys.stdout.write(main())
