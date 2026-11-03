"""The 13F Securities' `mastering` target (ticket 172): read the information
tables, reduce, combine, record, prepare, merge, and record each file in the
Change Journal. Every name and number here is invented."""
import hashlib
import json
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import changed_files
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
from edgar_warehouse.workers import journal_record
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.thirteenf.securities"
TABLE = ("<informationTable><infoTable><nameOfIssuer>EXAMPLE CORP</nameOfIssuer><titleOfClass>COM</titleOfClass>"
         "<cusip>ZZ0000906</cusip><value>1</value></infoTable></informationTable>")


def key(n: int) -> str:
    return f"warehouse/bronze/thirteenf_infotable/sec/accession=0000000042-26-00000{n}/infotable.xml"


def capture(tmp_path, numbers):
    receipts = []
    for n in numbers:
        raw = TABLE.encode()
        path = tmp_path / "capture" / "bronze" / key(n).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(n), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(n) for n in numbers]))
    return {"source": SOURCE, "target": "mastering", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def recorded(options, report):
    body = Artifacts().json(Artifacts().json(report["manifest"])["steps"]["processed"][0]["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        options["journal"].append(value)


def test_the_mastering_target_has_the_steps_that_prepare_and_merge_the_securities(tmp_path):
    report = write_manifest(**capture(tmp_path, [1, 2]))
    steps = Artifacts().json(report["manifest"])["steps"]
    assert set(steps) == {"read", "reduce", "combine", "record", "prepare", "merge", "land_holding", "processed"}
    assert [len(units) for units in steps.values()] == [1, 1, 1, 1, 1, 1, 1, 1]
    # Ticket 183: each information table lands its holdings in silver after the merge.
    assert steps["land_holding"][0]["keys"]["silver"] == "thirteenf_holding"
    assert steps["prepare"][0]["keys"]["table"] == "security"
    assert steps["prepare"][0]["keys"]["dataset"] == "sec.thirteenf.securities.v1"
    recorded_files = Artifacts().json(steps["processed"][0]["input"])["files"]
    assert [f["key"] for f in recorded_files] == [key(1), key(2)]


def test_a_second_pass_changes_nothing_and_changed_rules_name_every_file_again(tmp_path, monkeypatch):
    options = capture(tmp_path, [1, 2])
    recorded(options, write_manifest(**options))
    assert write_manifest(**{**options, "output": str(tmp_path / "again")})["manifest"] is None
    real = changed_files.source_rules
    monkeypatch.setattr(changed_files, "source_rules", lambda source: [real(source), "another rule"])
    after = write_manifest(**{**options, "output": str(tmp_path / "other")})
    named = Artifacts().json(Artifacts().json(after["manifest"])["steps"]["processed"][0]["input"])["files"]
    assert [f["key"] for f in named] == [key(1), key(2)]
