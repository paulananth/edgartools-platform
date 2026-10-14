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


def test_a_field_null_in_every_list_item_keeps_the_single_items_values(tmp_path):
    # Most documents hold one signer written as an object, with a title; the few that hold a
    # list hold the title empty, so the list items alone read the title as an empty JSON column.
    with (tmp_path / "docs.jsonl").open("w") as out:
        for n in range(40):
            signer = {"signer_id": f"S{n:05d}", "title": ["Chair", "Treasurer", "Secretary"][n % 3]}
            signers = [{"signer_id": f"S{n:05d}", "title": None}, {"signer_id": f"T{n:05d}", "title": None}] if n % 10 == 0 else signer
            out.write(json.dumps({"document_id": f"D-{n:04d}", "signers": {"signer": signers}}) + "\n")
    out = tmp_path / "out"
    assert profile_data.main(["run", "--name", "docs", "--input", f"doc={tmp_path / 'docs.jsonl'}",
                              "--out", str(out)]) == 0
    found = yaml.safe_load((out / "findings.yaml").read_text())
    signers = next(p for p in found["parts"] if p["part"] == "doc.signers.signer")
    title = next(c for c in signers["columns"] if c["name"] == "title")
    assert title["fill"] == round(36 / 44, 6) and title["distinct"] == 3


def test_compare_keeps_an_approved_entity_that_repeats_less_in_the_new_delivery(findings, tmp_path):
    approved = tmp_path / "approved"
    approved.mkdir()
    _documents(tmp_path / "first.jsonl")
    assert profile_data.main(["run", "--name", "documents", "--input", f"doc={tmp_path / 'first.jsonl'}",
                              "--out", str(approved)]) == 0
    assert profile_data.main(["approve", "--findings", str(approved / "findings.yaml"), "--by", "test",
                              "--words", "approved"]) == 0
    # The new delivery names each party once: too few repeats for discovery to find it.
    with (tmp_path / "second.jsonl").open("w") as out:
        for n in range(60):
            out.write(json.dumps({
                "document_id": f"E-{n:06d}", "filed": f"2026-04-{1 + n % 28:02d}",
                "party": {"party_id": f"Q{n:07d}", "party_name": f"{WORDS[n % 10]} {WORDS[n // 10 % 10]} Supply",
                          "city": WORDS[n % 10] + "ville", "postcode": f"{20000 + n}"},
                "lines": {"line": {"day": "2026-04-01", "quantity": n + 1, "code": "A"}},
                "fees": [{"amount": 5, "due": "2026-05-01"}] * 2}) + "\n")
    drift_out = tmp_path / "drift"
    assert profile_data.main(["compare", "--approved", str(approved / "findings.yaml"),
                              "--input", f"doc={tmp_path / 'second.jsonl'}", "--out", str(drift_out)]) == 0
    items = yaml.safe_load((drift_out / "drift.yaml").read_text())["drift"]
    assert not [i for i in items if i["part"] == "doc.party" and i["drift"] in ("part_missing", "link_broken")]
    new = yaml.safe_load((drift_out / "findings.yaml").read_text())
    party = next(p for p in new["parts"] if p["part"] == "doc.party")
    assert party["rows"] == 60 and party["derived_evidence"]["repeats"] == 1.0


def test_free_text_samples_are_written_as_their_shape(tmp_path):
    with (tmp_path / "docs.jsonl").open("w") as out:
        for n in range(80):
            out.write(json.dumps({"document_id": f"D-{n:04d}", "remark": (
                f"{WORDS[n % 10]} cargo shipped through the quillfeather depot since {2000 + n}; the "
                f"{WORDS[n // 10]} carrier keeps custody {'except' if n % 2 else 'beyond'} the dock")}) + "\n")
    out = tmp_path / "out"
    assert profile_data.main(["run", "--name", "docs", "--input", f"doc={tmp_path / 'docs.jsonl'}",
                              "--out", str(out)]) == 0
    remark = next(c for c in yaml.safe_load((out / "findings.yaml").read_text())["parts"][0]["columns"]
                  if c["name"] == "remark")
    assert remark["distribution"] is None and remark["top"][0]["value"].startswith("Aaaa")
    assert remark["sensitivity"] == "none"  # free text that names no one: masked as free text, not as personal
    assert not [f for f in out.iterdir() if "quillfeather" in f.read_text()]


def test_a_short_text_that_names_people_is_personal(tmp_path):
    # Most holdings are held directly or by a firm; a few name a person's trust or estate.
    held = ["Directly", "By spouse", "By Harbor Stone Partners, LP", "Through a retirement plan"]
    with (tmp_path / "docs.jsonl").open("w") as out:
        for n in range(200):
            how = f"By the Orrin Q. Vantrell {n} Revocable Trust" if n % 20 == 0 else held[n % 4]
            out.write(json.dumps({"document_id": f"D-{n:04d}", "held": how}) + "\n")
    out = tmp_path / "out"
    assert profile_data.main(["run", "--name", "docs", "--input", f"doc={tmp_path / 'docs.jsonl'}",
                              "--out", str(out)]) == 0
    held_by = next(c for c in yaml.safe_load((out / "findings.yaml").read_text())["parts"][0]["columns"]
                   if c["name"] == "held")
    assert held_by["sensitivity"] == "personal" and "values: text naming people" in held_by["sensitivity_signals"]
    assert not [f for f in out.iterdir() if "Vantrell" in f.read_text()]


def test_text_naming_people_needs_their_capitals():
    from profiling import sensitivity
    things = ["Dr Pepper Snapple", "100 Oak Dr Suite 5", "Living Trust Services LLC", "held by the family",
              "MS Office licence", "Estate of mind"]
    assert not [v for v in things if sensitivity._MENTION.search(v)]
    people = ["By the Orrin Q. Vantrell Revocable Trust", "Mr. Vantrell and his spouse", "Vantrell Family Trust",
              "By estate of Orrin Vantrell"]
    assert all(sensitivity._MENTION.search(v) for v in people)


def test_approval_rewrites_the_report(findings, tmp_path):
    out = tmp_path / "approve"
    _documents(tmp_path / "docs.jsonl")
    assert profile_data.main(["run", "--name", "documents", "--input", f"doc={tmp_path / 'docs.jsonl'}",
                              "--out", str(out)]) == 0
    assert "Approval: **draft**" in (out / "REPORT.md").read_text()
    assert profile_data.main(["approve", "--findings", str(out / "findings.yaml"), "--by", "test", "--words", "yes"]) == 0
    assert "Approval: **approved**" in (out / "REPORT.md").read_text()


# ---------------------------------------------------------------- identifiers that name another entity

from profiling import embedded, identifiers, profile  # noqa: E402

duckdb = pytest.importorskip("duckdb")


def _issued_id(n: int) -> str:
    """An 8-character base and the digit that makes it pass Luhn over letter values."""
    base = f"{n:05d}{'ABC'[n % 3]}{n % 10}{'XYZ'[n % 3]}"
    return next(base + d for d in "0123456789" if identifiers.luhn_letter_values(base + d))


def _entities(rows: list[tuple], columns: str):
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({columns})")
    con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(rows[0]))})", rows)
    found, _ = embedded.find(con, "t", profile.columns(con, "t"), set())
    return con, found


def test_an_issued_identifier_names_its_entity_though_the_rows_write_its_name_differently():
    # 60 securities held 5 times each; each holder writes the name its own way; stand-ins for none.
    rows = [(f"H{i:06d}", _issued_id(i % 60), f"{WORDS[i % 60 % 10]} {WORDS[i % 60 // 10]} {['Inc', 'Corp', 'Co'][i // 60 % 3]}",
             float(i)) for i in range(300)]
    rows += [(f"H{900000 + i:06d}", stand_in, "Cash", 1.0) for i, stand_in in enumerate(["N/A", "000000000"] * 20)]
    con, found = _entities(rows, "holding VARCHAR, security VARCHAR, issuer_name VARCHAR, balance DOUBLE")
    (security,) = found
    assert security["column"] == "security" and security["evidence"]["issued"] == "luhn over letter values"
    assert security["follows"] == ["issuer_name"]
    disagree = embedded.register(con, security)
    assert con.execute('SELECT count(*) FROM "t.security"').fetchone()[0] == 60  # no stand-in is an entity
    assert disagree["issuer_name"] > 0  # the names written differently go to quality


def test_identifiers_that_determine_each_other_are_one_entity():
    # 60 registrants, each with a number and a file number, filing 3 times.
    rows = [(f"A{i:05d}", f"{1000000 + i % 60:010d}", f"8-{20000 + i % 60}X", f"{WORDS[i % 60 % 10]} {WORDS[i % 60 // 10]} Fund")
            for i in range(180)]
    _, found = _entities(rows, "accession VARCHAR, registrant VARCHAR, file_number VARCHAR, name VARCHAR")
    assert [e["column"] for e in found] == ["registrant"]
    assert set(found[0]["follows"]) >= {"file_number", "name"}


def test_an_identifier_that_repeats_on_few_rows_is_an_entity_when_its_name_follows_there():
    # 300 reports of 270 series: 30 series report twice, and each keeps its one name.
    series = [i if i < 270 else i - 270 for i in range(300)]
    rows = [(f"R{i:06d}", f"S{s:09d}", f"{WORDS[s % 10]} {WORDS[s // 10 % 10]} Series {s}") for i, s in enumerate(series)]
    _, found = _entities(rows, "report VARCHAR, series VARCHAR, series_name VARCHAR")
    assert [(e["column"], e["follows"]) for e in found] == [("series", ["series_name"])]
