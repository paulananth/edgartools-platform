"""Tests for edgar_warehouse.parsers.ownership (Person Consumer Contract ticket 19).

The parser reads the Form 3/4/5 ownershipDocument XML directly and makes no
SEC request: reporting-owner classification evidence comes from a caller-
supplied bronze ``submissions.json`` lookup. These tests pin (a) the evidence
fields the Person contract needs, (b) that the output for the pre-existing
columns is unchanged from the edgartools-backed parser it replaces, and (c)
that no network is ever touched.
"""
from __future__ import annotations

import socket
from typing import Any

import pytest

from edgar_warehouse.parsers.ownership import (
    PARSER_VERSION,
    SNAPSHOT_SHA256_KEY,
    _is_company,
    _to_date_str,
    parse_ownership,
)

ACC = "0001234567-24-000001"


def _owner_xml(
    *,
    cik: str,
    name: str,
    street1: str = "1 MAIN ST",
    non_us: str | None = None,
    is_director: str = "0",
    is_officer: str = "0",
    is_ten_pct: str = "0",
    is_other: str = "0",
    officer_title: str | None = None,
    other_text: str | None = None,
) -> str:
    rel = [
        f"<isDirector>{is_director}</isDirector>",
        f"<isOfficer>{is_officer}</isOfficer>",
        f"<isTenPercentOwner>{is_ten_pct}</isTenPercentOwner>",
        f"<isOther>{is_other}</isOther>",
    ]
    if officer_title is not None:
        rel.append(f"<officerTitle>{officer_title}</officerTitle>")
    if other_text is not None:
        rel.append(f"<otherText>{other_text}</otherText>")
    addr = [
        f"<rptOwnerStreet1>{street1}</rptOwnerStreet1>",
        "<rptOwnerCity>CUPERTINO</rptOwnerCity>",
        "<rptOwnerState>CA</rptOwnerState>",
        "<rptOwnerZipCode>95014</rptOwnerZipCode>",
    ]
    if non_us is not None:
        addr.append(f"<rptOwnerNonUSAddressFlag>{non_us}</rptOwnerNonUSAddressFlag>")
    return (
        "<reportingOwner>"
        f"<reportingOwnerId><rptOwnerCik>{cik}</rptOwnerCik><rptOwnerName>{name}</rptOwnerName></reportingOwnerId>"
        f"<reportingOwnerAddress>{''.join(addr)}</reportingOwnerAddress>"
        f"<reportingOwnerRelationship>{''.join(rel)}</reportingOwnerRelationship>"
        "</reportingOwner>"
    )


def _nd_txn(
    *,
    security: str = "Common Stock",
    security_footnote: str | None = None,
    date: str = "2024-03-01",
    date_footnote: str | None = None,
    code: str = "S",
    shares: str = "1000",
    shares_footnote: str | None = None,
    price: str = "170.25",
    ad: str = "D",
    remaining: str = "50000",
    di: str = "D",
    nature: str | None = None,
) -> str:
    def v(tag: str, value: str, fn: str | None = None) -> str:
        inner = f"<value>{value}</value>" + (f'<footnoteId id="{fn}"/>' if fn else "")
        return f"<{tag}>{inner}</{tag}>"

    nature_xml = v("natureOfOwnership", nature) if nature else ""
    return (
        "<nonDerivativeTransaction>"
        + v("securityTitle", security, security_footnote)
        + v("transactionDate", date, date_footnote)
        + f"<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode><equitySwapInvolved>0</equitySwapInvolved></transactionCoding>"
        + "<transactionAmounts>"
        + v("transactionShares", shares, shares_footnote)
        + v("transactionPricePerShare", price)
        + v("transactionAcquiredDisposedCode", ad)
        + "</transactionAmounts>"
        + "<postTransactionAmounts>"
        + v("sharesOwnedFollowingTransaction", remaining)
        + "</postTransactionAmounts>"
        + "<ownershipNature>"
        + v("directOrIndirectOwnership", di)
        + nature_xml
        + "</ownershipNature>"
        + "</nonDerivativeTransaction>"
    )


def _d_txn(
    *,
    exercise_price: str = "50.00",
    exercise_price_footnote: str | None = None,
    exercise_date: str = "2025-01-15",
    exercise_date_footnote: str | None = None,
    expiration_date: str = "2030-01-15",
    expiration_footnote: str | None = None,
    underlying_shares: str = "2000",
    underlying_shares_footnote: str | None = None,
) -> str:
    def v(tag: str, value: str, fn: str | None = None) -> str:
        inner = f"<value>{value}</value>" + (f'<footnoteId id="{fn}"/>' if fn else "")
        return f"<{tag}>{inner}</{tag}>"

    return (
        "<derivativeTransaction>"
        + v("securityTitle", "Stock Option (Right to Buy)")
        + v("conversionOrExercisePrice", exercise_price, exercise_price_footnote)
        + v("transactionDate", "2024-03-01")
        + "<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>M</transactionCode><equitySwapInvolved>0</equitySwapInvolved></transactionCoding>"
        + "<transactionAmounts>"
        + v("transactionShares", "2000")
        + v("transactionPricePerShare", "0")
        + v("transactionAcquiredDisposedCode", "D")
        + "</transactionAmounts>"
        + v("exerciseDate", exercise_date, exercise_date_footnote)
        + v("expirationDate", expiration_date, expiration_footnote)
        + "<underlyingSecurity>"
        + v("underlyingSecurityTitle", "Common Stock")
        + v("underlyingSecurityShares", underlying_shares, underlying_shares_footnote)
        + "</underlyingSecurity>"
        + "<postTransactionAmounts>"
        + v("sharesOwnedFollowingTransaction", "0")
        + "</postTransactionAmounts>"
        + "<ownershipNature>"
        + v("directOrIndirectOwnership", "D")
        + "</ownershipNature>"
        + "</derivativeTransaction>"
    )


def _doc(
    *,
    owners: list[str],
    nd: list[str] = (),
    d: list[str] = (),
    footnotes: dict[str, str] | None = None,
    remarks: str | None = None,
    wrap_in_submission: bool = False,
) -> str:
    fn_xml = "".join(f'<footnote id="{k}">{v}</footnote>' for k, v in (footnotes or {}).items())
    doc = (
        '<?xml version="1.0"?><ownershipDocument><schemaVersion>X0508</schemaVersion>'
        "<documentType>4</documentType><periodOfReport>2024-03-01</periodOfReport>"
        "<issuer><issuerCik>0000320193</issuerCik><issuerName>Apple Inc.</issuerName><issuerTradingSymbol>AAPL</issuerTradingSymbol></issuer>"
        + "".join(owners)
        + (f"<nonDerivativeTable>{''.join(nd)}</nonDerivativeTable>" if nd else "")
        + (f"<derivativeTable>{''.join(d)}</derivativeTable>" if d else "")
        + (f"<footnotes>{fn_xml}</footnotes>" if fn_xml else "")
        + (f"<remarks>{remarks}</remarks>" if remarks is not None else "")
        + "<ownerSignature><signatureName>/s/ Somebody</signatureName><signatureDate>2024-03-03</signatureDate></ownerSignature>"
        "</ownershipDocument>"
    )
    if wrap_in_submission:
        return (
            "<SEC-DOCUMENT>0001234567-24-000001.txt : 20240303\n<SEC-HEADER>...\n</SEC-HEADER>\n"
            "<DOCUMENT>\n<TYPE>4\n<FILENAME>form4.xml\n<TEXT>\n<XML>\n" + doc + "\n</XML>\n</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>"
        )
    return doc


def _person_submissions(cik: int, name: str = "COOK TIMOTHY D") -> dict[str, Any]:
    return {
        "cik": str(cik), "name": name, "entityType": "other", "sic": "", "sicDescription": "",
        "ownerOrg": "", "ein": None, "stateOfIncorporation": "", "fiscalYearEnd": None,
        "tickers": [], "exchanges": [], "insiderTransactionForOwnerExists": 1,
        "insiderTransactionForIssuerExists": 0,
        "filings": {"recent": {"form": ["4", "4", "3"]}},
    }


def _company_submissions(cik: int, name: str = "SILVER LAKE GROUP, L.L.C.") -> dict[str, Any]:
    return {
        "cik": str(cik), "name": name, "entityType": "other", "sic": "6282", "sicDescription": "Investment Advice",
        "ownerOrg": "02 Finance", "ein": "123456789", "stateOfIncorporation": "DE", "fiscalYearEnd": "1231",
        "tickers": [], "exchanges": [], "insiderTransactionForOwnerExists": 1,
        "insiderTransactionForIssuerExists": 0,
        "filings": {"recent": {"form": ["4", "SC 13D", "13F-HR"]}},
    }


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Every test in this module fails if anything opens a socket."""

    def _refuse(*_a, **_k):
        raise AssertionError("parse_ownership must make zero network requests")

    monkeypatch.setattr(socket.socket, "connect", _refuse)


class TestOwnerEvidence:
    def test_other_text_and_document_footnotes_and_remarks_are_kept_per_owner(self):
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1", other_text="Director-by-Deputization")],
            footnotes={"F1": "Shares held by DST Global VI, L.P.", "F2": "Reporting person disclaims beneficial ownership."},
            remarks="Exhibit 24 - Power of Attorney",
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["other_text"] == "Director-by-Deputization"
        assert row["filing_footnote_text"] == (
            "[F1] Shares held by DST Global VI, L.P. | [F2] Reporting person disclaims beneficial ownership."
        )
        assert row["filing_remarks"] == "Exhibit 24 - Power of Attorney"

    def test_absent_text_fields_are_empty_strings_not_missing(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["other_text"] == ""
        assert row["filing_footnote_text"] == ""
        assert row["filing_remarks"] == ""

    def test_address_reduces_to_two_booleans_and_nothing_else(self):
        content = _doc(owners=[
            _owner_xml(cik="0001000001", name="DOE JANE", is_director="1", street1="C/O APPLE INC."),
            _owner_xml(cik="0001000002", name="ROE RICHARD", is_officer="1", street1="c/o Counsel", non_us="true"),
            _owner_xml(cik="0001000003", name="POE EDGAR", is_officer="1", street1="1 INFINITE LOOP", non_us="false"),
        ])
        rows = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"]
        assert [(r["address_is_care_of"], r["address_non_us"]) for r in rows] == [
            (True, False), (True, True), (False, False),
        ]
        forbidden = ("street", "city", "zip", "rptowner")
        for row in rows:
            for key in row:
                assert not any(word in key.lower() for word in forbidden), key
            assert "address_state" not in row and "address_country" not in row

    def test_owner_without_address_block_yields_false_false(self):
        content = _doc(owners=[
            ("<reportingOwner><reportingOwnerId><rptOwnerCik>0001000001</rptOwnerCik><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>"
            "<reportingOwnerRelationship><isDirector>1</isDirector></reportingOwnerRelationship></reportingOwner>")
        ])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert (row["address_is_care_of"], row["address_non_us"]) == (False, False)


class TestSubmissionsEvidence:
    def test_structural_fields_come_from_the_bronze_lookup(self):
        seen: list[int] = []

        def lookup(cik: int):
            seen.append(cik)
            return _company_submissions(cik)

        content = _doc(owners=[_owner_xml(cik="0001000002", name="SILVER LAKE GROUP, L.L.C.", is_ten_pct="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lookup)["sec_ownership_reporting_owner"][0]
        assert seen == [1000002]
        assert row["owner_submissions_present"] is True
        assert row["owner_entity_type"] == "other"
        assert row["owner_sic"] == "6282"
        assert row["owner_state_of_incorporation"] == "DE"
        assert row["owner_ein"] == "123456789"
        assert row["owner_ticker_count"] == 0
        assert row["owner_org"] == "02 Finance"
        assert row["owner_fiscal_year_end"] == "1231"

    def test_missing_snapshot_is_recorded_as_absent_with_empty_evidence(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["owner_submissions_present"] is False
        assert row["owner_entity_type"] == ""
        assert row["owner_sic"] == ""
        assert row["owner_state_of_incorporation"] == ""
        assert row["owner_ein"] == ""
        assert row["owner_ticker_count"] == 0
        assert row["owner_org"] == ""
        assert row["owner_fiscal_year_end"] == ""

    def test_null_json_values_become_empty_strings(self):
        payload = _person_submissions(1000001)
        assert payload["ein"] is None and payload["fiscalYearEnd"] is None
        content = _doc(owners=[_owner_xml(cik="0001000001", name="COOK TIMOTHY D", is_officer="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: payload)["sec_ownership_reporting_owner"][0]
        assert row["owner_ein"] == ""
        assert row["owner_fiscal_year_end"] == ""

    def test_no_lookup_supplied_means_no_snapshot(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        row = parse_ownership(ACC, content, "4")["sec_ownership_reporting_owner"][0]
        assert row["owner_submissions_present"] is False

    def test_lookup_is_called_once_per_distinct_cik(self):
        calls: list[int] = []

        def lookup(cik: int):
            calls.append(cik)

        content = _doc(owners=[
            _owner_xml(cik="0001000001", name="DOE JANE", is_director="1"),
            _owner_xml(cik="0001000001", name="DOE JANE", is_officer="1"),
        ])
        parse_ownership(ACC, content, "4", submissions_lookup=lookup)
        assert calls == [1000001]


class TestOwnerNameIsUnchangedFromTheEdgartoolsParser:
    """owner_name must come out exactly as before: reversed to 'First Last'
    for an individual, verbatim for a company, decided by edgartools' own
    classifier -- now fed from bronze instead of a live SEC fetch."""

    def test_individual_name_is_reversed(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="COOK TIMOTHY D", is_officer="1", officer_title="Chief Executive Officer")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: _person_submissions(cik))["sec_ownership_reporting_owner"][0]
        assert row["owner_name"] == "Timothy D Cook"
        assert row["owner_name_raw"] == "COOK TIMOTHY D"

    def test_company_name_is_verbatim(self):
        content = _doc(owners=[_owner_xml(cik="0001000002", name="SILVER LAKE GROUP, L.L.C.", is_ten_pct="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: _company_submissions(cik))["sec_ownership_reporting_owner"][0]
        assert row["owner_name"] == "SILVER LAKE GROUP, L.L.C."

    def test_no_snapshot_falls_back_to_the_individual_branch_like_edgartools_did(self):
        # edgartools' Entity(cik).data returned a placeholder ("Entity <cik>",
        # no signals) when the SEC lookup found nothing, which classifies as
        # an individual -> the name was reversed. Same result offline.
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["owner_name"] == "Jane Doe"

    def test_see_remarks_title_is_replaced_by_remarks(self):
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_officer="1", officer_title="See Remarks")],
            remarks="EVP, General Counsel",
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["officer_title"] == "EVP, General Counsel"


class TestPreExistingColumnsAreUnchanged:
    def test_owner_row_shape(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="COOK TIMOTHY D", is_officer="1", is_director="1", officer_title="CEO")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: _person_submissions(cik))["sec_ownership_reporting_owner"][0]
        assert row["accession_number"] == ACC
        assert row["owner_index"] == 1
        assert row["owner_cik"] == 1000001
        assert row["is_director"] is True
        assert row["is_officer"] is True
        assert row["is_ten_percent_owner"] is False
        assert row["is_other"] is False
        assert row["officer_title"] == "CEO"
        assert row["issuer_cik"] == 320193
        assert row["parser_version"] == PARSER_VERSION

    def test_non_derivative_row_shape_including_footnote_markers_on_string_fields(self):
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")],
            nd=[_nd_txn(security_footnote="F1", date_footnote="F2", shares_footnote="F3", nature="By Trust")],
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_non_derivative_txn"][0]
        assert row == {
            "accession_number": ACC,
            "owner_index": 1,
            "txn_index": 1,
            "security_title": "Common Stock [F1]",   # edgartools' value_with_footnotes format, kept
            "transaction_date": "2024-03-01",        # footnote marker stripped (date columns are typed DATE)
            "transaction_code": "S",
            "transaction_shares": 1000.0,
            "transaction_price": 170.25,
            "acquired_disposed_code": "D",
            "shares_owned_after": 50000.0,
            "ownership_direct_indirect": "D",
            "ownership_nature": "By Trust",
            "reporting_owner_count": 1,
            "parser_version": PARSER_VERSION,
        }

    def test_ownership_nature_is_empty_string_when_direct(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")], nd=[_nd_txn()])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_non_derivative_txn"][0]
        assert row["ownership_nature"] == ""

    def test_derivative_row_shape(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")], d=[_d_txn()])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_derivative_txn"][0]
        assert row["security_title"] == "Stock Option (Right to Buy)"
        assert row["conversion_or_exercise_price"] == 50.0
        assert row["exercise_date"] == "2025-01-15"
        assert row["expiration_date"] == "2030-01-15"
        assert row["underlying_security_title"] == "Common Stock"
        assert row["underlying_security_shares"] == 2000.0
        assert row["transaction_shares"] == 2000.0
        assert row["shares_owned_after"] == 0.0
        assert row["ownership_nature"] == ""

    def test_numeric_fields_with_footnotes_parse_the_value(self):
        # edgartools returned "50.00 [F1]" here and _to_float made it None;
        # the value is right there in the artifact, so keep it.
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")],
            d=[_d_txn(exercise_price_footnote="F1", underlying_shares_footnote="F2")],
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_derivative_txn"][0]
        assert row["conversion_or_exercise_price"] == 50.0
        assert row["underlying_security_shares"] == 2000.0

    def test_footnote_marked_dates_are_normalized(self):
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")],
            d=[_d_txn(exercise_date_footnote="F2", expiration_footnote="F3")],
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_derivative_txn"][0]
        for field in ("transaction_date", "exercise_date", "expiration_date"):
            assert "[" not in (row[field] or "")

    def test_full_sec_txt_submission_wrapper_is_accepted(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")], nd=[_nd_txn()], wrap_in_submission=True)
        parsed = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)
        assert len(parsed["sec_ownership_reporting_owner"]) == 1
        assert len(parsed["sec_ownership_non_derivative_txn"]) == 1

    def test_control_characters_do_not_abort_the_parse(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE\x0b", is_director="1")])
        parsed = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)
        assert parsed["sec_ownership_reporting_owner"][0]["owner_name"] == "Jane Doe"

    def test_non_ownership_document_yields_empty_tables(self):
        parsed = parse_ownership(ACC, "<html><body>not a form 4</body></html>", "4")
        assert parsed == {
            "sec_ownership_reporting_owner": [],
            "sec_ownership_non_derivative_txn": [],
            "sec_ownership_derivative_txn": [],
        }


class TestJointFilings:
    """A transaction belongs to the filing: the SEC schema gives it no owner
    reference. On a joint filing the parser therefore cannot attribute it to
    one reporting owner; it keeps owner_index = 1 (the landing key) and
    exposes what the artifact does say -- how many owners reported it and the
    free-text nature of ownership -- so a consumer can fail closed."""

    def test_single_owner_filing_attributes_transactions_to_that_owner(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")], nd=[_nd_txn(), _nd_txn(code="P")])
        parsed = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)
        assert [r["owner_index"] for r in parsed["sec_ownership_non_derivative_txn"]] == [1, 1]
        assert [r["reporting_owner_count"] for r in parsed["sec_ownership_non_derivative_txn"]] == [1, 1]

    def test_joint_filing_marks_every_transaction_with_the_owner_count(self):
        content = _doc(
            owners=[
                _owner_xml(cik="0001000002", name="DST GLOBAL VI, L.P.", is_ten_pct="1"),
                _owner_xml(cik="0001000003", name="DST INVESTMENTS XXI, L.P.", is_ten_pct="1"),
                _owner_xml(cik="0001000001", name="MILNER YURI", is_ten_pct="1"),
            ],
            nd=[_nd_txn(di="I", nature="By DST Global VI, L.P."), _nd_txn(di="I", nature="See footnote")],
            d=[_d_txn()],
        )
        parsed = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)
        assert [r["owner_index"] for r in parsed["sec_ownership_reporting_owner"]] == [1, 2, 3]
        nd = parsed["sec_ownership_non_derivative_txn"]
        assert [(r["owner_index"], r["txn_index"], r["reporting_owner_count"], r["ownership_nature"]) for r in nd] == [
            (1, 1, 3, "By DST Global VI, L.P."),
            (1, 2, 3, "See footnote"),
        ]
        assert parsed["sec_ownership_derivative_txn"][0]["reporting_owner_count"] == 3


class TestToDateStr:
    def test_strips_trailing_footnote_marker(self):
        assert _to_date_str("2021-02-04 [F2]") == "2021-02-04"

    def test_passes_through_clean_iso_date_unchanged(self):
        assert _to_date_str("2021-02-04") == "2021-02-04"

    def test_returns_none_for_none_empty_or_garbage(self):
        assert _to_date_str(None) is None
        assert _to_date_str("") is None
        assert _to_date_str("[F2]") is None
        assert _to_date_str("not a date") is None


class TestIsCompanyMatchesEdgartoolsSignals:
    """Each of edgartools 5.30.0's classifier signals, fed from a bronze
    payload -- the inputs most likely to drift on an edgartools bump."""

    @staticmethod
    def _base(**overrides: Any) -> dict[str, Any]:
        payload = {
            "name": "DOE JANE", "entityType": "other", "stateOfIncorporation": "", "ein": None,
            "tickers": [], "exchanges": [], "insiderTransactionForIssuerExists": 0,
            "insiderTransactionForOwnerExists": 1, "filings": {"recent": {"form": ["4"]}},
        }
        payload.update(overrides)
        return payload

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, False),
            ({"insiderTransactionForIssuerExists": 1}, True),
            ({"tickers": ["ACME"]}, True),
            ({"exchanges": ["Nasdaq"]}, True),
            ({"stateOfIncorporation": "DE"}, True),
            ({"entityType": "operating"}, True),
            ({"ein": "123456789"}, True),
            ({"ein": "000000000"}, False),
            ({"filings": {"recent": {"form": ["4", "10-K"]}}}, True),
            ({"name": "ACME HOLDINGS LLC"}, True),
        ],
    )
    def test_signal(self, overrides, expected):
        assert _is_company(1000001, self._base(**overrides)) is expected

    def test_company_form_beyond_the_first_fifty_is_ignored(self):
        forms = ["4"] * 50 + ["10-K"]
        assert _is_company(1000001, self._base(filings={"recent": {"form": forms}})) is False

    def test_no_payload_is_not_a_company(self):
        assert _is_company(1000001, None) is False


class TestProvenanceAndEdgeCases:
    def test_snapshot_sha256_is_recorded_on_the_owner_row(self):
        payload = {**_person_submissions(1000001), SNAPSHOT_SHA256_KEY: "ab" * 32}
        content = _doc(owners=[_owner_xml(cik="0001000001", name="COOK TIMOTHY D", is_officer="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: payload)["sec_ownership_reporting_owner"][0]
        assert row["owner_submissions_sha256"] == "ab" * 32
        assert SNAPSHOT_SHA256_KEY not in row

    def test_no_snapshot_leaves_the_sha256_empty(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["owner_submissions_sha256"] == ""

    def test_footnote_text_after_a_child_element_is_kept(self):
        content = _doc(owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")])
        content = content.replace(
            "<ownerSignature>",
            '<footnotes><footnote id="F1">Held by <b>trust</b> for children.</footnote></footnotes><ownerSignature>',
        )
        row = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_reporting_owner"][0]
        assert row["filing_footnote_text"] == "[F1] Held by trust for children."

    def test_transaction_missing_a_required_block_is_dropped_and_not_numbered(self):
        broken = _nd_txn(code="X").replace("<postTransactionAmounts>", "<ignored>").replace(
            "</postTransactionAmounts>", "</ignored>"
        )
        content = _doc(
            owners=[_owner_xml(cik="0001000001", name="DOE JANE", is_director="1")],
            nd=[_nd_txn(code="P"), broken, _nd_txn(code="S")],
        )
        rows = parse_ownership(ACC, content, "4", submissions_lookup=lambda cik: None)["sec_ownership_non_derivative_txn"]
        assert [(r["txn_index"], r["transaction_code"]) for r in rows] == [(1, "P"), (2, "S")]
