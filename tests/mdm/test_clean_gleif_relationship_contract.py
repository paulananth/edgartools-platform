"""A GLEIF relationship record read by its contract alone (L6): the keys, ends,
period and refusals the older reader (`gleif_source.record_evidence`, retired after 68cc1240) built first.
Each case's outcome was compared with that reader on 2026-10-10: all equal."""

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import subject_key
from edgar_warehouse.mdm.clean.gleif_publication import dataset_contract

CHILD, PARENT = "HWUPKR0MPOU8FGXBT394", "5493001KJTIIGC8Y1R12"
PERIOD = {"StartDate": {"$": "2020-01-01T00:00:00Z"}, "PeriodType": {"$": "RELATIONSHIP_PERIOD"}}
ACCOUNTING = {"StartDate": {"$": "2019-01-01T00:00:00Z"}, "PeriodType": {"$": "ACCOUNTING_PERIOD"}}
PUBLICATION = {"publication_key": "p", "revision": 1, "artifact_sha256": "a" * 64, "member": "relationships",
               "effective_at": None}


def record(periods=(PERIOD,), status="ACTIVE", start_type="LEI", deletion=None, start=CHILD):
    found = {"RelationshipRecord": {
        "Relationship": {
            "StartNode": {"NodeID": {"$": start}, "NodeIDType": {"$": start_type}},
            "EndNode": {"NodeID": {"$": PARENT}, "NodeIDType": {"$": "LEI"}},
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipPeriods": {"RelationshipPeriod": list(periods) if isinstance(periods, tuple) else periods},
            "RelationshipStatus": {"$": status}},
        "Registration": {"LastUpdateDate": {"$": "2026-09-01T00:00:00Z"}, "RegistrationStatus": {"$": "PUBLISHED"}}}}
    if deletion is not None:
        found["RelationshipRecord"]["Extension"] = {"gleif:Deletion": deletion}
    return found


def read(row):
    return normalize(row, source_code="gleif.relationships.v1", contract=dataset_contract("relationships"),
                     publication=PUBLICATION)


def test_a_relationship_links_the_childs_record_to_the_parents_from_its_own_period():
    body = read(record((PERIOD, ACCOUNTING)))
    (link,) = body["relationships"]
    assert link["type"] == "IS_DIRECTLY_CONSOLIDATED_BY"
    assert link["source_subject"] == subject_key("gleif.level1.v1", CHILD)
    assert link["target_subject"] == subject_key("gleif.level1.v1", PARENT)
    assert (link["valid_from"], link["valid_to"]) == ("2020-01-01T00:00:00+00:00", None)
    assert link["properties"] == {"source_relationship_status": "ACTIVE", "source_registration_status": "PUBLISHED"}
    assert body["effective_at"] == "2026-09-01T00:00:00+00:00"
    assert body["provenance"]["source"]["native_record"] == record((PERIOD, ACCOUNTING))


def test_an_ended_relationship_and_a_time_with_an_offset_are_written_as_instants():
    ended = read(record(({**PERIOD, "EndDate": {"$": "2024-01-01T00:00:00Z"}},), status="INACTIVE"))
    assert ended["relationships"][0]["valid_to"] == "2024-01-01T00:00:00+00:00"
    offset = read(record(({"StartDate": {"$": "2020-01-01T05:00:00+05:00"}, "PeriodType": {"$": "RELATIONSHIP_PERIOD"}},)))
    assert offset["relationships"][0]["valid_from"] == "2020-01-01T00:00:00+00:00"


@pytest.mark.parametrize("row,reason", [
    (record((PERIOD, PERIOD)), "ambiguous_relationship_period"),
    (record((ACCOUNTING,)), "ambiguous_relationship_period"),
    (record(({**PERIOD, "EndDate": {"$": "2019-01-01T00:00:00Z"}},)), "invalid_relationship_interval"),
    (record(status="INACTIVE"), "invalid_relationship_status_interval"),
    (record(status="RETIRED"), "invalid_relationship_status_interval"),
    (record(start_type="FUND"), "unsupported_relationship_endpoint"),
    (record(deletion={"$": "x"}), "gleif_deletion_flag"),
    (record(start="BAD"), "invalid_lei"),
], ids=["two periods", "no relationship period", "end before start", "inactive without end", "other status",
        "endpoint not an LEI", "deletion flag", "bad LEI"])
def test_a_record_the_older_reader_set_aside_waits_with_the_same_reason(row, reason):
    with pytest.raises(UnsupportedRecord) as refused:
        read(row)
    assert refused.value.reason == reason


def test_an_empty_deletion_field_and_a_single_period_object_read_as_usual():
    assert read(record(deletion=None))["relationships"]
    assert read(record(PERIOD))["relationships"][0]["valid_from"] == "2020-01-01T00:00:00+00:00"


def test_a_null_deletion_field_and_a_bad_check_digit():
    row = record()
    row["RelationshipRecord"]["Extension"] = {"gleif:Deletion": None}
    assert read(row)["relationships"]
    with pytest.raises(UnsupportedRecord) as waiting:
        read(record(start="HWUPKR0MPOU8FGXBT395"))
    assert waiting.value.reason == "invalid_lei_checksum"


@pytest.mark.parametrize("extension,flagged", [
    (None, False), ({}, False), ({"gleif:Deletion": None}, False), ({"gleif:Deletion": {"$": "x"}}, True),
    ("unexpected", True), (7, True), ([], True),
], ids=["null", "empty object", "null flag", "flag", "text", "number", "list"])
def test_an_extension_that_is_not_an_object_is_read_as_the_flag(extension, flagged):
    # As the older reader did: an object holds the flag, anything else is it (operator, 2026-10-10).
    row = record()
    row["RelationshipRecord"]["Extension"] = extension
    if not flagged:
        assert read(row)["relationships"]
        return
    with pytest.raises(UnsupportedRecord) as refused:
        read(row)
    assert refused.value.reason == "gleif_deletion_flag"
