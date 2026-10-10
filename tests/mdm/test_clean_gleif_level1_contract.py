"""A GLEIF Level 1 record read by its contract alone (L6): the fields, kinds,
addresses, corrections and successor links the older reader
(`gleif_source.record_evidence` and its tests, retired after 68cc1240) was
tested for, now through `adapters.normalize` with the configured contract."""

import copy

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, normalize
from edgar_warehouse.mdm.clean.evidence import subject_key
from edgar_warehouse.mdm.clean.gleif_publication import dataset_contract
from edgar_warehouse.mdm.clean.matching import _read

LEI = "HWUPKR0MPOU8FGXBT394"
PUBLICATION = {"publication_key": "p1", "revision": 1, "artifact_sha256": "a" * 64, "member": "level1",
               "effective_at": None}


def read(row, **kwargs):
    return normalize(row, source_code="gleif.level1.v1", contract=dataset_contract("level1"),
                     publication=PUBLICATION, **kwargs)


def record(category="GENERAL", **entity):
    return {"LEI": {"$": LEI}, "Entity": {"EntityCategory": {"$": category}, **entity},
            "Registration": {"LastUpdateDate": {"$": "2026-09-10T00:00:00Z"}, "RegistrationStatus": {"$": "LAPSED"}}}


def test_a_company_record_maps_its_fields_through_the_contract():
    row = record(LegalName={"$": "Example Inc."}, LegalJurisdiction={"$": "US-CA"}, LegalAddress={
        "FirstAddressLine": {"$": "One Main Street"},
        "AdditionalAddressLine": [{"$": "Building A"}, {"$": "Suite 700"}],
        "City": {"$": "Cupertino"}, "Region": {"$": "US-CA"}, "PostalCode": {"$": "95014"}, "Country": {"$": "US"}})
    body = read(row)
    assert body["fields"]["jurisdiction"]["value"] == "US-CA"
    assert body["fields"]["address"]["value"] == {
        "street": "One Main Street", "street2": "Building A\nSuite 700", "city": "Cupertino",
        "region": "US-CA", "postcode": "95014", "country": "US"}
    assert body["fields"]["gleif_registration_status"]["value"] == "LAPSED"
    assert body["fields"]["name"] == {"op": "value", "value": "Example Inc."}
    # The record's own time and the whole record, as the older reader kept them.
    assert body["effective_at"] == "2026-09-10T00:00:00+00:00"
    assert body["provenance"]["source"]["native_record"] == row


@pytest.mark.parametrize(("category", "probable"), [
    ("FUND", "fund_structure"),
    ("BRANCH", "branch"),
    ("RESIDENT_GOVERNMENT_ENTITY", "government"),
    ("INTERNATIONAL_ORGANIZATION", "international_organization"),
    ("SOLE_PROPRIETOR", None),
])
def test_a_waiting_record_carries_the_kind_its_category_names(category, probable):
    with pytest.raises(UnsupportedRecord) as waiting:
        read(record(category))
    assert waiting.value.reason == "unsupported_identity_kind"
    assert waiting.value.probable_kind == probable


def test_a_corrected_reading_of_one_publication_is_a_second_assertion():
    row = record(LegalName={"$": "Example Inc."})
    first, corrected = read(row), read(row, mapping_version=2)
    assert "mapping_version" not in first
    assert corrected["mapping_version"] == 2
    assert corrected["assertion_id"] != first["assertion_id"]
    assert corrected["subject"] == first["subject"]


def test_an_agent_legal_address_is_withheld_and_the_headquarters_address_is_kept():
    body = read(record(
        LegalName={"$": "Example Inc."},
        LegalAddress={"FirstAddressLine": {"$": "C/O The Corporation Trust Company"},
                      "AdditionalAddressLine": [{"$": "1209 Orange Street"}], "City": {"$": "Wilmington"},
                      "PostalCode": {"$": "19801"}, "Country": {"$": "US"}},
        HeadquartersAddress={"FirstAddressLine": {"$": "One Main Street"},
                             "AdditionalAddressLine": [{"$": "Suite 700"}], "City": {"$": "Cupertino"},
                             "PostalCode": {"$": "95014-2083"}, "Country": {"$": "US"}}))
    assert body["fields"]["address"]["value"]["street"] == "C/O The Corporation Trust Company"
    assert _read(body, "matching.address") is None
    assert _read(body, "matching.headquarters_address") == {
        "street": "ONE MAIN ST", "city": "CUPERTINO", "postcode": "95014", "country": "US"}
    assert body["provenance"]["matching"]["headquarters_postal_code"] == "95014-2083"


def test_a_bad_check_digit_waits_without_blocking():
    with pytest.raises(UnsupportedRecord) as waiting:
        read({**record(), "LEI": {"$": "HWUPKR0MPOU8FGXBT395"}})
    assert waiting.value.reason == "invalid_lei_checksum"
    for member in ("level1", "relationships", "reporting_exceptions"):
        reasons = dataset_contract(member)["nonblocking_deferred_reasons"]
        assert {"invalid_lei", "invalid_lei_checksum"} <= set(reasons), member
    assert "gleif_deletion_flag" not in dataset_contract("level1")["nonblocking_deferred_reasons"]


def _event(status, kind, effective, *affected):
    return {"@event_status": status, "LegalEntityEventType": {"$": kind},
            "LegalEntityEventEffectiveDate": {"$": effective},
            "AffectedFields": {"AffectedField": [
                {"@field_xpath": "/lei:LEIData/lei:LEIRecords/lei:LEIRecord/lei:Entity/lei:SuccessorEntity/lei:SuccessorLEI",
                 "$": lei} for lei in affected]}}


def test_each_successor_lei_is_a_link_dated_by_its_completed_event():
    first, second = "549300JB1P61FUTPEZ75", "5493001KJTIIGC8Y1R12"
    row = record(
        LegalName={"$": "Ceased a.s."}, EntityStatus={"$": "INACTIVE"},
        SuccessorEntity=[{"SuccessorLEI": {"$": first}},
                         {"SuccessorEntityName": {"@xml:lang": "sk", "$": "Named only, a.s."}},
                         {"SuccessorLEI": {"$": second}}],
        LegalEntityEvents={"LegalEntityEvent": [
            _event("WITHDRAWN_CANCELLED", "MERGERS_AND_ACQUISITIONS", "2021-06-01T00:00:00+01:00", first),
            _event("COMPLETED", "MERGERS_AND_ACQUISITIONS", "2022-01-01T00:00:00+01:00", first),
            _event("COMPLETED", "CHANGE_LEGAL_NAME", "2020-01-01T00:00:00+01:00"),
            # Not a succession type: it names the second successor, but dates nothing.
            _event("COMPLETED", "CHANGE_LEGAL_FORM", "2019-01-01T00:00:00+01:00", second)]})
    links = read(row)["relationships"]
    assert [(r["type"], r["target_subject"]) for r in links] == [
        ("SUCCESSOR_ENTITY", subject_key("gleif.level1.v1", lei)) for lei in (first, second)]
    assert links[0]["valid_from"] == "2022-01-01T00:00:00+01:00"
    assert links[0]["properties"] == {"source_event_type": "MERGERS_AND_ACQUISITIONS",
                                      "source_event_status": "COMPLETED", "source_entity_status": "INACTIVE"}
    assert links[1]["valid_from"] is None and links[1]["properties"] == {
        "source_event_type": None, "source_event_status": None, "source_entity_status": "INACTIVE"}
    alone = copy.deepcopy(row)
    alone["Entity"].pop("SuccessorEntity")
    assert read(alone)["relationships"] == []
