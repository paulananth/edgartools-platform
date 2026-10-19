"""One writer builds a declared target's input manifest (ticket 14, slice 2), from
the source's Bookkeeping section version 2."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
from edgar_warehouse.mdm.clean.target_manifest import write_manifest
from edgar_warehouse.rules import files
from tests.support.memory_journal import MemoryJournal
from tests.support.sec_capture import document, key, person, write_capture

SOURCE = "sec.submissions.person"
DOCUMENTS = {1001: person(1001, "DOE JOHN"), 1002: person(1002, "ROE JANE"),
             320193: document(320193, "EXAMPLE INC")}


def options(tmp_path, **changes):
    folder, _ = write_capture(tmp_path / "capture", DOCUMENTS)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in DOCUMENTS]))
    return {"source": SOURCE, "capture": str(folder), "documents": str(listed), "capture_run": "capture-1",
            "output": str(tmp_path / "bundle"), "as_of": "2026-10-18T00:00:00Z", "revision": 0,
            "journal": MemoryJournal(), **changes}


def captured(tmp_path):
    """Each document's reference in the capture, in key order."""
    return [(tmp_path / "capture" / "bronze" / key(cik).removeprefix("warehouse/bronze/")).as_uri()
            for cik in sorted(DOCUMENTS, key=key)]


def steps_of(report):
    return Artifacts().json(report["manifest"])["steps"]


def test_the_declared_writer_builds_persons_mastering_manifest(tmp_path):
    report = write_manifest(target="mastering", **options(tmp_path))
    steps = steps_of(report)

    assert {name: len(units) for name, units in steps.items()} == {"read": 1, "records": 1, "merge": 1, "processed": 1}
    read = Artifacts().json(steps["read"][0]["input"])
    assert [a["uri"] for a in read["artifacts"]] == captured(tmp_path)
    assert Artifacts().json(read["contract"]) == files.load(files.ROOT / "sources" / SOURCE / "source.yaml")
    records = steps["records"][0]
    assert {k: records["keys"][k] for k in ("table", "record_column", "dataset", "revision")} == {
        "table": "submissions", "record_column": "record", "dataset": "sec.submissions.person.v1", "revision": "0"}
    assert records["input"]["compose"]["slots"] == {"read": [{"step": "read", "key": "read-0"}]}
    assert steps["merge"][0]["input"] == {"from": {"step": "records", "key": "records"}}
    assert steps["merge"][0]["keys"] == {"batch_id": report["publication"]["batch_id"],
                                         "consumer": report["publication"]["consumer"]}
    assert len(Artifacts().json(steps["processed"][0]["input"])["files"]) == len(DOCUMENTS)


def test_the_engine_sees_version_one_steps():
    steps = validate(files.source(SOURCE), "mastering")["steps"]

    assert all(set(step) == {"name", "operation", "requires", "key", "leases", "checks"} for step in steps)


@pytest.mark.parametrize("plan, words", [
    ({"units": {"slices": {"bytes": 0}}}, "slices name their bytes"),
    ({"units": {"groups": 17}}, "groups hold 1..16"),
    ({"units": {"every": 2}}, "units are one"),
    ({"input": {"other": 1}}, "contract, keys and readings only"),
    ({"input": {"readings": {"read": {"all": "nothing"}}}}, "one prerequisite step"),
])
def test_a_plan_the_engine_cannot_run_is_refused(plan, words):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1].update(plan)

    with pytest.raises(Blocked, match=words):
        validate(body, "mastering")


def test_a_version_one_section_runs_but_states_no_plan(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["version"] = 1
    with pytest.raises(Blocked, match="A step requires name, operation"):
        validate(body, "mastering")  # version 1 holds no units or input
    for step in body["bookkeeping"]["targets"]["mastering"]["steps"]:
        step.pop("units", None), step.pop("input", None)
    assert len(validate(body, "mastering")["steps"]) == 4
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="must be version 2"):
        write_manifest(target="mastering", **options(tmp_path))


def test_units_on_a_step_that_reads_no_captured_documents_are_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1]["units"] = {"groups": 4}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="only a read of captured documents forms units"):
        write_manifest(target="mastering", **options(tmp_path))


def test_a_record_column_the_reading_does_not_declare_is_refused(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1]["input"]["keys"]["record_column"] = "other"
    monkeypatch.setattr(files, "source", lambda name, root=None: body)

    with pytest.raises(ValueError, match="not declared by the reading"):
        write_manifest(target="mastering", **options(tmp_path))


def test_the_declared_slices_cut_the_read_units(tmp_path, monkeypatch):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 2000}}
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    steps = steps_of(write_manifest(target="mastering", **options(tmp_path)))

    read = [[a["uri"] for a in Artifacts().json(unit["input"])["artifacts"]] for unit in steps["read"]]
    assert len(read) > 1 and sum(read, []) == captured(tmp_path)
    assert [u["keys"]["unit"] for u in steps["read"]] == [s["key"] for s in steps["records"][0]["input"]["compose"]["slots"]["read"]]


def test_a_source_whose_section_states_no_plan_is_refused(tmp_path):
    with pytest.raises(ValueError, match="must be version 2"):  # SEC Company keeps its own writer for now
        write_manifest(target="mastering", **options(tmp_path, source="sec.submissions.company"))


def test_an_edit_to_a_declared_contract_is_a_new_consumer(tmp_path, monkeypatch):
    first = write_manifest(target="mastering", **options(tmp_path / "a"))
    load = files.load

    def edited(path, *args, **kwargs):
        body = load(path, *args, **kwargs)
        return {**body, "note": "edited"} if path.name == "source.yaml" and SOURCE in str(path) else body
    monkeypatch.setattr(files, "load", edited)
    second = write_manifest(target="mastering", **options(tmp_path / "b"))

    assert second["publication"]["consumer"] != first["publication"]["consumer"]
    frozen = Artifacts().json(Artifacts().json(steps_of(second)["read"][0]["input"])["contract"])
    assert frozen["note"] == "edited"  # the ids digest the contract that is frozen
