"""Turn approved profiling findings into a quality block the engine runs, and measure it.

    draft    findings + a column → field map → quality.yaml, QUALITY.md
    measure  a quality.yaml + mapped records (JSON Lines) → counts per check,
             compared with the counts profiling found; one planted record per
             check proves the check can fire

Only the engine's own checks are used (`edgar_warehouse.mdm.clean.quality`):
a defect with no check in its catalog is listed as new code, for a ticket,
never written. Run it where the platform is installed (`uv run python ...`
from the platform checkout).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import yaml

from edgar_warehouse.mdm.clean import quality

# A profiling check → the engine check that carries it. `when` limits it to the
# items whose args fit what the engine test checks exactly.
CATALOG = {
    "missing": {"test": "present@1", "args": lambda a: {}},
    "placeholder": {"test": "placeholder@1", "args": lambda a: {"values": a["values"]}},
    "shape_outlier": {"test": "pattern@1", "args": lambda a: {"regex": a["regex"]}},
    "code_list": {"test": "in_set@1", "args": lambda a: {"values": a["values"]}},
    # The engine's mod 97-10 test reads a 20-character identifier; other families are new code.
    "check_digit": {"test": "lei_check_digit@1", "args": lambda a: {},
                    "when": lambda a: a.get("family") == "mod 97-10" and a.get("length") == 20},
}
# What the check a new-code item needs would test, for its ticket.
NEW_CODE = {
    "check_digit": "the value passes its check-digit family (args.family)",
    "link_not_found": "the value is a key of the part it points at (args.to)",
    "hierarchy_invalid": "the row's parent exists, is not the row itself, is not on a cycle, and is the "
                         "parent its code has; each invalid row is in invalid_rows.jsonl",
    "no_natural_key": "the designed record key is filled and unique",
}
# A value each engine test refuses, for the planted record.
TRIPS = {
    "present@1": None,
    "placeholder@1": "0000",  # all zeros is a placeholder whatever the list
    "pattern@1": "\u0000",
    "in_set@1": "\u0000",
    "lei_check_digit@1": "0" * 20,  # remainder 0 under mod 97; a valid value leaves 1
}


class PlanError(ValueError):
    """Findings or a map the plan cannot use."""


def _check_id(check: str, path: str) -> str:
    """`placeholder` on `fields.address.city` → `placeholder_address_city`."""
    return f"{check}_{path.split('.', 1)[1].replace('.', '_')}"


def draft(findings: dict, part: str, fields: dict[str, str], version: str) -> dict:
    """The quality block for one part, with what it cannot carry listed apart.

    `fields` maps a source column to the record path a check reads
    (`fields.<name>`, `fields.address.<part>` or `matching.<name>`).
    """
    if (findings.get("approval") or {}).get("status") != "approved":
        raise PlanError("the findings are not approved: profile and approve them first")
    found = next((p for p in findings["parts"] if p["part"] == part), None)
    if found is None:
        raise PlanError(f"no part {part} in the findings")
    checks, fixes, new_code, unmapped, expected = [], [], [], [], {}
    for item in found.get("quality") or []:
        target = CATALOG.get(item["check"])
        args = item.get("args") or {}
        if item.get("proposal") == "blank" and args.get("values"):
            target = {"fix": "blank_values@1"}  # the values are written for "none": blanked, not checked
        elif target is None or not target.get("when", lambda a: True)(args):
            new_code.append({**item, "check_would_test": NEW_CODE.get(item["check"])})
            continue
        path = fields.get(item["column"])
        if path is None:
            unmapped.append(item)
            continue
        check_id = _check_id(item["check"], path)
        if "fix" in target:
            fixes.append({"id": check_id, "fix": target["fix"], "args": {"field": path, "values": args["values"]}})
            expected[check_id] = item["rows"]
            continue
        checks.append({"id": check_id, "test": target["test"], "value": path,
                       "on_fail": item["proposal"] if item["proposal"] in quality.ON_FAIL else "flag",
                       **({"args": target["args"](item["args"])} if target["args"](item["args"]) else {})})
        expected[check_id] = item["rows"]
    block = {"version": version, **({"fixes": fixes} if fixes else {}), "checks": checks}
    quality.check_quality(block)
    return {"part": part, "block": block, "expected": expected, "new_code": new_code, "unmapped": unmapped,
            "items": found.get("quality") or []}


def mapped(row: dict, fields: dict[str, str]) -> dict:
    """A source row as the record a check reads: `{"fields": {...}, "matching": {...}}`."""
    record: dict = {"fields": {}, "matching": {}}
    for column, path in fields.items():
        area, *parts = path.split(".")
        target = record[area]
        for name in parts[:-1]:
            target = target.setdefault(name, {})
        target[parts[-1]] = row.get(column)
    return record


def measure(block: dict, records: list[dict]) -> dict[str, int]:
    """How many records each fix changed and each check fired on. Each check runs on its own after the
    fixes, as profiling counts it: an `exception` elsewhere does not hide a record from it."""
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

    fixes = block.get("fixes") or []
    fired = {i["id"]: 0 for i in [*fixes, *(block.get("checks") or [])]}
    for record in records:
        result = quality.apply({**block, "checks": []}, copy.deepcopy(record.get("fields") or {}),
                               copy.deepcopy(record.get("matching")))
        for fix_id in result.get("fixes") or {}:
            fired[fix_id] += 1
        for check in block.get("checks") or []:
            try:
                result = quality.apply({**block, "checks": [check]}, copy.deepcopy(record.get("fields") or {}),
                                       copy.deepcopy(record.get("matching")))
            except UnsupportedRecord:
                fired[check["id"]] += 1
                continue
            fired[check["id"]] += bool(result.get("flags") or result.get("withheld"))
    return fired


def planted_fire(block: dict) -> dict[str, bool | None]:
    """One made-up record per check, holding a value that check must refuse: did it fire? None when this
    helper has no planted value for the check's test."""
    out = {}
    for c in block.get("checks") or []:
        if c["test"] not in TRIPS:
            out[c["id"]] = None
            continue
        alone = {**block, "checks": [c], "fixes": []}
        record = mapped({"value": TRIPS[c["test"]]}, {"value": c["value"]})
        out[c["id"]] = measure(alone, [record])[c["id"]] == 1
    return out


def loads(path: Path, source_code: str) -> set[str]:
    """Load a written quality.yaml as the rules loader does, beside a stub contract, and check it as
    registration does. Returns the reasons the contract must list as non-blocking."""
    import tempfile

    from edgar_warehouse.rules import files

    with tempfile.TemporaryDirectory() as folder:
        stub = Path(folder) / "source.yaml"
        stub.write_text(yaml.safe_dump({"mdm": {source_code: {"contract": {}}}}), encoding="utf-8")
        (Path(folder) / "quality.yaml").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        block = files.load_source(stub)["mdm"][source_code]["contract"]["quality"]
    quality.check_quality(block)
    return quality.exception_reasons(block)


def write(plan: dict, source_code: str, path: Path) -> Path:
    """`rules/sources/<source>/quality.yaml` shape: version, then quality per source code."""
    block = plan["block"]
    body = {"version": block["version"], "quality": {source_code: {k: v for k, v in block.items() if k != "version"}}}
    path.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def report(plan: dict) -> str:
    lines = [f"# Data quality plan: {plan['part']}", "", f"Version **{plan['block']['version']}**. "
             "Each check's `on_fail`, and each fix, is a proposal: the operator decides each one.", "",
             "| Check or fix | Engine | Reads | on_fail | Rows found |", "|---|---|---|---|---|"]
    for f in plan["block"].get("fixes") or []:
        lines.append(f"| {f['id']} | {f['fix']} | {f['args']['field']} | (a fix) | {plan['expected'][f['id']]} |")
    for c in plan["block"]["checks"]:
        lines.append(f"| {c['id']} | {c['test']} | {c['value']} | {c['on_fail']} | {plan['expected'][c['id']]} |")
    lines += ["", "Examples per item are in the findings (`quality`), masked for a personal column."]
    for title, items, extra in (("New code (log a ticket; not written)", plan["new_code"], "check_would_test"),
                                ("No field mapped (map the column, or drop the item)", plan["unmapped"], "why")):
        if items:
            lines += ["", f"## {title}", "", "| Check | Column | Rows | Notes |", "|---|---|---|---|"]
            lines += [f"| {i['check']} | {i['column']} | {i['rows']} | {i.get(extra) or ''} |" for i in items]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quality_plan.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("draft", help="approved findings + a column → field map → quality.yaml and QUALITY.md")
    d.add_argument("--findings", required=True, type=Path)
    d.add_argument("--part", required=True)
    d.add_argument("--map", required=True, type=Path, help="YAML: {<column>: fields.<name> | matching.<name>}")
    d.add_argument("--version", required=True, help="the quality version name; a change is a new name")
    d.add_argument("--source-code", required=True, help="the Dataset Contract code the block belongs to")
    d.add_argument("--out", required=True, type=Path, help="a folder")
    m = sub.add_parser("measure", help="run a quality.yaml on mapped records and compare with profiling")
    m.add_argument("--quality", required=True, type=Path)
    m.add_argument("--source-code", required=True)
    m.add_argument("--records", required=True, type=Path, help="JSON Lines of {fields, matching} records")
    m.add_argument("--expected", type=Path, help="the draft's expected.yaml, to compare counts")
    args = parser.parse_args(argv)
    if args.command == "draft":
        plan = draft(yaml.safe_load(args.findings.read_text()), args.part, yaml.safe_load(args.map.read_text()),
                     args.version)
        args.out.mkdir(parents=True, exist_ok=True)
        write(plan, args.source_code, args.out / "quality.yaml")
        (args.out / "expected.yaml").write_text(yaml.safe_dump(plan["expected"], sort_keys=False))
        (args.out / "QUALITY.md").write_text(report(plan), encoding="utf-8")
        print(f"wrote {args.out}/quality.yaml, expected.yaml and QUALITY.md: {len(plan['block']['checks'])} checks, "
              f"{len(plan['new_code'])} new code, {len(plan['unmapped'])} unmapped")
        return 0
    body = yaml.safe_load(args.quality.read_text())
    block = {"version": body["version"], **body["quality"][args.source_code]}
    reasons = loads(args.quality, args.source_code)
    if reasons:
        print(f"list these in the contract's nonblocking_deferred_reasons: {', '.join(sorted(reasons))}")
    records = [json.loads(line) for line in args.records.read_text().splitlines() if line.strip()]
    counts, planted = measure(block, records), planted_fire(block)
    expected = yaml.safe_load(args.expected.read_text()) if args.expected else {}
    ok = all(v is not False for v in planted.values()) and all(counts.get(k) == v for k, v in expected.items())
    notes = {True: "", False: "; the planted record did NOT fire", None: "; no planted record for this test"}
    for check_id, n in counts.items():
        print(f"{check_id}: {n} records" + (f" (profiling found {expected[check_id]})" if check_id in expected else "")
              + notes[planted.get(check_id, True)])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
