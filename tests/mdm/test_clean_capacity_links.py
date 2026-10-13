"""A Dataset Contract states a link in a capacity (operator, 2026-10-13: "Yes,
generic change"): `capacity` names it, `on` dates the sighting, `held` reads the
flag, `title` the period's detail. The Merge Stage folds the sightings into
periods (test_clean_person_links). Every name and number here is invented."""

from __future__ import annotations

import pytest

from edgar_warehouse.mdm.clean.adapters import MappingError, normalize, subject_key
from edgar_warehouse.mdm.clean.relationships import fold_sightings
from tests.support.reading import reading

PUBLICATION = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "m"}
OFFICER = {"type": "EMPLOYED_BY", "capacity": "officer", "target_key": ["issuer"],
           "target_source": "fixture.companies", "on": "period", "held": "is_officer", "title": "title",
           "scope": "Fixture ownership", "time_format": "date"}


def read(row: dict, *links: dict) -> list[dict]:
    contract = {"schema_version": "1", "adapter": {
        "version": "fixture-v1", "kind": "person", "record_key": ["key"], "reading": reading(),
        "relationships": list(links or [OFFICER])}}
    return normalize({"key": "K", **row}, source_code="fixture.owners", contract=contract,
                     publication=PUBLICATION)["relationships"]


def test_a_capacity_link_is_a_dated_sighting():
    (link,) = read({"issuer": "1", "period": "2026-01-05", "is_officer": True, "title": "Chief Widget Officer"})
    assert link == {
        "type": "EMPLOYED_BY", "target_subject": subject_key("fixture.companies", "1"), "scope": "Fixture ownership",
        "valid_to": None, "properties": {}, "valid_from": "2026-01-05T00:00:00+00:00", "capacity": "officer",
        "on": "2026-01-05T00:00:00+00:00", "held": True, "title": "Chief Widget Officer"}


@pytest.mark.parametrize("flag", [False, None])
def test_a_flag_that_is_not_true_is_a_drop(flag):
    (link,) = read({"issuer": "1", "period": "2026-01-05", "is_officer": flag})
    assert link["held"] is False and link["title"] is None


def test_the_sightings_fold_into_a_period_the_drop_ends():
    sightings = [{**link, "basis": "observed", "assertion_id": n, "subject": n}
                 for n, link in enumerate(
                     read({"issuer": "1", "period": p, "is_officer": held})[0]
                     for p, held in (("2026-01-05", True), ("2026-03-01", True), ("2026-06-01", False)))]
    periods, _ = fold_sightings(sightings)
    assert [(p["valid_from"][:10], p["valid_to"][:10]) for p in periods] == [("2026-01-05", "2026-06-01")]


def test_a_link_without_a_capacity_reads_as_before():
    link = {"type": "SUCCEEDS", "target_key": ["issuer"], "target_source": "fixture.companies",
            "valid_from": "period"}
    (found,) = read({"issuer": "1", "period": "2026-01-05"}, link)
    assert found["valid_from"] == "2026-01-05" and "capacity" not in found


def test_a_capacity_link_without_its_date_stops_the_run():
    link = {k: v for k, v in OFFICER.items() if k != "on"}
    with pytest.raises(MappingError):
        read({"issuer": "1", "period": "2026-01-05", "is_officer": True}, link)


def test_a_flag_that_is_not_a_boolean_sets_the_record_aside():
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

    with pytest.raises(UnsupportedRecord, match="invalid_field_shape"):
        read({"issuer": "1", "period": "2026-01-05", "is_officer": "1"})


@pytest.mark.parametrize("given", ["20260105", "2026-W01-1", "2026-01-05T10:00:00+00:00", "2026-02-30", 20260105])
def test_a_date_that_is_not_a_calendar_date_sets_the_record_aside(given):
    from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord

    with pytest.raises(UnsupportedRecord, match="invalid_time"):
        read({"issuer": "1", "period": given, "is_officer": True})
