"""A CUSIP failing its check digit is flagged and held back, and the Security is mastered by another identifier."""

import pytest

from edgar_warehouse.mdm import adapters
from edgar_warehouse.rules import files

SOURCE, CODE = "sec.nport.security", "sec.nport.security.v2"
GOOD, BAD = "037833100", "037833101"  # invented look-alikes: the second fails its check digit
PUBLICATION = {"publication_key": "invented", "revision": 1, "artifact_sha256": "a" * 64, "member": "invented",
               "record_locator": "1"}


def read(**row):
    base = {"key": row.get("cusip") or row.get("isin"), "name": "Example Corp", "title": "Common", "class": None,
            "classes": {"class_sample": []}, "key_class": "cusip", "cusip": None, "isin": None, "sedol": None,
            "loanx": None, "lei": None}
    return adapters.normalize({**base, **row}, source_code=CODE, contract=files.mdm_contract(SOURCE, CODE),
                              policy=files.policy(), publication=PUBLICATION)


def test_a_bad_cusip_is_set_aside_beside_the_record_and_flagged_and_the_isin_is_kept():
    record = read(cusip=BAD, isin="US0378331005")
    assert record["identifiers"] == {"isin": "US0378331005"}  # mastered by the ISIN
    assert record["provenance"]["identifiers_set_aside"] == [
        {"namespace": "cusip", "value": BAD, "reason": "invalid_cusip_checksum"}]
    quality = record["provenance"]["quality"]
    assert "cusip_check_digit" in str(quality)  # the data quality check flagged it


def test_a_good_cusip_is_kept_and_not_flagged():
    record = read(cusip=GOOD, isin="US0378331005")
    assert record["identifiers"]["cusip"] == GOOD
    assert "identifiers_set_aside" not in record["provenance"]
    assert "cusip_check_digit" not in str(record["provenance"].get("quality"))


def test_a_bad_cusip_with_no_other_identifier_is_still_set_aside_with_its_reason():
    with pytest.raises(adapters.UnsupportedRecord) as refused:
        read(cusip=BAD)
    assert refused.value.reason == "invalid_cusip_checksum"
