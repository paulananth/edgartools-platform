"""A run names only the files the Change Journal does not record as processed
under its rules and shared inputs (ticket 22; operator, 2026-10-13: "Rules +
shared inputs", "Change Journal events", "--all flag, recorded"). The events
are the `journal.record` worker's own, appended to a journal in memory."""

import json
from pathlib import Path
from uuid import uuid4

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.mdm.clean import changed_files
from edgar_warehouse.mdm.clean.capture_prepare import write_capture_manifest
from edgar_warehouse.workers import journal_record
from tests.mdm.test_clean_company_preparation import capture as company_capture  # noqa: F401
from tests.mdm.test_clean_company_preparation import census_capture, documents as company_documents, prepare
from tests.mdm.test_clean_company_preparation import CATALOG_ROWS
from tests.support.memory_journal import MemoryJournal
from tests.support.sec_capture import address, document, key, write_capture

SOURCE = "sec.submissions.person"
PEOPLE = {1001: document(1001, "DOE JOHN", entity_type="other"), 1002: document(1002, "ROE JANE", entity_type="other")}


def person(tmp_path, found, journal, *, name="b", force=False):
    folder, _ = write_capture(tmp_path / f"capture-{name}", found)
    listed = tmp_path / f"{name}.json"
    listed.write_text(json.dumps([key(cik) for cik in found]))
    return write_capture_manifest(source=SOURCE, capture=str(folder), documents=str(listed), capture_run="capture-1",
                                  output=str(tmp_path / name), as_of="2026-10-01T00:00:00Z", revision=0,
                                  force=force, journal=journal)


def record(report, journal):
    """What the run's last step appends once its merge is verified."""
    steps = Artifacts().json(report["manifest"])["steps"]
    (unit,) = steps["processed"]
    body = Artifacts().json(unit["input"])
    for value in journal_record._events({"claim": {"run_id": str(uuid4())}}, body):
        journal.append(value)
    return body


def named(report):
    steps = Artifacts().json(report["manifest"])["steps"]
    return [f["key"] for f in Artifacts().json(steps["processed"][0]["input"])["files"]]


def test_an_unchanged_repeat_names_no_file_and_starts_no_run(tmp_path):
    journal = MemoryJournal()
    first = person(tmp_path, PEOPLE, journal, name="first")
    assert named(first) == sorted(key(c) for c in PEOPLE) and first["scope"]["documents"] == 2
    record(first, journal)
    again = person(tmp_path, PEOPLE, journal, name="again")
    assert again["manifest"] is None and again["scope"] == {**first["scope"], "documents": 0,
                                                            "receipts_sha256": again["scope"]["receipts_sha256"]}


def test_one_changed_file_is_the_only_one_named(tmp_path):
    journal = MemoryJournal()
    record(person(tmp_path, PEOPLE, journal, name="first"), journal)
    changed = {**PEOPLE, 1002: document(1002, "ROE JANE Q", entity_type="other")}
    report = person(tmp_path, changed, journal, name="second")
    assert named(report) == [key(1002)] and report["scope"]["listed"] == 2


def test_forcing_names_every_file_and_says_so(tmp_path):
    journal = MemoryJournal()
    record(person(tmp_path, PEOPLE, journal, name="first"), journal)
    forced = person(tmp_path, PEOPLE, journal, name="forced", force=True)
    assert named(forced) == sorted(key(c) for c in PEOPLE) and forced["scope"]["forced"] is True
    body = Artifacts().json(Artifacts().json(forced["manifest"])["steps"]["processed"][0]["input"])
    events = journal_record._events({"claim": {"run_id": str(uuid4())}}, body)
    assert {e["scope"]["forced"] for e in events} == {"yes"}


def test_other_rules_or_another_shared_input_is_another_identity():
    reading = {"read": {"format": "json"}, "mdm": {}}
    base = changed_files.identity(reading, "p1", [{"name": "census", "sha256": "a" * 64}])
    assert base == changed_files.identity(reading, "p1", [{"name": "census", "sha256": "a" * 64}])
    assert base != changed_files.identity({**reading, "read": {"format": "xml"}}, "p1",
                                          [{"name": "census", "sha256": "a" * 64}])
    assert base != changed_files.identity(reading, "p2", [{"name": "census", "sha256": "a" * 64}])
    assert base != changed_files.identity(reading, "p1", [{"name": "census", "sha256": "b" * 64}])


def test_a_company_repeat_names_no_file_and_forcing_names_them_all(tmp_path, company_capture):  # noqa: F811
    journal = MemoryJournal()
    first, _ = prepare(tmp_path, company_capture, output="first", journal=journal)
    record(first, journal)
    again, _ = prepare(tmp_path, company_capture, output="again", journal=journal)
    assert again["manifest"] is None and again["scope"]["listed"] == 3
    forced, _ = prepare(tmp_path, company_capture, output="forced", journal=journal, force=True)
    assert len(named(forced)) == 3 and forced["scope"]["forced"] is True


def test_a_company_census_from_another_capture_names_every_file(tmp_path, company_capture):  # noqa: F811
    # The census is a shared input: a new one may change any Company's match.
    journal = MemoryJournal()
    record(prepare(tmp_path, company_capture, output="first", journal=journal)[0], journal)
    renamed = company_documents({42: document(42, "ACME GROUP PLC")})  # one name, so the census differs
    other = census_capture(tmp_path / "other", renamed, CATALOG_ROWS)
    assert Path(other[2]).read_bytes() != Path(company_capture[2]).read_bytes()
    report, _ = prepare(tmp_path, other, output="second", journal=journal)
    assert len(named(report)) == 3  # the two unchanged documents too


def test_a_new_capture_where_one_address_changed_names_only_that_company(tmp_path, company_capture):  # noqa: F811
    # Operator, 2026-10-13: "Only true content change is change". The new capture's census
    # names another capture, but its name counts are the same, so only the changed file is named.
    journal = MemoryJournal()
    record(prepare(tmp_path, company_capture, output="first", journal=journal)[0], journal)
    moved = company_documents({42: document(42, "ACME HOLDINGS PLC", business=address(
        street="2 KING ST", city="LONDON", state="X0", zip_code="EC2", country="UNITED KINGDOM", country_code="GB"))})
    other = census_capture(tmp_path / "other", moved, CATALOG_ROWS)
    old_census, new_census = (json.loads(Path(c[2]).read_text()) for c in (company_capture, other))
    assert old_census["sec"] != new_census["sec"] and old_census["entries"] == new_census["entries"]
    report, _ = prepare(tmp_path, other, output="second", journal=journal)
    assert named(report) == [key(42)] and report["scope"]["listed"] == 3
