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


def _lines(path: Path, flip: bool = False) -> None:
    # 240 order lines, each naming one of 60 suppliers by an issued-looking id at the top level of the row,
    # with the supplier's name and city; a status that is "OK" on nearly every row (it follows any id by
    # coincidence); a per-row channel; two rows giving supplier 7 another name; and supplier 9's two names
    # tied (two rows each), in an order `flip` reverses.
    rows = ["line_id,supplier_id,supplier_name,supplier_city,status,channel,quantity"]
    for n in range(240):
        s = n % 60
        name = f"{WORDS[s % 10]} {WORDS[s // 10]} Supply"
        if s == 7 and n in (7, 67):
            name = "Renamed Supply"
        if s == 9:
            name = ("Tied One", "Tied Two")[(n // 60 + flip) % 2]
        rows.append(f"L{n:05d},S{s:06d},{name},{WORDS[(s * 3) % 10]}ville,{'HOLD' if n == 5 else 'OK'},"
                    f"{'web' if (n // 60) % 2 else 'store'},{n % 13 + 1}")
    path.write_text("\n".join(rows) + "\n")


def _run(base: Path, flip: bool = False) -> dict:
    base.mkdir(parents=True, exist_ok=True)
    _lines(base / "lines.csv", flip)
    assert profile_data.main(["run", "--name", "lines", "--input", f"lines={base / 'lines.csv'}",
                              "--out", str(base / "out")]) == 0
    return yaml.safe_load((base / "out" / "findings.yaml").read_text())


def test_a_top_level_identifier_carries_only_the_columns_that_follow_it(tmp_path):
    found = _run(tmp_path)
    supplier = next(p for p in found["parts"] if p["part"] == "lines.supplier_id")
    assert [c["name"] for c in supplier["columns"]] == ["supplier_id", "supplier_name", "supplier_city"]
    assert supplier["derived_evidence"]["values"] == 60 and supplier["derived_evidence"]["rows"] == 240
    assert set(supplier["derived_evidence"]["follows"]) == {"supplier_name", "supplier_city"}
    # 2 renamed rows, and supplier 9's two rows of the name not kept.
    assert supplier["derived_evidence"]["disagreeing_rows"] == {"supplier_name": 4, "supplier_city": 0}
    flagged = [q for q in supplier["quality"] if q["check"] == "carried_value_disagrees"]
    assert [(q["column"], q["rows"]) for q in flagged] == [("supplier_name", 4)]


def test_a_tie_keeps_the_same_value_whatever_the_row_order():
    import duckdb
    from profiling import embedded

    kept = []
    for order in ("ASC", "DESC"):
        con = duckdb.connect()
        con.execute("CREATE TABLE src AS SELECT * FROM (VALUES ('S1', 'Tied One'), ('S1', 'Tied Two'), "
                    "('S1', 'Tied Two'), ('S1', 'Tied One')) v(id, name)")
        con.execute(f"CREATE TABLE rows AS SELECT * FROM src ORDER BY name {order}")
        entity = {"part": "rows.id", "from": "rows", "column": "id", "follows": ["name"]}
        assert embedded.register(con, entity) == {"name": 2}
        kept.append(con.execute('SELECT name FROM "rows.id"').fetchone()[0])
    assert kept == ["Tied One", "Tied One"]
