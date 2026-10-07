"""A reference table kept as a map of code to fields, as a code set version and back.

Each field becomes either the code's label or a crosswalk row to another code
set (one the import also drafts, or an outside standard). A field with no place
refuses the import, so nothing is dropped; `rebuild` gives the map back exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from edgar_warehouse.control_contract import Blocked

from .store import OUTSIDE


@dataclass(frozen=True)
class Crosswalk:
    """Where one field of the table goes: a code of `to_set` at `to_version`."""

    field: str
    to_set: str
    to_version: str
    match_type: str

    @classmethod
    def parse(cls, text: str) -> "Crosswalk":
        """`<field>=<code set>@<version>:<match type>`, e.g. `iso=iso-3166@outside:exact`."""
        try:
            field, target = text.split("=", 1)
            target, match_type = target.rsplit(":", 1)
            to_set, to_version = target.split("@", 1)
        except ValueError as exc:
            raise Blocked(f"A crosswalk is <field>=<code set>@<version>:<match type>, not {text!r}") from exc
        return cls(field, to_set, to_version, match_type)


def draft(table: dict[str, dict], *, label: str, crosswalks: list[Crosswalk], source: str) -> dict:
    """The codes, preferred labels and crosswalk rows of a table, plus the codes
    of each crosswalk target RDM holds (its distinct values, labelled as written)."""
    fields = {label, *(c.field for c in crosswalks)}
    codes, labels, rows = [], [], []
    targets: dict[str, set] = {c.to_set: set() for c in crosswalks if c.to_version != OUTSIDE}
    for code, row in table.items():
        extra = set(row) - fields
        if extra:
            raise Blocked(f"Code {code!r} has fields with no place in the code set: {sorted(extra)}")
        if not row.get(label):
            raise Blocked(f"Code {code!r} has no {label}")
        codes.append({"code": str(code), "label": str(row[label])})
        labels.append({"code": str(code), "label": str(row[label]), "kind": "preferred", "source": source})
        for c in crosswalks:
            value = row.get(c.field)
            if value is None:
                continue
            rows.append({"from_code": str(code), "to_set": c.to_set, "to_version": c.to_version,
                         "to_code": str(value), "match_type": c.match_type})
            if c.to_set in targets:
                targets[c.to_set].add(str(value))
    return {"codes": codes, "labels": labels, "crosswalk": rows,
            "targets": {name: [{"code": v, "label": v} for v in sorted(values)] for name, values in targets.items()}}


def as_version(found: dict) -> list[dict]:
    """A draft's codes as a stored version reads back: crosswalk rows on their code."""
    rows = {c["code"]: {**c, "crosswalk": []} for c in found["codes"]}
    for x in found["crosswalk"]:
        rows[x["from_code"]]["crosswalk"].append(x)
    return list(rows.values())


def rebuild(codes: list[dict], *, label: str, crosswalks: list[Crosswalk]) -> dict[str, dict]:
    """The table back from a version's codes: the inverse of `draft`."""
    table = {}
    for row in codes:
        out = {label: row["label"]}
        for c in crosswalks:
            hits = [x["to_code"] for x in row["crosswalk"]
                    if (x["to_set"], x["to_version"], x["match_type"]) == (c.to_set, c.to_version, c.match_type)]
            if len(hits) > 1:
                raise Blocked(f"Code {row['code']!r} maps to {len(hits)} codes of {c.to_set}")
            out[c.field] = hits[0] if hits else None
        table[row["code"]] = out
    return table
