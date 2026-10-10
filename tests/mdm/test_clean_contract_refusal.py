"""A contract's own record checks set a record aside, with their reason, before
anything else of the record is read (L6: GLEIF refusals move into the contract,
operator ruling 2026-10-10)."""

import copy

import pytest

from edgar_warehouse.mdm.clean.adapters import UnsupportedRecord, mapped_values, normalize
from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceRejected
from edgar_warehouse.workers.source_mapping import record_refusal

DELETION = {"check": "absent", "path": "Extension.gleif:Deletion", "reason": "gleif_deletion_flag",
            "on_fail": "defer"}
PUBLICATION = {"artifact_sha256": "a" * 64, "member": "level1", "publication_key": "fixture", "revision": 1,
               "effective_at": None}


def contract(*checks):
    body = copy.deepcopy(files.source("gleif")["mdm"]["gleif.level1.v1"]["contract"])
    body["adapter"]["reading"]["read"]["tables"]["mapped"]["checks"] = list(checks)
    return body


def record(category="GENERAL", **extra):
    return {"LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
            "Entity": {"EntityCategory": {"$": category}, "LegalName": {"$": "Example Inc."}}, **extra}


def test_a_check_names_its_reason_and_a_passing_record_has_none():
    reading = contract(DELETION)["adapter"]["reading"]
    assert record_refusal(record(Extension={"gleif:Deletion": {"$": "x"}}), reading) == "gleif_deletion_flag"
    assert record_refusal(record(), reading) is None
    assert record_refusal(record(Extension={"gleif:Deletion": None}), reading) is None  # empty in a full file


def test_a_reading_without_checks_refuses_nothing():
    reading = copy.deepcopy(files.source("gleif")["mdm"]["gleif.level1.v1"]["contract"]["adapter"]["reading"])
    reading["read"]["tables"]["mapped"].pop("checks")
    assert record_refusal(record(Extension={"gleif:Deletion": {"$": "x"}}), reading) is None


def test_the_refusal_comes_before_the_kind():
    # A FUND would defer as unsupported_identity_kind; the contract's check speaks first.
    with pytest.raises(UnsupportedRecord) as refused:
        normalize(record("FUND", Extension={"gleif:Deletion": {"$": "x"}}), source_code="gleif.level1.v1",
                  contract=contract(DELETION), publication=PUBLICATION)
    assert refused.value.reason == "gleif_deletion_flag"
    with pytest.raises(UnsupportedRecord) as kind:
        normalize(record("FUND"), source_code="gleif.level1.v1", contract=contract(DELETION),
                  publication=PUBLICATION)
    assert kind.value.reason == "unsupported_identity_kind"


def test_mapped_values_refuses_the_same_record():
    with pytest.raises(UnsupportedRecord, match="gleif_deletion_flag"):
        mapped_values(record(Extension={"gleif:Deletion": {"$": "x"}}), contract(DELETION))


def test_a_reading_of_several_tables_is_a_contract_error():
    reading = copy.deepcopy(contract(DELETION)["adapter"]["reading"])
    reading["read"]["tables"]["other"] = reading["read"]["tables"]["mapped"]
    with pytest.raises(SourceRejected):
        record_refusal(record(), reading)


@pytest.mark.parametrize("member,row", [
    ("level1", lambda e: {**record(), "Extension": e}),
    ("reporting_exceptions", lambda e: {"LEI": {"$": "HWUPKR0MPOU8FGXBT394"},
                                        "ExceptionCategory": {"$": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT"},
                                        "ExceptionReason": [{"$": "NON_CONSOLIDATING"}], "Extension": e}),
])
@pytest.mark.parametrize("extension,flagged", [
    (None, False), ({}, False), ({"gleif:Deletion": None}, False), ({"gleif:Deletion": {"$": "x"}}, True),
    ("unexpected", True), (7, True), ([], True),
], ids=["null", "empty object", "null flag", "flag", "text", "number", "list"])
def test_an_extension_that_is_not_an_object_is_read_as_the_flag(member, row, extension, flagged):
    # As the older reader did: an object holds the flag, anything else is it (operator, 2026-10-10).
    reading = files.source("gleif")["mdm"][f"gleif.{member}.v1"]["contract"]["adapter"]["reading"]
    assert (record_refusal(row(extension), reading) == "gleif_deletion_flag") is flagged
