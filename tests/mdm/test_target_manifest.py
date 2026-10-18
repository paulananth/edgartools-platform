"""One writer builds a declared target's input manifest (ticket 14, slice 2): for
SEC Person it builds exactly what that source's own writer built."""
import json

import pytest

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
    assert set(json.loads((tmp_path / "bundle" / own["manifest"]["uri"].rsplit("/", 1)[1]).read_text())["steps"]) \
        == {"read", "records", "merge", "processed"}


def test_the_engine_sees_version_one_steps():
    steps = validate(files.source(SOURCE), "mastering")["steps"]

    assert all(set(step) == {"name", "operation", "requires", "key", "leases", "checks"} for step in steps)


@pytest.mark.parametrize("plan, words", [
    ({"units": {"slices": {"bytes": 0}}}, "units are one"),
    ({"units": {"groups": 17}}, "units are one"),
    ({"input": {"other": 1}}, "contract, keys and readings only"),
    ({"input": {"readings": {"read": {"all": "nothing"}}}}, "one prerequisite step"),
])
def test_a_plan_the_engine_cannot_run_is_refused(plan, words):
    body = files.source(SOURCE)
    body["bookkeeping"]["targets"]["mastering"]["steps"][1].update(plan)

    with pytest.raises(Blocked, match=words):
        validate(body, "mastering")


def test_a_version_one_section_is_not_a_plan(tmp_path):
    body = files.source(SOURCE)
    body["bookkeeping"]["version"] = 1
    for step in body["bookkeeping"]["targets"]["mastering"]["steps"]:
        step.pop("units", None), step.pop("input", None)

    validate(body, "mastering")  # version 1 still runs as it is
