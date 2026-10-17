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
  are equally common, every row of the group is.
An empty value passes every check: whether a column may be empty is its
`nullable`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from edgar_warehouse.control_contract import Blocked

QUALITY = "quality"  # the column a flagged row's check ids are written to
ON_FAIL = ("flag", "exception")
# Each check and the keys it takes beside id, check, why and on_fail.
ARGUMENTS = {"identifier": {"column", "type"}, "in_set": {"column", "values"}, "one_value": {"column", "per"}}


def check(spec: dict, names: list[str]) -> None:
    """A spec's checks, refused with Blocked unless each can run on its columns."""
    seen = set()
    for item in spec.get("checks") or []:
        kind = item.get("check") if isinstance(item, dict) else None
        if kind not in ARGUMENTS or set(item) != ARGUMENTS[kind] | {"id", "check", "why", "on_fail"}:
            raise Blocked(f"A silver check is one of {sorted(ARGUMENTS)} with id, why, on_fail and its own keys "
                          f"({ {k: sorted(v) for k, v in ARGUMENTS.items()} }): {item!r}")
        if not isinstance(item["id"], str) or not item["id"] or item["id"] in seen:
            raise Blocked(f"Each silver check has its own id: {item['id']!r}")
        seen.add(item["id"])
        if item["on_fail"] not in ON_FAIL:
            raise Blocked(f"Check {item['id']}: on_fail is one of {ON_FAIL}")
        if not isinstance(item["why"], str) or not item["why"].strip():
            raise Blocked(f"Check {item['id']}: why is plain words")
        for role in ("column", "per"):
            if role in item and item[role] not in names:
                raise Blocked(f"Check {item['id']}: {role} names a column of the spec: {item[role]!r}")
        if kind == "identifier":
            from edgar_warehouse.mdm.clean.identifier_types import TYPES

            if item["type"] not in TYPES:
                raise Blocked(f"Check {item['id']}: no identifier type {item['type']!r} in rules/identifiers")
        if kind == "in_set" and (not isinstance(item["values"], list) or not item["values"]):
            raise Blocked(f"Check {item['id']}: values lists the allowed values")


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
    kept = []
    for row, ids in zip(rows, failed):
        if refusing.intersection(ids):
            continue
        kept.append({**row, QUALITY: sorted(ids) or None})
    report = {c["id"]: {("refused" if c["id"] in refusing else "flagged"): counts[c["id"]]} for c in checks}
    return kept, report


def _identifier(item: dict, rows: list[dict]) -> list[int]:
    from edgar_warehouse.mdm.clean.identifier_types import TYPES

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


def _empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


_FAILS: dict[str, Callable[[dict, list[dict]], list[int]]] = {
    "identifier": _identifier, "in_set": _in_set, "one_value": _one_value}
