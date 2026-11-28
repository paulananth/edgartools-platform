"""A silver table spec (docs/specs/profiling/findings.md section 6), checked before
any table is made from it.

The spec does not depend on the store: types are the logical types profiling
reports, and each sink maps them to its own (`POSTGRES` here).
"""

from __future__ import annotations

import re

from edgar_warehouse.control_contract import Blocked

from .checks import QUALITY
from .checks import check as check_quality

KEYS = {"table", "grain", "columns", "key", "links", "time", "partition", "load_mode", "why"}
OPTIONAL = {"definition", "checks", "may_be_empty", "master_columns", "master_through", "holds_no_master"}
COLUMN_KEYS = {"name", "type", "nullable", "definition", "source", "sensitivity"}
LINK_KEYS = {"columns", "kinds", "source_code", "identifier", "venue", "to_part", "source_key", "inclusion"}
# What builds the table: a spec that differs from the registered one only outside these (its links, its words) is
# the same table (operator, 2026-11-28: "Compare table shape (Recommended)").
COLUMN_SHAPE = ("name", "type", "nullable")
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


def check(spec: dict) -> dict:
    """The spec, checked: every key the format names, real types, names a store
    keeps apart, links that name their master, and a load mode. Refuses with Blocked."""
    if not isinstance(spec, dict) or not KEYS <= set(spec) or set(spec) - KEYS - OPTIONAL:
        raise Blocked(f"A silver table spec holds {sorted(KEYS)} (and optionally {sorted(OPTIONAL)})")
    _name(spec["table"], "table")
    for field in ("grain", "why"):
        _words(spec[field], field, required=True)
    _words(spec.get("definition"), "definition")
    columns = spec["columns"]
    if not isinstance(columns, list) or not columns:
        raise Blocked("A silver table spec names at least one column")
    names = []
    for column in columns:
        if not isinstance(column, dict) or not {"name", "type", "nullable"} <= set(column) or set(column) - COLUMN_KEYS:
            raise Blocked(f"A column holds name, type and nullable, and only {sorted(COLUMN_KEYS)}: {column!r}")
        names.append(_name(column["name"], "column"))
        if not isinstance(column["type"], str):
            raise Blocked(f"Column {column['name']}: type is a logical type name")
        postgres_type(column["type"])
        for field in ("definition", "source"):
            _words(column.get(field), f"column {column['name']} {field}")
        if column.get("sensitivity") not in (None, "none", "personal", "sensitive_personal"):
            raise Blocked(f"Column {column['name']}: sensitivity is none, personal or sensitive_personal")
        if not isinstance(column["nullable"], bool):
            raise Blocked(f"Column {column['name']}: nullable is true or false")
    key = spec["key"]
    if not isinstance(key, list) or not key or not set(key) <= set(names) or len(set(key)) != len(key):
        raise Blocked(f"The key names one or more of the spec's columns, each once: {key!r}")
    if any(_column(spec, k)["nullable"] for k in key):
        raise Blocked("A key column is never empty: mark it nullable false")
    if spec["load_mode"] not in LOAD_MODES:
        raise Blocked(f"load_mode is one of {LOAD_MODES}")
    if "may_be_empty" in spec and (spec["may_be_empty"] is not True or spec["load_mode"] != "snapshot"):
        raise Blocked("may_be_empty is true, and only on a snapshot: a snapshot of a list its parent owns "
                      "is empty when the parent has none")
    added = []
    for link in spec["links"] or []:
        if not isinstance(link, dict) or not {"columns", "kinds", "source_key"} <= set(link) \
                or set(link) - LINK_KEYS:
            raise Blocked(f"A link holds columns, kinds, source_code or identifier, and source_key: {link!r}")
        finds = [link.get(by) for by in ("source_code", "identifier") if link.get(by) is not None]
        kinds = link["kinds"]
        if not isinstance(kinds, list) or not kinds or not all(isinstance(k, str) and k for k in kinds) \
                or len(set(kinds)) != len(kinds) or len(finds) != 1 or not isinstance(finds[0], str) or not finds[0]:
            raise Blocked(f"Link on {link['source_key']}: name the master's kinds and either the Dataset Contract whose "
                          "record key the column holds (source_code) or the identifier the master holds (identifier)")
        if "venue" in link and (not link.get("identifier") or link["venue"] not in names):
            raise Blocked(f"Link on {link['source_key']}: venue names the column holding the row's exchange, "
                          "for a link found by an identifier")
        if link["columns"] != [link["source_key"]] or link["source_key"] not in names:
            raise Blocked(f"A link points from one column of the spec, its source key: {link!r}")
        if link.get("inclusion") is not None and not (isinstance(link["inclusion"], (int, float))
                                                      and not isinstance(link["inclusion"], bool)
                                                      and 0 <= link["inclusion"] <= 1):
            raise Blocked(f"Link on {link['source_key']}: inclusion is a share from 0 to 1")
    ways = [bool(spec["links"]), bool(spec.get("master_columns")), bool(spec.get("master_through")),
            spec.get("holds_no_master") is True]
    if sum(ways) != 1:
        raise Blocked("A table finds its master exactly one way: links (a key found in master_binding), master_columns "
                      "(columns that hold master ids) or master_through (the table whose key it carries), or says it "
                      "holds_no_master (a table of records no master holds)")
    for column in spec.get("master_columns") or []:
        if column not in names:
            raise Blocked(f"master_columns names a column of the spec: {column!r}")
    if "master_through" in spec and not (isinstance(spec["master_through"], str) and spec["master_through"]):
        raise Blocked("master_through names the table whose key this table carries")
    check_quality(spec, names)
    added += quality_columns(spec)
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


def columns(spec: dict) -> list[str]:
    """Every column of the table: the spec's columns, the quality column when the spec has
    checks, and loaded_at when added. A linked master is found by a join on master_binding, so no column is added for its id."""
    return [c["name"] for c in spec["columns"]] + quality_columns(spec) + added_time(spec)


def quality_columns(spec: dict) -> list[str]:
    """The column a flagged row's check ids are written to, when the spec has checks."""
    return [QUALITY] if spec.get("checks") else []


def shape(spec: dict) -> dict:
    """What builds the spec's table: its columns' names, types and nullability, key, partition, checks (without their
    words), load mode and as-at column. Two specs of one shape are one table."""
    return {"table": spec["table"], "columns": [{k: c[k] for k in COLUMN_SHAPE} for c in spec["columns"]],
            "key": spec["key"], "partition": spec["partition"],
            "checks": [{k: v for k, v in check.items() if k != "why"} for check in spec.get("checks") or []],
            "load_mode": spec["load_mode"], "as_at": spec["time"]["as_at"]}


def describe_link(link: dict) -> str:
    """How a link finds its master, in words: the record key of a Dataset Contract, or an identifier."""
    kinds = " or ".join(link["kinds"])
    if link.get("identifier"):
        venue = f", by the venue in `{link['venue']}` when several hold it" if link.get("venue") else ""
        return f"the {kinds} that alone holds `{link['source_key']}` as its {link['identifier']} identifier{venue}"
    return f"the {kinds} whose `{link['source_code']}` record key is `{link['source_key']}`"



def added_time(spec: dict) -> list[str]:
    return [LOADED_AT] if spec["time"]["as_at"] == LOADED_AT and LOADED_AT not in [c["name"] for c in spec["columns"]] else []


def _column(spec: dict, name: str) -> dict:
    return next(c for c in spec["columns"] if c["name"] == name)


def quote(name: str) -> str:
    """A PostgreSQL identifier, written by hand: SQLAlchemy's quoting doubles `%`
    for its own parameter formatting, which statements sent as written must not."""
    return '"' + name.replace('"', '""') + '"'


def _words(value, what: str, required: bool = False) -> None:
    if (value is None and not required) or (isinstance(value, str) and value.strip()):
        return
    raise Blocked(f"{what} is plain words" + ("" if required else ", or empty"))


def _name(value, what: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > NAME_BYTES or "\x00" in value:
        raise Blocked(f"A {what} name is text of 1 to {NAME_BYTES} bytes: {value!r}")
    return value
