"""A `rules test` report recorded as a saved version's test run (ticket 14), on real PG16."""
import json
from uuid import uuid4

import pytest

from edgar_warehouse.rules import files, proving
from edgar_warehouse.rules.db import Rules
from edgar_warehouse.mdm.clean.store import digest
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401

PERSON = "sec.submissions.person"


def label():
    """A version label of its own: the tests share one Rules Database."""
    return f"v-{uuid4().hex[:8]}"


def report(document, passed=True):
    return {"test_run": f"{PERSON}, target mastering, on a local capture", "rules_digest": digest(document),
            "batch_hash": "a" * 64, "passed": passed, "passes": [{"records_in_mdm": 3}, {"records_in_mdm": 3}],
            "second_pass_changed_nothing": passed, "capture": {"capture_run": "c"}, "policy_digest": "b" * 64,
            "contract_digests": {"sec.submissions.person.v1": "c" * 64}}


@pytest.fixture
def operator_rules(databases, monkeypatch):
    engine = databases.rules.engine
    monkeypatch.setenv("RULES_DATABASE_URL", engine.url.render_as_string(hide_password=False))
    return Rules(engine)


def test_a_passing_run_proves_the_version_it_tested(operator_rules):
    version = label()
    document = files.source(PERSON)
    operator_rules.save("source", PERSON, version, document)

    rules = proving.recording(PERSON, version, document, sandbox="elsewhere")
    proving.record(rules, report(document), source=PERSON, version=version)

    row = operator_rules.version("source", PERSON, version)
    assert row["status"] == "proven" and row["proof"]["evidence"]["passes"][0] == {"records_in_mdm": 3}


def test_a_failing_run_stays_a_draft_with_its_evidence(operator_rules):
    version = label()
    document = files.source(PERSON)
    operator_rules.save("source", PERSON, version, document)

    proving.record(proving.recording(PERSON, version, document, sandbox="elsewhere"), report(document, passed=False),
                   source=PERSON, version=version)

    row = operator_rules.version("source", PERSON, version)
    assert row["status"] == "draft" and row["proof"]["passed"] is False


def test_a_version_that_is_not_the_rules_on_disk_is_refused_before_the_run(operator_rules):
    version = label()
    document = files.source(PERSON)
    operator_rules.save("source", PERSON, version, {**document, "note": "an earlier edit"})

    with pytest.raises(proving.TestRunError, match="not the rules on disk"):
        proving.recording(PERSON, version, document, sandbox="elsewhere")


def test_a_source_with_acquisition_is_recorded_with_its_capture_proof_instead(operator_rules):
    version = label()
    document = files.source("openfigi")
    operator_rules.save("source", "openfigi", version, document)

    with pytest.raises(proving.TestRunError, match="declares acquisition"):
        proving.recording("openfigi", version, document, sandbox="elsewhere")


def test_the_sandbox_and_an_unsaved_version_are_refused(operator_rules, monkeypatch):
    with pytest.raises(proving.TestRunError, match="no saved version"):
        proving.recording(PERSON, "v9", files.source(PERSON), sandbox="elsewhere")
    sandbox = json.loads(json.dumps(operator_rules.engine.url.render_as_string(hide_password=False)))
    with pytest.raises(proving.TestRunError, match="sandbox"):
        proving.recording(PERSON, label(), files.source(PERSON), sandbox=sandbox)
    monkeypatch.delenv("RULES_DATABASE_URL")
    with pytest.raises(proving.TestRunError, match="Set RULES_DATABASE_URL"):
        proving.recording(PERSON, label(), files.source(PERSON), sandbox="elsewhere")
