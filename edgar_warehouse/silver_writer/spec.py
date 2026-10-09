"""A silver table spec (docs/specs/profiling/findings.md section 6), checked before
any table is made from it.

The spec does not depend on the store: types are the logical types profiling
reports, and each sink maps them to its own (`POSTGRES` here).
"""

from __future__ import annotations

import re

from edgar_warehouse.control_contract import Blocked, digest

KEYS = {"table", "grain", "columns", "key", "links", "time", "partition", "load_mode", "why"}
OPTIONAL = {"definition"}
COLUMN_KEYS = {"name", "type", "nullable", "definition", "source", "sensitivity"}
LINK_KEYS = {"columns", "kind", "source_code", "source_key", "mdm_id_column", "inclusion"}
LOAD_MODES = ("append", "upsert", "snapshot")
LOADED_AT = "loaded_at"  # the as-at column the writer adds when no source column holds it
NAME_BYTES = 63  # PostgreSQL cuts longer names silently; two long names could become one

# Profiling's logical types (DuckDB's names) and the PostgreSQL type each lands
# as. Integers are never narrower than BIGINT (CLAUDE.md, schema conventions);
# an integer wider than BIGINT keeps every digit as numeric. Nested values are jsonb.
POSTGRES = {
    "BOOLEAN": "boolean",
    "TINYINT": "bigint", "SMALLINT": "bigint", "INTEGER": "bigint", "BIGINT": "bigint",
    "UTINYINT": "bigint", "USMALLINT": "bigint", "UINTEGER": "bigint",
    "UBIGINT": "numeric(20,0)", "HUGEINT": "numeric(39,0)", "UHUGEINT": "numeric(39,0)",
    "FLOAT": "double precision", "DOUBLE": "double precision",
    "VARCHAR": "text", "UUID": "uuid", "BLOB": "bytea",
    "DATE": "date", "TIME": "time", "TIMESTAMP": "timestamp",
    "TIMESTAMP WITH TIME ZONE": "timestamp with time zone", "INTERVAL": "interval",
    "JSON": "jsonb",
}
_DECIMAL = re.compile(r"^DECIMAL\((\d+),(\d+)\)$")
_NESTED = re.compile(r"^(STRUCT|MAP|UNION)\(|\[\d*\]$")


def postgres_type(logical: str) -> str:
    """The PostgreSQL type a logical type lands as; an unknown type is refused, never read as text."""
    found = POSTGRES.get(logical)
    if found:
        return found
    decimal = _DECIMAL.match(logical.replace(" ", ""))
    if decimal:
        return f"numeric({decimal[1]},{decimal[2]})"
    if _NESTED.search(logical):
        return "jsonb"
    raise Blocked(f"No silver type for {logical!r}: name the logical type in the spec")


def nested(logical: str) -> bool:
    return postgres_type(logical) == "jsonb"


def check(spec: dict) -> dict:
    """The spec, checked: every key the format names, real types, names a store
    keeps apart, links that name their master, and a load mode. Refuses with Blocked."""
    if not isinstance(spec, dict) or not KEYS <= set(spec) or set(spec) - KEYS - OPTIONAL:
        raise Blocked(f"A silver table spec holds {sorted(KEYS)} (and optionally {sorted(OPTIONAL)})")
    _name(spec["table"], "table")
    columns = spec["columns"]
    if not isinstance(columns, list) or not columns:
        raise Blocked("A silver table spec names at least one column")
    names = []
    for column in columns:
        if not isinstance(column, dict) or not {"name", "type", "nullable"} <= set(column) or set(column) - COLUMN_KEYS:
            raise Blocked(f"A column holds name, type and nullable, and only {sorted(COLUMN_KEYS)}: {column!r}")
        names.append(_name(column["name"], "column"))
        postgres_type(column["type"])
        if not isinstance(column["nullable"], bool):
            raise Blocked(f"Column {column['name']}: nullable is true or false")
    key = spec["key"]
    if not isinstance(key, list) or not key or not set(key) <= set(names) or len(set(key)) != len(key):
        raise Blocked(f"The key names one or more of the spec's columns, each once: {key!r}")
    if any(_column(spec, k)["nullable"] for k in key):
        raise Blocked("A key column is never empty: mark it nullable false")
    if spec["load_mode"] not in LOAD_MODES:
        raise Blocked(f"load_mode is one of {LOAD_MODES}")
    added = []
    for link in spec["links"] or []:
        if not isinstance(link, dict) or not {"columns", "kind", "source_code", "source_key", "mdm_id_column"} <= set(link) \
                or set(link) - LINK_KEYS - {"to_part"}:
            raise Blocked(f"A link holds columns, kind, source_code, source_key and mdm_id_column: {link!r}")
        if not link["kind"] or not link["source_code"]:
            raise Blocked(f"Link on {link['source_key']}: name the master's kind and Dataset Contract "
                          "(data-onboarding fills them from the onboarded master)")
        if link["columns"] != [link["source_key"]] or link["source_key"] not in names:
            raise Blocked(f"A link points from one column of the spec, its source key: {link!r}")
        added.append(_name(link["mdm_id_column"], "column"))
    time = spec["time"]
    if not isinstance(time, dict) or set(time) != {"as_of", "as_at", "event_time"} or not time["as_at"]:
        raise Blocked("time holds as_of, as_at and event_time; as_at is always named")
    for role in ("as_of", "event_time"):
        if time[role] is not None and time[role] not in names:
            raise Blocked(f"time.{role} names a column of the spec: {time[role]!r}")
    if time["as_at"] not in names:
        if time["as_at"] != LOADED_AT:
            raise Blocked(f"time.as_at names a column of the spec, or {LOADED_AT!r}, which the writer adds")
        added.append(LOADED_AT)
    every = names + added
    if len(set(every)) != len(every):
        raise Blocked(f"Two columns of the table share a name: {sorted(n for n in every if every.count(n) > 1)}")
    if not isinstance(spec["partition"], list) or not set(spec["partition"]) <= set(names):
        raise Blocked("partition names columns of the spec")
    return spec


def sha256(spec: dict) -> str:
    return digest(spec)


def columns(spec: dict) -> list[str]:
    """Every column of the table: the spec's columns, each link's MDM id column, and loaded_at when added."""
    return [c["name"] for c in spec["columns"]] + mdm_id_columns(spec) + added_time(spec)


def mdm_id_columns(spec: dict) -> list[str]:
    return [link["mdm_id_column"] for link in spec["links"] or []]


def added_time(spec: dict) -> list[str]:
    return [LOADED_AT] if spec["time"]["as_at"] == LOADED_AT and LOADED_AT not in [c["name"] for c in spec["columns"]] else []


def _column(spec: dict, name: str) -> dict:
    return next(c for c in spec["columns"] if c["name"] == name)


def _name(value, what: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > NAME_BYTES or "\x00" in value:
        raise Blocked(f"A {what} name is text of 1 to {NAME_BYTES} bytes: {value!r}")
    return value
