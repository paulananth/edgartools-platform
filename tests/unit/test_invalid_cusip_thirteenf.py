"""A 13F CUSIP failing its check digit is flagged, and the holding is still a mastered Security keyed by the CUSIP as
filed (operator, 2026-11-10: "if a security is found in 13f or NPort we must have a mastered security")."""

import pytest

from edgar_warehouse.mdm import adapters
from edgar_warehouse.rules import files

SOURCE, CODE = "sec.thirteenf.securities", "sec.thirteenf.securities.v2"
GOOD, BAD = "037833100", "037833101"  # invented look-alikes: the second fails its check digit
PUBLICATION = {"publication_key": "invented", "revision": 1, "artifact_sha256": "a" * 64, "member": "invented",
               "record_locator": "1"}


def read(cusip):
    row = {"cusip": cusip, "name": {"name_sample": [{"issuer_name": "Example Corp"}]},
           "title": {"title_sample": [{"security_title": "COM"}]}, "class": None,
           "classes": {"class_sample": []}, "figi": None}
    return adapters.normalize(row, source_code=CODE, contract=files.mdm_contract(SOURCE, CODE), policy=files.policy(),
                              publication=PUBLICATION)


def test_a_good_cusip_is_kept_as_the_cusip_and_not_flagged():
    record = read(GOOD)
    assert record["identifiers"] == {"cusip": GOOD} and record["provenance"]["record_key"] == GOOD
    assert "identifiers_set_aside" not in record["provenance"]
    assert record["provenance"]["quality"]["checks"]["cusip_check_digit"]["rows_failed"] == 0
    assert "cusip_check_digit" not in record["provenance"]["quality"]["flags"]


def test_a_bad_cusip_is_kept_as_filed_and_flagged():
    record = read(BAD)
    assert record["identifiers"] == {"filed_cusip": BAD} and record["provenance"]["record_key"] == BAD
    assert record["provenance"]["identifiers_set_aside"] == [
        {"namespace": "cusip", "value": BAD, "reason": "invalid_cusip_checksum"}]
    assert "cusip_check_digit" in str(record["provenance"]["quality"])


def test_a_value_that_is_no_cusip_at_all_is_still_set_aside():
    with pytest.raises(adapters.UnsupportedRecord):
        read("111111111")  # one repeated character is a stand-in, never an identity
