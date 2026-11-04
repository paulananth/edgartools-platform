"""A silver table's data quality checks, run on each delivery as it lands
(rebuild priorities ticket 105).

A spec may list `checks`. Each names its `id`, its `check` and the columns it
reads, why it exists (`why`), and what a failure does (`on_fail`):
- `flag` (operator, 2026-10-17: "Flag, land the row"): the row lands, and the
  check's id is written in the row's `quality` column, so nothing is lost and a
  reader can leave flagged rows out;
- `exception`: the row is not landed, and the landing report counts it.

The checks:
- `identifier`: a column's value is a declared identifier type
  (`rules/identifiers/<type>.yaml`): its shape, stand-ins and check digit;
- `in_set`: a column's value is one of the listed values;
- `one_value`: rows sharing a value of `per` hold one value of `column`
  (a level of a hierarchy has one parent). Within the delivery, a row is
  flagged when its value is not the group's most common one; when two values
  are equally common, every row of the group is. It holds only within one
  delivery: split a part into several deliveries and each is checked alone;
- `not_after`: `column` is not after `later` (a start is not after its end); both
  columns are `DATE`, `TIMESTAMP` or `BIGINT` of one type; an empty value passes;
- `reason_if_empty`: `column` is empty exactly when `reason` (a `VARCHAR` column)
  is filled: an empty value with no reason, and a value beside a reason, both fail
  (ticket 175; a blank reason is none). It is the one check that reads an empty value.
`in_set` reads a text column (`VARCHAR`, listed values are text) or a `BIGINT`
column (listed values are whole numbers; every integer is `BIGINT`), compared as delivered; no check reads a
nested column. An empty value passes every check: whether a column may be empty
is its `nullable`. A snapshot table takes no `exception` check: a row kept
out of its delivery would be deleted from the table.

The landing report gives, for each check, the rows that failed it (a row
may fail several), and the rows flagged and refused in all.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from edgar_warehouse.control_contract import Blocked

QUALITY = "quality"  # the column a flagged row's check ids are written to
ON_FAIL = ("flag", "exception")
# Each check and the keys it takes beside id, check, why and on_fail.
ARGUMENTS = {"identifier": {"column", "type"}, "in_set": {"column", "values"}, "one_value": {"column", "per"},
             "not_after": {"column", "later"}, "reason_if_empty": {"column", "reason"}}
ORDERED = ("DATE", "TIMESTAMP", "BIGINT")  # the types `not_after` compares
TEXT, WHOLE = "VARCHAR", "BIGINT"  # the types `in_set` reads: text, or a whole number (every integer is BIGINT)


def check(spec: dict, names: list[str]) -> None:
    """A spec's checks, refused with Blocked unless each can run on its columns."""
    from .spec import postgres_type  # spec.py checks a spec through this module

    seen = set()
    types = {c["name"]: c["type"] for c in spec["columns"]}
    keys = "; ".join(f"{kind}: {', '.join(sorted(args))}" for kind, args in ARGUMENTS.items())
    for item in spec.get("checks") or []:
        kind = item.get("check") if isinstance(item, dict) else None
        if kind not in ARGUMENTS or set(item) != ARGUMENTS[kind] | {"id", "check", "why", "on_fail"}:
            raise Blocked(f"A silver check is one of {sorted(ARGUMENTS)} with id, why, on_fail and its own keys "
                          f"({keys}): {item!r}")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise Blocked(f"Each silver check has its own id: {item['id']!r}")
        seen.add(item["id"])
        if item["on_fail"] not in ON_FAIL:
            raise Blocked(f"Check {item['id']}: on_fail is one of {ON_FAIL}")
        if item["on_fail"] == "exception" and spec["load_mode"] == "snapshot":
            raise Blocked(f"Check {item['id']}: a snapshot table takes no exception check; "
                          "a row kept out of a delivery would be deleted")
        if not isinstance(item["why"], str) or not item["why"].strip():
            raise Blocked(f"Check {item['id']}: why is plain words")
        for role in ("column", "per", "later", "reason"):
            if role in item and item[role] not in names:
                raise Blocked(f"Check {item['id']}: {role} names a column of the spec: {item[role]!r}")
            if role in item and kind == "in_set" and types[item[role]] not in (TEXT, WHOLE):
                raise Blocked(f"Check {item['id']}: in_set reads a {TEXT} or a {WHOLE} column, not {item[role]} "
                              f"({types[item[role]]})")
            if role in item and postgres_type(types[item[role]]) == "jsonb":
                raise Blocked(f"Check {item['id']}: {item[role]} holds nested values, which no check reads")
        if kind == "not_after":
            first, second = types[item["column"]], types[item["later"]]
            if first != second or first not in ORDERED:
                raise Blocked(f"Check {item['id']}: not_after reads two columns of the same type, a date, timestamp or "
                              f"whole-number type, not {item['column']} ({first}) and {item['later']} ({second})")
        if kind == "reason_if_empty" and types[item["reason"]] != TEXT:
            raise Blocked(f"Check {item['id']}: the reason column {item['reason']} is {TEXT}, not {types[item['reason']]}")
        if kind == "identifier":
            from edgar_warehouse.mdm.identifier_types import TYPES

            if item["type"] not in TYPES:
                raise Blocked(f"Check {item['id']}: no identifier type {item['type']!r} in rules/identifiers")
        if kind == "in_set":
            whole = types.get(item["column"]) == WHOLE
            kept = int if whole else str
            if (not isinstance(item["values"], list) or not item["values"]
                    or not all(type(v) is kept for v in item["values"])):
                raise Blocked(f"Check {item['id']}: values lists the allowed values, "
                              f"as {'whole numbers' if whole else 'text'} to match the column")


def run(spec: dict, rows: list[dict]) -> tuple[list[dict], dict]:
    """The delivery's rows with each flagged row's `quality`, without the rows an
    exception refuses, and the count of rows each check flagged or refused."""
    checks = spec.get("checks") or []
    if not checks:
        return rows, {}
    failed: list[list[str]] = [[] for _ in rows]
    counts: dict[str, int] = {}
    for item in checks:
        fails = _FAILS[item["check"]](item, rows)
        counts[item["id"]] = len(fails)
        for number in fails:
            failed[number].append(item["id"])
    refusing = {c["id"] for c in checks if c["on_fail"] == "exception"}
    kept, refused = [], 0
    for row, ids in zip(rows, failed):
        if refusing.intersection(ids):
            refused += 1
            continue
        kept.append({**row, QUALITY: sorted(ids) or None})
    report = {"checks": {c["id"]: {"on_fail": c["on_fail"], "rows_failed": counts[c["id"]]} for c in checks},
              "rows_checked": len(rows), "rows_flagged": sum(1 for row in kept if row[QUALITY]), "rows_refused": refused}
    return kept, report


def _identifier(item: dict, rows: list[dict]) -> list[int]:
    from edgar_warehouse.mdm.identifier_types import TYPES

    kind = TYPES[item["type"]]
    return [n for n, row in enumerate(rows) if not _empty(row.get(item["column"]))
            and kind.refusal(row[item["column"]])[1] is not None]


def _in_set(item: dict, rows: list[dict]) -> list[int]:
    allowed = set(item["values"])
    return [n for n, row in enumerate(rows) if not _empty(row.get(item["column"])) and row[item["column"]] not in allowed]


def _one_value(item: dict, rows: list[dict]) -> list[int]:
    groups: dict[object, list[int]] = defaultdict(list)
    for n, row in enumerate(rows):
        if not _empty(row.get(item["per"])) and not _empty(row.get(item["column"])):
            groups[row[item["per"]]].append(n)
    out = []
    for members in groups.values():
        values = Counter(rows[n][item["column"]] for n in members)
        if len(values) < 2:
            continue
        (top, most), (_, second) = values.most_common(2)
        out += members if most == second else [n for n in members if rows[n][item["column"]] != top]
    return sorted(out)


def _not_after(item: dict, rows: list[dict]) -> list[int]:
    out = []
    for n, row in enumerate(rows):
        first, second = row.get(item["column"]), row.get(item["later"])
        if _empty(first) or _empty(second):
            continue
        if type(first) is not type(second):  # a date delivered as text beside a date: compare their ISO forms
            first, second = str(first), str(second)
        if first > second:
            out.append(n)
    return out


def _reason_if_empty(item: dict, rows: list[dict]) -> list[int]:
    return [n for n, row in enumerate(rows) if _empty(row.get(item["column"])) == _empty(row.get(item["reason"]))]


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


_FAILS: dict[str, Callable[[dict, list[dict]], list[int]]] = {
    "identifier": _identifier, "in_set": _in_set, "one_value": _one_value, "not_after": _not_after,
    "reason_if_empty": _reason_if_empty}
