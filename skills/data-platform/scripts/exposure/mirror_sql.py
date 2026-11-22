"""The SQL that creates, changes, checks and retires the managed mirror. It prints text and connects to nothing.

The tables are the ones sources/managed-mirror.yaml lists, the system of record for the mirror; each must be on
destination/authorised_data_sharing.yaml, whose layers give the PostgreSQL schemas. The mirror's name, database, refresh interval and table
format come from the same record, the target database from rules/snowflake.yaml, and the call is the mirror skill's SETUP
step 5 with Snowflake-managed storage. Run the output as the mirror operator, after the skill's read-only pre-flight and
the operator's approval:

    python mirror_sql.py exists                                         # read-back: does the target database exist (absent before a create)
    python mirror_sql.py plan --publication-limit 2 --publications-held 0   # the one mirror of the data database, or the refusal
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


DATA_DATABASE = "data"  # the one database the mirror reads (the data stores' database); the control database is never mirrored


def plan(managed: dict, exposure: dict, publication_limit: int, publications_held: int) -> str:
    """The plan for the one mirror, or the refusal: only the data database, each layer a schema, one free publication."""
    if managed["postgres_database"] != DATA_DATABASE:
        raise SystemExit(f"postgres_database is {managed['postgres_database']}: only the {DATA_DATABASE} database is mirrored")
    layers = exposure["layers"]
    held = {e["layer"]: layers[e["layer"]]["connection"] for e in managed["tables"]}
    if len(set(held.values())) > 1:
        spread = sorted(f"{e['layer']}.{e['table']} ({held[e['layer']]})" for e in managed["tables"])
        raise SystemExit(f"the tables are not all in the data database, so one mirror cannot carry them: {', '.join(spread)}")
    listed = tables(managed, exposure)
    if publications_held + 1 > publication_limit:
        raise SystemExit(f"no free publication: {publications_held} held of {publication_limit}; the mirror needs 1")
    by_layer = sorted({e["layer"] for e in managed["tables"]})
    lines = [f"mirror {managed['mirror']}: database {DATA_DATABASE}, {len(listed)} tables, 1 publication ({publications_held} held of {publication_limit})"]
    for layer in by_layer:
        count = sum(1 for e in managed["tables"] if e["layer"] == layer)
        lines.append(f"  {layers[layer]['source_schema']} -> {layers[layer]['target_schema']}: {count} table{'s' if count != 1 else ''}")
    return "\n".join(lines) + "\n"


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


def exists(names: dict) -> str:
    """The read-back of the one mirror target: absent before a create and after a retire, present while it replicates. Any role that can list databases runs it."""
    return f"SHOW DATABASES LIKE '{names['mirror']['database']}';\n"


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
    parser.add_argument("action", choices=["plan", "create", "alter", "verify", "check", "retire", "release", "exists"])
    parser.add_argument("--managed", type=Path, default=SOURCES / "managed-mirror.yaml", help="the managed mirror record")
    parser.add_argument("--exposure", type=Path, default=SOURCES.parent / "destination" / "authorised_data_sharing.yaml", help="the exposure list that bounds the record")
    parser.add_argument("--names", type=Path, default=RULES / "snowflake.yaml", help="the file naming the mirror database")
    parser.add_argument("--publication-limit", type=int, help="snowflake_cdc.max_publications, read from the instance (plan)")
    parser.add_argument("--publications-held", type=int, help="the publications the instance already holds (plan)")
    parser.add_argument("--instance", help="the Postgres instance (create)")
    parser.add_argument("--reads", type=Path, help="the dbt sources file Gold reads (check)")
    parser.add_argument("--mirrored", type=Path, help="a JSON list of the tables the mirror holds, read back (alter)")
    args = parser.parse_args(argv)
    load = lambda path: yaml.safe_load(path.read_text(encoding="utf-8"))
    managed = load(args.managed)
    if args.action == "plan":
        if args.publication_limit is None or args.publications_held is None:
            parser.error("plan needs --publication-limit and --publications-held")
        return plan(managed, load(args.exposure), args.publication_limit, args.publications_held)
    if args.action == "verify":
        return verify(managed)
    if args.action == "exists":
        return exists(load(args.names))
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
