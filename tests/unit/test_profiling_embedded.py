"""An entity carried inside another part becomes a part of its own; nested records are identified by structure."""

import json
import sys
from pathlib import Path

import pytest
import yaml

pytest.importorskip("duckdb")  # in the mdm extra, which CI installs

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "data-profiling" / "scripts"))
import profile_data  # noqa: E402

WORDS = ["North", "South", "East", "West", "Harbor", "Summit", "River", "Stone", "Maple", "Cedar"]


def _documents(path: Path) -> None:
    # 180 documents: each names one of 60 parties (an issued-looking id, a name and an address)
    # and lists 1 to 3 lines. An id with only a name would be a code list with its label.
    with path.open("w") as out:
        for n in range(180):
            party = n % 60
            lines = [{"day": f"2026-01-{1 + (n + i) % 28:02d}", "quantity": (n * 7 + i) % 97 + 1,
                      "code": "AB"[i % 2]} for i in range(1 + n % 3)]
            out.write(json.dumps({
                "document_id": f"D-{n:06d}", "filed": f"2026-02-{1 + n % 28:02d}",
                "party": {"party_id": f"P{party:07d}", "party_name": f"{WORDS[party % 10]} {WORDS[party // 10]} Trading",
                          "city": WORDS[(party * 3) % 10] + "ville", "postcode": f"{10000 + party * 37}"},
                "lines": {"line": lines if len(lines) > 1 else lines[0]},
                # Items that repeat exactly: only the parent and the place in the list tell them apart.
                "fees": [{"amount": 5 + n % 4, "due": "2026-03-01"}] * 2,
            }) + "\n")


@pytest.fixture(scope="module")
def findings(tmp_path_factory):
    base = tmp_path_factory.mktemp("embedded")
    _documents(base / "docs.jsonl")
    out = base / "out"
    assert profile_data.main(["run", "--name", "documents", "--input", f"doc={base / 'docs.jsonl'}",
                              "--out", str(out)]) == 0
    return yaml.safe_load((out / "findings.yaml").read_text()), (out / "REPORT.md").read_text()


def part(findings, name):
    return next(p for p in findings[0]["parts"] if p["part"] == name)


def test_the_dataset_keeps_its_name(findings):
    assert findings[0]["dataset"]["name"] == "documents"
    assert findings[1].startswith("# Profiling report: documents")


def test_an_entity_inside_a_part_is_its_own_master_part(findings):
    party = part(findings, "doc.party")
    assert party["derived_from"] == "doc" and party["rows"] == 60
    assert party["record_key"]["columns"] == ["party.party_id"] and party["record_key"]["found"]
    assert party["class"] == "master"
    links = {(r["from"]["part"], r["to"]["part"]) for r in findings[0]["relationships"]}
    assert ("doc", "doc.party") in links
    assert [i["location"] for i in findings[0]["dataset"]["inputs"]] and \
        all("party" not in i["location"] for i in findings[0]["dataset"]["inputs"])
    assert "an entity found inside doc" in findings[1]


def test_the_document_and_its_lines_are_transactions(findings):
    assert part(findings, "doc")["class"] == "transaction"
    lines = part(findings, "doc.lines.line")
    assert lines["rows"] == sum(1 + n % 3 for n in range(180))
    assert lines["record_key"]["found"] or lines["record_key"]["design"] == "natural_composite"
    assert lines["class"] == "transaction"


def test_a_nested_record_with_no_key_of_its_own_is_identified_by_its_parent_and_place(findings):
    fees = part(findings, "doc.fees")
    assert fees["record_key"] == {**fees["record_key"], "found": False, "design": "natural_composite",
                                  "columns": ["document_id", "_position"]}
    assert fees["class"] == "transaction"
