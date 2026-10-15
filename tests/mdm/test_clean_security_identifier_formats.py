"""The Security's identifier formats: CUSIP and ISIN, checked and normalized like CIK and LEI.

Operator, 2026-10-14: "CUSIP and ISIN join (Recommended)" for the Security master.
"""

import pytest

from edgar_warehouse.mdm.clean.adapters import FORMATS, UnsupportedRecord, format_value


@pytest.mark.parametrize("raw, kept", [
    ("594918104", "594918104"),     # digits only
    ("67066G104", "67066G104"),     # a letter in the issuer part
    (" 02079k305 ", "02079K305"),   # trimmed, upper-cased
])
def test_a_cusip_is_kept_upper_cased(raw, kept):
    assert format_value(raw, "cusip") == kept


@pytest.mark.parametrize("raw, reason", [
    ("594918105", "invalid_cusip_checksum"),  # the check digit is wrong
    ("037833900", "invalid_cusip_checksum"),  # an option's issue number on an equity's base: not recomputed
    ("59491810", "invalid_cusip"),            # eight characters
    ("N/A", "invalid_cusip"),
    ("000000000", "invalid_cusip"),           # a stand-in for none, though its check digit holds
    ("999999999", "invalid_cusip"),
])
def test_a_cusip_that_is_not_one_is_refused_with_its_reason(raw, reason):
    with pytest.raises(UnsupportedRecord) as refused:
        format_value(raw, "cusip")
    assert refused.value.reason == reason


@pytest.mark.parametrize("raw, kept", [
    ("US5949181045", "US5949181045"),
    ("us0378331005", "US0378331005"),
    ("GB0002634946", "GB0002634946"),
])
def test_an_isin_is_kept_upper_cased(raw, kept):
    assert format_value(raw, "isin") == kept


@pytest.mark.parametrize("raw, reason", [
    ("US5949181046", "invalid_isin_checksum"),
    ("5949181045", "invalid_isin"),     # no country prefix
    ("U15949181045", "invalid_isin"),   # the prefix is not two letters
    ("N/A", "invalid_isin"),
])
def test_an_isin_that_is_not_one_is_refused_with_its_reason(raw, reason):
    with pytest.raises(UnsupportedRecord) as refused:
        format_value(raw, "isin")
    assert refused.value.reason == reason


def test_a_us_isin_holds_its_cusip():
    # The two identifiers of one US security agree: the ISIN is the country, the CUSIP and a check digit.
    assert format_value("US5949181045", "isin")[2:11] == format_value("594918104", "cusip")


def test_both_formats_are_in_the_one_table():
    assert {"cusip", "isin"} <= set(FORMATS)
