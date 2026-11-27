#!/usr/bin/env python3
"""Plan or apply an explicit table-level reset on one hosted store.

    uv run python infra/scripts/reset-hosted-tables.py --store mdm --inventory
    uv run python infra/scripts/reset-hosted-tables.py --store mdm --manifest <file>
    uv run python infra/scripts/reset-hosted-tables.py --store mdm --manifest <file> \
        --apply --words "<the operator's exact words>" --plan-sha256 <the reviewed plan digest> [--wait-minutes 15] [--with-suspended-mirror]

The manifest selects ordinary tables in one store schema and says `drop` or `truncate` for each.
The script never drops a database, schema, or table with CASCADE. A dropped table must be recreated
by that store's normal init/deploy procedure. A truncated table keeps its schema and constraints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import sqlalchemy as sa
import yaml

# The stores of the data and control databases. Rules, in the config database, is never reset: a reload needs it.
STORE_SCHEMAS = {
    "mdm": "mdm",
    "rdm": "rdm",
    "bookkeeping": "bookkeeping",
    "change_journal": "journal",
    "silver": "silver",
}
# Only these verified retention triggers can be paused for a reviewed truncate.
RETENTION_TRIGGERS = {
    ("rdm", "code_set_version"): ("no_truncate_version", "rdm.govern_version()"),
    ("journal", "event"): ("immutable_event", "journal.immutable()"),
}
PRESERVED_TABLES = {"mdm": {"migration"}, "silver": {"table_spec"}}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
PERSISTENT_TABLES = """
    SELECT c.relkind, c.relpersistence,
           EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid OR i.inhparent = c.oid) AS partitioned,
           c.reltuples::bigint
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relname = :table
"""


class UniqueYamlLoader(yaml.SafeLoader):
    pass


class BlockedError(RuntimeError):
    """A session other than an idle managed worker is connected to the store; its message names them by kind."""


class ReceiptError(RuntimeError):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.YAMLError("Manifest keys must be text")
        if key in mapping:
            raise yaml.YAMLError("Duplicate manifest key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueYamlLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def fail(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    return code


def quote(engine, identifier: str) -> str:
    return engine.dialect.identifier_preparer.quote(identifier)


def inventory(conn, schema: str) -> list[dict]:
    rows = conn.execute(sa.text("""
        SELECT c.relname, c.relkind, c.relpersistence,
               EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid OR i.inhparent = c.oid) AS inherited,
               c.reltuples::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND c.relkind IN ('r', 'p')
        ORDER BY c.relname
    """), {"schema": schema}).all()
    return [{"table": str(name), "kind": kind, "persistence": persistence, "inherited": inherited,
             "rows_estimate": None if estimate < 0 else int(estimate)}
            for name, kind, persistence, inherited, estimate in rows]


def load_manifest(path: Path, requested_store: str) -> list[dict[str, str]]:
    try:
        document = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueYamlLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("Cannot read the table-reset manifest") from exc
    if not isinstance(document, dict) or set(document) != {"version", "store", "tables"}:
        raise ValueError("Manifest must contain only version, store and tables")
    if type(document["version"]) is not int or document["version"] != 1 or document["store"] != requested_store:
        raise ValueError("Manifest version or selected store does not match this invocation")
    schema = STORE_SCHEMAS[requested_store]
    tables = document["tables"]
    if not isinstance(tables, list) or not tables:
        raise ValueError("Manifest must list at least one table")
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in tables:
        if not isinstance(item, dict) or set(item) != {"schema", "table", "action"}:
            raise ValueError("Each table entry must contain only schema, table and action")
        name, action = item["table"], item["action"]
        if item["schema"] != schema or not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
            raise ValueError("Manifest table must use the selected store schema and a valid table name")
        if not isinstance(action, str) or action not in {"drop", "truncate"}:
            raise ValueError("Table action must be drop or truncate")
        if name in PRESERVED_TABLES.get(schema, ()):
            raise ValueError("Reset manifest includes deployment metadata")
        if name in seen:
            raise ValueError("Manifest contains a duplicate table")
        seen.add(name)
        found.append({"schema": schema, "table": name, "action": action})
    return sorted(found, key=lambda row: row["table"])


def retention_trigger(conn, item: dict) -> str | None:
    key = (item["schema"], item["table"])
    if item["action"] != "truncate" or key not in RETENTION_TRIGGERS:
        return None
    trigger, function = RETENTION_TRIGGERS[key]
    enabled = conn.scalar(sa.text("""
        SELECT tgenabled FROM pg_trigger
        WHERE tgrelid = to_regclass(:relation) AND tgname = :trigger
          AND tgfoid = to_regprocedure(:function) AND NOT tgisinternal
    """), {"relation": ".".join(key), "trigger": trigger, "function": function})
    if enabled != "O":
        raise ValueError("Expected retention trigger is missing, changed or disabled")
    return trigger


def read_plan(conn, engine, store: str, tables: list[dict[str, str]], *, require_all: bool = False) -> dict:
    schema = STORE_SCHEMAS[store]
    if engine.dialect.name != "postgresql":
        raise ValueError("Hosted table reset supports PostgreSQL only")
    database = conn.scalar(sa.text("SELECT current_database()"))
    version = int(conn.scalar(sa.text("SHOW server_version_num")))
    if version // 10000 != 16:
        raise ValueError("Hosted table reset requires PostgreSQL 16")
    if require_all:
        selected = {item["table"] for item in tables}
        if selected != {row["table"] for row in inventory(conn, schema)} - PRESERVED_TABLES.get(schema, set()):
            raise ValueError("Manifest does not match the full store table inventory")
        if any(item["action"] != "truncate" for item in tables):
            raise ValueError("A full store reset requires truncate for every table")
    plan_tables = []
    for item in tables:
        relation = conn.execute(sa.text(PERSISTENT_TABLES),
                                {"schema": item["schema"], "table": item["table"]}).first()
        if relation is None:
            raise ValueError("A selected table is missing")
        relkind, persistence, partitioned, estimate = relation
        if relkind != "r" or persistence != "p" or partitioned:
            raise ValueError("Only ordinary, persistent, non-partitioned tables can be reset")
        planned = {**item, "rows_estimate": None if estimate < 0 else int(estimate)}
        if trigger := retention_trigger(conn, item):
            planned["retention_trigger"] = trigger
        plan_tables.append(planned)
    plan = {"store": store, "database": database, "postgres_major": version // 10000, "tables": plan_tables}
    if require_all:
        plan["require_all_tables"] = True
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    plan["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan


def print_inventory(engine, store: str) -> int:
    schema = STORE_SCHEMAS[store]
    with engine.connect() as conn:
        database = conn.scalar(sa.text("SELECT current_database()"))
        exists = bool(conn.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=:schema)"),
                                  {"schema": schema}))
        if not exists:
            raise ValueError("Selected store schema is missing")
        rows = inventory(conn, schema)
    print(f"Store: {store}; database: {database}; schema: {schema}")
    print("Table rows are planner estimates; only ordinary persistent non-partitioned tables can be reset:")
    for item in rows:
        supported = item["kind"] == "r" and item["persistence"] == "p" and not item["inherited"]
        estimate = "unknown" if item["rows_estimate"] is None else str(item["rows_estimate"])
        note = "supported" if supported else "unsupported table shape"
        if item["table"] in PRESERVED_TABLES.get(schema, ()):
            note = "preserved deployment metadata"
        print(f"  {item['table']}: {estimate} rows; {note}")
    print(f"{len(rows)} tables listed; nothing changed")
    return 0


def approval_log() -> Path:
    folder = Path(os.environ.get("STORES_FOLDER") or Path.home() / ".config/edgartools/hosted")
    return folder / "table-reset-approvals.jsonl"


def append_receipt(record: dict) -> None:
    path = approval_log()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    path.chmod(0o600)


def blocking_sessions(conn, mirror_suspended: bool = False) -> str:
    """The sessions that block a reset, by kind and number ("walsender 1"), or "" when none does. A managed worker with no
    session state and no open transaction never blocks. With the mirror suspended, its own sessions (its walsender, and a
    managed worker with no open transaction) stay connected through the reset; the mirror is restarted after it, which
    takes a new snapshot of the emptied tables. A client session blocks always."""
    return ", ".join(f"{kind} {count}" for kind, count in conn.execute(sa.text("""
        SELECT coalesce(backend_type, 'unknown'), count(*) FROM pg_stat_activity
        WHERE datname = current_database() AND pid <> pg_backend_pid()
          AND NOT (backend_type IS NOT DISTINCT FROM 'pg base extension worker'
                   AND (state IS NULL OR :mirror_suspended) AND xact_start IS NULL)
          AND NOT (:mirror_suspended AND backend_type IS NOT DISTINCT FROM 'walsender')
        GROUP BY 1 ORDER BY 1
    """), {"mirror_suspended": mirror_suspended}))


def wait_for_quiet(engine, minutes: float, every: float = 30, mirror_suspended: bool = False) -> None:
    """Wait until no session blocks the reset, checking every `every` seconds for at most `minutes`. A suspended mirror's
    walsender stays connected for a while after the suspend; this is the wait for it to leave."""
    deadline = time.monotonic() + minutes * 60
    while True:
        with engine.connect() as conn:
            blocking = blocking_sessions(conn, mirror_suspended)
        if not blocking:
            return
        if time.monotonic() >= deadline:
            waited = f" after {minutes:g} minutes" if minutes > 0 else ""
            raise BlockedError(f"Refusing reset while connected to this store{waited}: {blocking}")
        print(f"waiting for the store to be quiet: {blocking}", flush=True)
        time.sleep(every)


def show_plan(plan: dict) -> None:
    print(f"Store: {plan['store']}; database: {plan['database']}; PostgreSQL {plan['postgres_major']}")
    for item in plan["tables"]:
        count = "unknown" if item["rows_estimate"] is None else f"about {item['rows_estimate']}"
        print(f"  {item['action']} {item['schema']}.{item['table']}: {count} rows (planner estimate)")
        if trigger := item.get("retention_trigger"):
            print(f"    pause and restore retention trigger: {trigger}")
    print(f"Plan SHA-256: {plan['plan_sha256']}")


def apply_plan(engine, store: str, tables: list[dict[str, str]], words: str, expected_digest: str, *,
               require_all: bool = False, mirror_suspended: bool = False) -> dict:
    plan = None
    schema = STORE_SCHEMAS[store]
    try:
        with engine.begin() as conn:
            if blocking := blocking_sessions(conn, mirror_suspended):
                raise BlockedError(f"Refusing reset while connected to this store: {blocking}")
            conn.exec_driver_sql("SET LOCAL lock_timeout = '2s'")
            for item in tables:
                qualified = f"{quote(engine, schema)}.{quote(engine, item['table'])}"
                conn.exec_driver_sql(f"LOCK TABLE {qualified} IN ACCESS EXCLUSIVE MODE NOWAIT")
            if blocking := blocking_sessions(conn, mirror_suspended):
                raise BlockedError(f"Refusing reset while connected to this store: {blocking}")
            plan = read_plan(conn, engine, store, tables, require_all=require_all)
            if plan["plan_sha256"] != expected_digest:
                raise ValueError("Plan changed since it was reviewed; generate and review a new plan")
            append_receipt({"at": datetime.now(ZoneInfo("America/New_York")).isoformat(), "status": "pending",
                            "words": words, **plan})
            protected = [(item, f"{quote(engine, schema)}.{quote(engine, item['table'])}")
                         for item in plan["tables"] if "retention_trigger" in item]
            for item, qualified in protected:
                trigger = quote(engine, item["retention_trigger"])
                conn.exec_driver_sql(f"ALTER TABLE ONLY {qualified} DISABLE TRIGGER {trigger}")
            for action, command in (("truncate", "TRUNCATE TABLE"), ("drop", "DROP TABLE")):
                targets = [f"{quote(engine, schema)}.{quote(engine, item['table'])}"
                           for item in plan["tables"] if item["action"] == action]
                if targets:
                    conn.exec_driver_sql(f"{command} {', '.join(targets)}")
            for item, qualified in protected:
                trigger = quote(engine, item["retention_trigger"])
                conn.exec_driver_sql(f"ALTER TABLE ONLY {qualified} ENABLE TRIGGER {trigger}")
                retention_trigger(conn, item)
            for item in plan["tables"]:
                qualified = f"{quote(engine, schema)}.{quote(engine, item['table'])}"
                exists = bool(conn.scalar(sa.text("SELECT to_regclass(:name) IS NOT NULL"),
                                        {"name": f"{schema}.{item['table']}"}))
                if item["action"] == "drop" and exists:
                    raise ValueError("Dropped table remains after reset")
                if item["action"] == "truncate" and int(conn.scalar(sa.text(f"SELECT count(*) FROM {qualified}"))) != 0:
                    raise ValueError("Truncated table is not empty")
    except Exception as exc:
        if plan is not None:
            append_receipt({"at": datetime.now(ZoneInfo("America/New_York")).isoformat(), "status": "failed",
                            "reason": type(exc).__name__, "words": words, **plan})
        raise
    try:
        append_receipt({"at": datetime.now(ZoneInfo("America/New_York")).isoformat(), "status": "complete",
                        "words": words, **plan})
    except OSError as exc:
        raise ReceiptError("Database committed but the completion receipt failed") from exc
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", choices=sorted(STORE_SCHEMAS), required=True)
    parser.add_argument("--inventory", action="store_true", help="list tables and planner row estimates; change nothing")
    parser.add_argument("--manifest", type=Path, help="explicit per-table drop/truncate plan")
    parser.add_argument("--require-all-tables", action="store_true", help="require a truncate entry for every resettable table in the store")
    parser.add_argument("--apply", action="store_true", help="apply the reviewed plan")
    parser.add_argument("--words", help="operator's exact approval words; required with --apply")
    parser.add_argument("--plan-sha256", help="digest printed by the reviewed plan; required with --apply")
    parser.add_argument("--with-suspended-mirror", action="store_true",
                        help="with --apply: the mirror is suspended (mirror_sql.py status says SUSPENDED) and is restarted after the "
                             "reset; its walsender and idle managed workers may stay connected")
    parser.add_argument("--wait-minutes", type=float, default=0,
                        help="with --apply: wait up to this long for blocking sessions (a suspended mirror's walsender) to leave")
    args = parser.parse_args(argv)
    if args.inventory == (args.manifest is not None):
        return fail("Choose exactly one of --inventory or --manifest")
    if args.require_all_tables and args.inventory:
        return fail("--require-all-tables requires a manifest")
    if args.apply and (not args.words or not args.words.strip() or not args.plan_sha256):
        return fail("--apply requires exact --words and --plan-sha256")
    if not args.apply and (args.words is not None or args.plan_sha256 is not None):
        return fail("--words and --plan-sha256 require --apply")
    from edgar_warehouse.database_connections import store_engine

    try:
        tables = None if args.inventory else load_manifest(args.manifest, args.store)
        engine = store_engine(args.store)
        try:
            if args.inventory:
                return print_inventory(engine, args.store)
            if not args.apply:
                with engine.connect() as conn:
                    plan = read_plan(conn, engine, args.store, tables, require_all=args.require_all_tables)
                show_plan(plan)
                print("Plan only; nothing changed")
                return 0
            wait_for_quiet(engine, args.wait_minutes, mirror_suspended=args.with_suspended_mirror)
            plan = apply_plan(engine, args.store, tables, args.words.strip(), args.plan_sha256,
                              require_all=args.require_all_tables, mirror_suspended=args.with_suspended_mirror)
            show_plan(plan)
            print(f"Applied {len(plan['tables'])} table actions; receipt recorded in the private stores folder")
            return 0
        finally:
            engine.dispose()
    except BlockedError as exc:
        return fail(str(exc))
    except ReceiptError as exc:
        return fail(str(exc) + "; inspect the pending approval receipt before retrying", 3)
    except (KeyError, OSError, ValueError, yaml.YAMLError):
        return fail("Table reset refused; inspect the manifest and store configuration")
    except sa.exc.DBAPIError as exc:
        code = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None) or "database error"
        return fail(f"Table reset refused by the database ({code})")


if __name__ == "__main__":
    raise SystemExit(main())
