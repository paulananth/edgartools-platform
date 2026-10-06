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
    # The engine's mod 97-10 test reads a 20-character identifier (ISO 17442); other families are new code.
    "check_digit": {"test": "lei_check_digit@1", "args": lambda a: {},
                    "when": lambda a: a.get("family") == "mod97_10" and a.get("length") == 20},
}
# A value each engine test refuses, for the planted record.
TRIPS = {"present@1": None, "placeholder@1": "NONE", "pattern@1": "\u0000", "in_set@1": "\u0000",
         "lei_check_digit@1": "0" * 19 + "1"}


class PlanError(ValueError):
    """Findings or a map the plan cannot use."""


def _check_id(check: str, path: str) -> str:
    return f"{check}_{path.rsplit('.', 1)[-1]}"


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
    checks, new_code, unmapped, expected = [], [], [], {}
    for item in found.get("quality") or []:
        target = CATALOG.get(item["check"])
        if target is None or not target.get("when", lambda a: True)(item.get("args") or {}):
            new_code.append(item)
            continue
        path = fields.get(item["column"])
        if path is None:
            unmapped.append(item)
            continue
        check_id = _check_id(item["check"], path)
        checks.append({"id": check_id, "test": target["test"], "value": path,
                       "on_fail": item["proposal"] if item["proposal"] in quality.ON_FAIL else "flag",
                       **({"args": target["args"](item["args"])} if target["args"](item["args"]) else {})})
        expected[check_id] = item["rows"]
    block = {"version": version, "checks": checks}
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
    """How many records each check fired on. An `exception` sets its record aside, so later checks
    do not see it, as in a run."""
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

    fired = {c["id"]: 0 for c in block.get("checks") or []}
    withhold = {}
    for c in block.get("checks") or []:
        if c["on_fail"] == "withhold":
            withhold.setdefault(c["value"], []).append(c["id"])
    for record in records:
        record = copy.deepcopy(record)
        try:
            result = quality.apply(block, record.get("fields") or {}, record.get("matching"))
        except UnsupportedRecord as exc:
            fired[exc.args[0].removeprefix("quality_")] += 1
            continue
        for check_id in result.get("flags") or []:
            fired[check_id] += 1
        for path in result.get("withheld") or []:
            for check_id in withhold.get(path, []):
                fired[check_id] += 1
    return fired


def planted_fire(block: dict) -> dict[str, bool]:
    """One made-up record per check, holding a value that check must refuse: did it fire?"""
    out = {}
    for c in block.get("checks") or []:
        alone = {**block, "checks": [c], "fixes": []}
        record = mapped({"value": TRIPS[c["test"]]}, {"value": c["value"]})
        out[c["id"]] = measure(alone, [record])[c["id"]] == 1
    return out


def write(plan: dict, source_code: str, path: Path) -> Path:
    """`rules/sources/<source>/quality.yaml` shape: version, then quality per source code."""
    block = plan["block"]
    body = {"version": block["version"], "quality": {source_code: {"checks": block["checks"]}}}
    path.write_text(yaml.safe_dump(body, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def report(plan: dict) -> str:
    lines = [f"# Data quality plan: {plan['part']}", "", f"Version **{plan['block']['version']}**. "
             "Each check's `on_fail` is a proposal: the operator decides each one.", "",
             "| Check | Engine test | Reads | on_fail | Rows found | Examples |", "|---|---|---|---|---|---|"]
    rows = {i: n for i, n in plan["expected"].items()}
    for c in plan["block"]["checks"]:
        item = next(i for i in plan["items"] if _check_id(i["check"], c["value"]) == c["id"])
        lines.append(f"| {c['id']} | {c['test']} | {c['value']} | {c['on_fail']} | {rows[c['id']]} | "
                     f"{', '.join(map(str, item['examples']))} |")
    for title, items in (("New code (log a ticket; not written)", plan["new_code"]),
                         ("No field mapped (map the column, or drop the item)", plan["unmapped"])):
        if items:
            lines += ["", f"## {title}", "", "| Check | Column | Rows | Why |", "|---|---|---|---|"]
            lines += [f"| {i['check']} | {i['column']} | {i['rows']} | {i.get('why', '')} |" for i in items]
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
    quality.check_quality(block)
    records = [json.loads(line) for line in args.records.read_text().splitlines() if line.strip()]
    counts, planted = measure(block, records), planted_fire(block)
    expected = yaml.safe_load(args.expected.read_text()) if args.expected else {}
    ok = all(planted.values()) and all(counts.get(k) == v for k, v in expected.items())
    for check_id, n in counts.items():
        print(f"{check_id}: {n} records" + (f" (profiling found {expected[check_id]})" if check_id in expected else "")
              + ("" if planted[check_id] else "; the planted record did NOT fire"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
