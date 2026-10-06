"""Quality items found while profiling: rows, masked examples, and invalid hierarchy rows marked."""

import csv
import json
import sys
from pathlib import Path

import pytest
import yaml

pytest.importorskip("duckdb")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
from profiling import identifiers, report, run  # noqa: E402


def _luhn_value(n: int) -> str:
    body = f"{n:09d}"
    for digit in "0123456789":
        if identifiers.luhn(body + digit):
            return body + digit
    raise AssertionError


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as handle:
        out = csv.writer(handle)
        out.writerow(header)
        out.writerows(rows)


@pytest.fixture(scope="module")
def found(tmp_path_factory):
    """Planted defects, one of each kind, in a set with no real source."""
    base = tmp_path_factory.mktemp("quality")
    folder = base / "set"
    folder.mkdir()
    accounts = []
    for n in range(1, 401):
        ref = f"AB{n:04d}" if n not in (7, 8) else f"A{n}"  # two values off the one shape
        status = ["open", "closed", "held"][n % 3]
        note = "N/A" if n in (11, 12, 13) else f"note {n}"  # placeholders in a text column
        issued = _luhn_value(1000 + n) if n != 20 else f"{1000 + n:09d}5"  # one check digit wrong
        if identifiers.luhn(issued) and n == 20:
            issued = f"{1000 + n:09d}6"
        accounts.append([n, ref, status, note, issued])
    _write(folder / "account.csv", ["account_id", "ref_code", "status", "note", "issued_no"], accounts)
    nodes = [["N001", ""]] + [[f"N{n:03d}", f"N{(n - 1) // 3 + 1:03d}"] for n in range(2, 121)]
    nodes[40][1] = "n014"     # an orphan whose parent exists in another case: an evidence-backed fix
    nodes[41][1] = "ZZZ999"   # an orphan with no near match: needs a steward
    _write(folder / "node.csv", ["node_id", "parent_node_id"], nodes)
    findings = run.profile_inputs({"set": str(folder)}, "planted")
    report.write(findings, base / "out")
    return findings, base / "out"


def _items(findings, part, check):
    p = next(x for x in findings["parts"] if x["part"].endswith(part))
    return [q for q in p["quality"] if q["check"] == check]


def test_shape_outliers_have_rows_examples_and_a_pattern(found):
    findings, _ = found
    item, = _items(findings, "account", "shape_outlier")
    assert item["column"] == "ref_code" and item["rows"] == 2
    assert set(item["examples"]) == {"A7", "A8"}
    assert item["args"]["regex"] == "[A-Z][A-Z][0-9][0-9][0-9][0-9]"


def test_placeholders_are_counted_with_their_values(found):
    findings, _ = found
    item, = _items(findings, "account", "placeholder")
    assert item["column"] == "note" and item["rows"] == 3 and item["examples"] == ["N/A"]
    assert item["proposal"] == "withhold"


def test_check_digit_failures_name_the_family(found):
    findings, _ = found
    item, = _items(findings, "account", "check_digit")
    assert item["column"] == "issued_no" and item["rows"] == 1 and item["args"]["family"] == "luhn"


def test_a_code_list_gets_a_guard_for_codes_not_seen(found):
    findings, _ = found
    item, = [q for q in _items(findings, "account", "code_list") if q["column"] == "status"]
    assert item["rows"] == 0 and sorted(item["args"]["values"]) == ["closed", "held", "open"]
    assert item["proposal"] == "flag"


def test_invalid_hierarchy_rows_are_marked_with_fixes_or_a_steward(found):
    findings, out = found
    h, = [x for x in findings["hierarchies"] if x["part"].endswith("node") and x["evidence_kind"] == "parent_column"]
    assert h["orphans"] == 2 and h["invalid_rows"] == 2
    item, = _items(findings, "node", "hierarchy_invalid")
    assert item["rows"] == 2 and len(item["examples"]) == 2
    marked = [json.loads(line) for line in (out / "invalid_rows.jsonl").read_text().splitlines()]
    by_parent = {m["value"]: m for m in marked}
    assert by_parent["n014"]["fix"] == "N014" and "case" in by_parent["n014"]["fix_evidence"]
    assert by_parent["ZZZ999"]["fix"] is None and by_parent["ZZZ999"]["needs_steward"] is True
    assert {tuple(m["key"].values()) for m in marked} == {("N041",), ("N042",)}
    assert "marked_rows" not in yaml.safe_load((out / "findings.yaml").read_text())


def test_compare_lists_codes_not_in_the_approved_code_list():
    from profiling import drift

    def findings(values, cls="transaction"):
        part = {"part": "p", "class": cls, "rows": 10, "record_key": {"columns": ["id"], "found": True},
                "columns": [], "code_lists": [],
                "quality": [{"check": "code_list", "column": "status", "args": {"values": values}}]}
        return {"parts": [part], "relationships": [], "hierarchies": []}

    items = drift.compare(findings(["held", "open"]), findings(["closed", "open"]))
    item, = [i for i in items if i["drift"] == "codes_new"]
    assert item["column"] == "status" and "closed" in item["detail"] and item["handled_by"] == "data-quality"
    item, = [i for i in drift.compare(findings(["a"], "reference"), findings(["a", "b"], "reference"))
             if i["drift"] == "codes_new"]
    assert item["handled_by"] == "rdm"
