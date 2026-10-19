"""`rules test` on real Docker PG16 (ticket 14): a source's `mastering` target, run
twice on the disposable local stores, each step's worker and verifier as their own
process and login. Invented people are mastered by their CIK, a company-shaped name
is held back, and the second pass changes nothing."""
import json
from uuid import uuid4

import pytest

from edgar_warehouse.rules import proving
from tests.support.sec_capture import document, key, person, write_capture
from tests.unit.test_local_test_stores import local

DOCUMENTS = {1001: person(1001, "DOE JOHN"), 1002: person(1002, "ROE JANE"), 1003: person(1003, "POE ANN"),
             1004: document(1004, "EXAMPLE HOLDINGS INC", entity_type="other")}


@pytest.fixture
def stores(tmp_path):
    found = local.LocalStores(tmp_path / "stores", tmp_path / "worktree")
    name = "rules-proving-" + uuid4().hex[:10]
    try:
        with found.locked(name):
            found.start(name)
        yield found.folder(name)
    finally:
        if (found.folder(name) / "identity.json").exists():
            container, volume = found.owned(name, found.identity(name))
            if found.resource("container", container):
                found.docker("rm", "-f", container)
            if found.resource("volume", volume):
                found.docker("volume", "rm", volume)


def run(tmp_path, stores, **changes):
    capture, _ = write_capture(tmp_path / "capture", DOCUMENTS)
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in DOCUMENTS]))
    options = dict(source="sec.submissions.person", capture=capture, documents=listed, capture_run="rules-test-1",
                   as_of="2026-10-18T00:00:00Z", stores=stores, out=tmp_path / "report.json", minutes=10)
    return proving.run(**{**options, **changes})


def test_people_are_mastered_and_a_second_pass_changes_nothing(tmp_path, stores):
    report = run(tmp_path, stores)

    assert report["passed"] and report["second_pass_changed_nothing"]
    first = report["passes"][0]
    assert first["mdm"]["masters"] == {"person": 3}
    assert first["mdm"]["decisions"] == {"bind": 3}
    assert first["mdm"]["set_aside"] == {"classification_entity_undetermined": 1}
    assert first["records_in_mdm"] == len(DOCUMENTS)
    assert not first["mdm"]["identifiers_on_two_masters"]
    # The second pass named every document again and did the same work.
    assert report["passes"][1]["run_counts"] == first["run_counts"] and first["run_counts"]
    assert json.loads((tmp_path / "report.json").read_text()) == report
    # What the quality rule did, counted from the prepared records, and each contract's digest.
    assert isinstance(first["quality"], dict) and report["passes"][1]["quality"] == first["quality"]
    assert set(report["contract_digests"]) == {"sec.submissions.person.v1"}
    assert report["batch_hash"] == first["manifest_sha256"]


def test_a_store_that_already_holds_records_is_refused(tmp_path, stores):
    run(tmp_path, stores)

    with pytest.raises(proving.TestRunError, match="already holds records"):
        run(tmp_path, stores, out=tmp_path / "again.json")


def test_a_source_whose_section_states_no_plan_stops_the_test(tmp_path, stores):
    with pytest.raises(proving.TestRunError, match="must be version 2"):
        run(tmp_path, stores, source="sec.submissions.company")
