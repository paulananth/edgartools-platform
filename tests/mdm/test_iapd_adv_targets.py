"""The Form ADV bulk file's two targets (ticket 176): `mastering` masters the adviser filings
with their custodians joined in, `custodians` masters one record per custodian; each ends in
the Change Journal. Every name and number here is invented."""
import hashlib
import json
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm import changed_files
from edgar_warehouse.mdm.target_manifest import write_manifest
from edgar_warehouse.workers import journal_record
from tests.support.memory_journal import MemoryJournal

SOURCE = "iapd.adv"
FACTS = {"published": "2026-09-30T00:00:00Z"}
STEPS = {"mastering": ["read_filings", "read_custody", "read_ciks", "combine", "record", "prepare", "merge", "land_custody", "processed"],
         "custodians": ["read", "combine", "record", "prepare", "merge", "processed"]}


def key(n: int) -> str:
    return f"warehouse/bronze/reference/iapd_adv_bulk/2026-0{n}/ADV_Filing_Data_20260{n}01_20260{n}30.zip"


def capture(tmp_path, target, numbers):
    receipts = []
    for n in numbers:
        raw = f"an invented archive {n}".encode()
        path = tmp_path / "capture" / "bronze" / key(n).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(n), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(n) for n in numbers]))
    return {"source": SOURCE, "target": target, "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal(), "facts": FACTS}


def recorded(options, report):
    body = Artifacts().json(Artifacts().json(report["manifest"])["steps"]["processed"][0]["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        options["journal"].append(value)


@pytest.mark.parametrize("target", STEPS)
def test_each_target_has_its_steps_and_ends_in_the_change_journal(tmp_path, target):
    steps = Artifacts().json(write_manifest(**capture(tmp_path, target, [8, 9]))["manifest"])["steps"]
    assert set(steps) == set(STEPS[target])
    assert len(steps["merge"]) == 1 and len(steps["prepare"]) == 1
    recorded_files = Artifacts().json(steps["processed"][0]["input"])["files"]
    assert [f["key"] for f in recorded_files] == [key(8), key(9)]


def test_the_filings_and_the_custodians_prepare_their_own_datasets(tmp_path):
    filings = Artifacts().json(write_manifest(**capture(tmp_path / "a", "mastering", [8]))["manifest"])["steps"]
    custodians = Artifacts().json(write_manifest(**capture(tmp_path / "b", "custodians", [8]))["manifest"])["steps"]
    assert (filings["prepare"][0]["keys"]["dataset"], filings["prepare"][0]["keys"]["table"]) == ("iapd.adv.filings.v2", "filings")
    assert (custodians["prepare"][0]["keys"]["dataset"], custodians["prepare"][0]["keys"]["table"]) == (
        "iapd.adv.custodians.v1", "custody")
    assert "distinct_on" not in filings["prepare"][0]["keys"]
    assert custodians["prepare"][0]["keys"]["distinct_on"] == ["custodian_id"]  # one record per custodian in a file


@pytest.mark.parametrize("target", STEPS)
def test_a_second_pass_changes_nothing_and_changed_rules_name_every_file_again(tmp_path, monkeypatch, target):
    options = capture(tmp_path, target, [8, 9])
    recorded(options, write_manifest(**options))
    assert write_manifest(**{**options, "output": str(tmp_path / "again")})["manifest"] is None
    real = changed_files.source_rules
    monkeypatch.setattr(changed_files, "source_rules", lambda source: [real(source), "another rule"])
    after = write_manifest(**{**options, "output": str(tmp_path / "other")})
    named = Artifacts().json(Artifacts().json(after["manifest"])["steps"]["processed"][0]["input"])["files"]
    assert [f["key"] for f in named] == [key(8), key(9)]


def test_recording_the_filings_does_not_skip_the_custodians_of_the_same_file(tmp_path):
    options = capture(tmp_path / "a", "mastering", [8])
    recorded(options, write_manifest(**options))
    custodians = {**capture(tmp_path / "b", "custodians", [8]), "journal": options["journal"]}
    assert write_manifest(**custodians)["manifest"] is not None  # each target keeps its own record of the file


def test_the_amount_each_custodian_holds_lands_in_silver_after_the_filings_merge(tmp_path):
    """Ticket 01: the custody rows are read once (read_custody) and landed in `adv_custody` once the adviser's
    filing is mastered; the journal records the file only after the landing."""
    steps = Artifacts().json(write_manifest(**capture(tmp_path, "mastering", [8, 9]))["manifest"])["steps"]
    assert len(steps["land_custody"]) == len(steps["read_custody"])  # each read unit lands its own rows
    assert {(u["keys"]["table"], u["keys"]["silver"]) for u in steps["land_custody"]} == {("custody_facts", "adv_custody")}
