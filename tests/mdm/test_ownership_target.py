"""The insider ownership filings' `mastering` target (ticket 176): read the SEC
submission files, prepare and merge the reporting owners, land the owners and the
lines in silver once the merge is done, and record each file in the Change
Journal. Every name and number here is invented."""
import hashlib
import json
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import changed_files
from edgar_warehouse.mdm.target_manifest import write_manifest
from edgar_warehouse.workers import journal_record
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.ownership"
LANDS = {"land_owner": ("reporting_owner", "insider_reporting_owner"),
         "land_nd_transaction": ("non_derivative_transaction", "insider_position"),
         "land_nd_holding": ("non_derivative_holding", "insider_position"),
         "land_d_transaction": ("derivative_transaction", "insider_position"),
         "land_d_holding": ("derivative_holding", "insider_position")}


def key(n: int) -> str:
    return f"warehouse/bronze/filing_artifact/sec/accession=0000000042-26-00000{n}/0000000042-26-00000{n}.txt"


def capture(tmp_path, numbers):
    receipts = []
    for n in numbers:
        raw = f"an invented submission {n}".encode()
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


def test_the_target_masters_the_owners_then_lands_the_owners_and_lines_in_silver(tmp_path):
    report = write_manifest(**capture(tmp_path, [1, 2]))
    steps = Artifacts().json(report["manifest"])["steps"]
    assert set(steps) == {"read", "prepare", "merge", "processed", *LANDS}
    assert all(len(units) == 1 for units in steps.values())  # two small files share one read unit
    (read,) = steps["read"]
    assert steps["prepare"][0]["keys"]["table"] == "owner_record"
    assert steps["prepare"][0]["keys"]["dataset"] == "sec.ownership.reporting_owner.v1"
    for name, (table, silver) in LANDS.items():  # each lands the read step's unit, once the merge is done
        (land,) = steps[name]
        assert (land["keys"]["table"], land["keys"]["silver"]) == (table, silver)
        assert land["input"] == {"from": {"step": "read", "key": read["keys"]["unit"]}}
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


def test_the_security_symbols_target_reads_the_symbol_then_prepares_and_merges_it(tmp_path):
    """Ticket 24: a second target, since a target prepares one publication. It lands nothing in
    silver and reads only the issuer and symbol of each filing."""
    report = write_manifest(**{**capture(tmp_path, [1, 2]), "target": "security_symbols"})
    steps = Artifacts().json(report["manifest"])["steps"]
    assert set(steps) == {"read_security", "prepare_security", "merge_security", "processed_security"}
    (read,) = steps["read_security"]
    assert steps["prepare_security"][0]["keys"]["table"] == "security_record"
    assert steps["prepare_security"][0]["keys"]["dataset"] == "sec.ownership.security.v1"
    recorded_files = Artifacts().json(steps["processed_security"][0]["input"])["files"]
    assert [f["key"] for f in recorded_files] == [key(1), key(2)]
    assert read["keys"]["unit"]
