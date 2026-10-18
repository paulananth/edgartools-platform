"""One writer builds a declared target's input manifest (ticket 14, slice 2): for
SEC Person it builds exactly what that source's own writer built."""
import json

import pytest

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, validate
from edgar_warehouse.mdm.clean.capture_prepare import write_capture_manifest
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


def test_the_declared_writer_builds_what_the_sources_own_writer_built(tmp_path):
    own = write_capture_manifest(**options(tmp_path))
    declared = write_manifest(target="mastering", **options(tmp_path))

    assert declared == own
    assert set(Artifacts().json(own["manifest"])["steps"]) == {"read", "records", "merge", "processed"}


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


def test_both_writers_cut_the_same_read_units(tmp_path, monkeypatch):
    from edgar_warehouse.mdm.clean import capture_prepare

    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][0]["units"] = {"slices": {"bytes": 2000}}
    monkeypatch.setattr(capture_prepare, "READ_BYTES", 2000)
    own = write_capture_manifest(**options(tmp_path))
    monkeypatch.setattr(files, "source", lambda name, root=None: body)
    declared = write_manifest(target="mastering", **options(tmp_path))

    assert declared == own
    assert len(Artifacts().json(own["manifest"])["steps"]["read"]) > 1
