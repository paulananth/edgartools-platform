"""The company facts' `silver` target (ticket 169): read the filers' files, land
them in `company_fact`, record each file in the Change Journal. Every name and
number here is invented."""
import hashlib
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.target_manifest import write_manifest
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.company-facts"
FACTS = {"cik": 42, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
    {"end": "2025-12-31", "val": 10, "accn": "0000000042-26-000001", "fy": 2025, "fp": "FY", "form": "10-K",
     "filed": "2026-02-01"}]}}}}}


def key(cik: int) -> str:
    return f"warehouse/bronze/company_facts/sec/cik={cik}/CIK{cik:010d}.json"


def capture(tmp_path, ciks):
    receipts = []
    for cik in ciks:
        raw = json.dumps({**FACTS, "cik": cik}).encode()
        path = tmp_path / "capture" / "bronze" / key(cik).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(cik), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in ciks]))
    return {"source": SOURCE, "target": "silver", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def test_the_silver_target_reads_lands_derives_and_records_each_file(tmp_path):
    report = write_manifest(**capture(tmp_path, [42, 43]))
    steps = Artifacts().json(report["manifest"])["steps"]

    assert {name: len(units) for name, units in steps.items()} == {
        "facts": 1, "land": 1, "line_items": 1, "measures": 1, "processed": 1}
    (read,) = steps["facts"]
    (land,) = steps["land"]
    assert land["keys"]["table"] == "company_fact" and land["keys"]["silver"] == "company_fact"
    assert land["input"] == {"from": {"step": "facts", "key": read["keys"]["unit"]}}
    assert land["output"].endswith(f"/land/{read['keys']['unit']}.json")
    for name in ("line_items", "measures"):  # each derived table is one unit, named by its build
        (derive,) = steps[name]
        assert derive["keys"]["build"] == name
        assert Artifacts().json(derive["input"]) == {"version": 1, "build": name, "silver": derive["keys"]["silver"],
                                                     "reads": derive["keys"]["reads"]}
    recorded = Artifacts().json(steps["processed"][0]["input"])["files"]
    assert [f["key"] for f in recorded] == [key(42), key(43)]


def test_a_file_already_recorded_under_the_same_rules_is_skipped_and_a_changed_one_is_named(tmp_path):
    from uuid import uuid4

    from edgar_warehouse.workers import journal_record

    options = capture(tmp_path, [42, 43])
    first = write_manifest(**options)
    body = Artifacts().json(Artifacts().json(first["manifest"])["steps"]["processed"][0]["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        options["journal"].append(value)
    again = write_manifest(**{**options, "output": str(tmp_path / "bundle2")})
    assert again["manifest"] is None  # every file recorded under these rules: no run
    forced = write_manifest(**{**options, "output": str(tmp_path / "bundle3"), "force": True})
    assert forced["scope"]["forced"] is True and forced["scope"]["documents"] == 2
    changed = capture(tmp_path / "next", [42, 43])  # the same files; then one file's bytes change
    (tmp_path / "next" / "capture" / "bronze" / key(43).removeprefix("warehouse/bronze/")).write_bytes(
        json.dumps({**FACTS, "cik": 43, "extra": 1}).encode())
    receipts = [json.loads(line) for line in (tmp_path / "next" / "capture" / "receipts.jsonl").read_text().splitlines()]
    raw = (tmp_path / "next" / "capture" / "bronze" / key(43).removeprefix("warehouse/bronze/")).read_bytes()
    for r in receipts:
        if r["key"] == key(43):
            r.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (tmp_path / "next" / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    after = write_manifest(**{**changed, "journal": options["journal"]})
    named = Artifacts().json(Artifacts().json(after["manifest"])["steps"]["processed"][0]["input"])["files"]
    assert [f["key"] for f in named] == [key(43)]


def test_changed_rules_name_every_file_again(tmp_path, monkeypatch):
    from uuid import uuid4

    from edgar_warehouse.mdm import changed_files
    from edgar_warehouse.workers import journal_record

    options = capture(tmp_path, [42, 43])
    first = write_manifest(**options)
    body = Artifacts().json(Artifacts().json(first["manifest"])["steps"]["processed"][0]["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        options["journal"].append(value)
    assert write_manifest(**{**options, "output": str(tmp_path / "same")})["manifest"] is None
    real = changed_files.source_rules
    monkeypatch.setattr(changed_files, "source_rules", lambda source: [real(source), "another rule"])
    after = write_manifest(**{**options, "output": str(tmp_path / "other")})
    named = Artifacts().json(Artifacts().json(after["manifest"])["steps"]["processed"][0]["input"])["files"]
    assert [f["key"] for f in named] == [key(42), key(43)]


def test_a_landing_that_names_no_table_is_refused():
    from edgar_warehouse.mdm import target_manifest as tm

    with pytest.raises(ValueError, match="table and silver"):
        tm.FORMS["silver.land"]({"name": "land", "requires": ["facts"], "input": {"keys": {"table": "company_fact"}}},
                                None, {"facts": []})


def test_a_derivation_that_names_no_build_is_refused():
    from edgar_warehouse.mdm import target_manifest as tm

    with pytest.raises(ValueError, match="build, silver"):
        tm.FORMS["silver.derive"]({"name": "line_items", "requires": ["land"], "input": {"keys": {"build": "x"}}}, None, {"land": []})


def _landing(requires):
    """`_land` over an invented target: a read step, a preparation, a merge and the landing."""
    from types import SimpleNamespace

    from edgar_warehouse.mdm import target_manifest

    by_name = {"read": {"operation": "source.read"}, "prepare": {"operation": "mdm.prepare"},
               "merge": {"operation": "mdm.merge"}, "land": {"operation": "silver.land"}}
    run = SimpleNamespace(by_name=by_name, root="run")
    step = {"name": "land", "requires": requires, "input": {"keys": {"table": "t", "silver": "s"}}}
    units = {"read": [{"keys": {"unit": "u1"}}, {"keys": {"unit": "u2"}}], "merge": [{"keys": {"batch_id": "b"}}]}
    return lambda: target_manifest._land(step, run, units)


def test_a_landing_may_wait_for_a_merge_and_still_takes_its_rows_from_the_read_step():
    made = _landing(["read", "merge"])()
    assert [u["input"] for u in made] == [{"from": {"step": "read", "key": "u1"}},
                                         {"from": {"step": "read", "key": "u2"}}]
    assert made == _landing(["read"])()  # the wait changes the order, not the units


@pytest.mark.parametrize("requires", [[], ["merge"], ["read", "read"], ["read", "prepare"]])
def test_a_landing_that_reads_no_step_or_two_or_waits_for_another_kind_is_refused(requires):
    with pytest.raises(ValueError, match="a landing follows one read step"):
        _landing(requires)()
