"""The ownership readings (`rules/sources/sec.ownership/`, profiling ticket 07).

A Form 3, 4 or 5 document is read the same way captured as bare XML (the
accession from the caller) and inside the SGML submission file (the accession
from its header). Dates are calendar dates; flags are XML Schema booleans and
any other spelling refuses the filing (operator, 2026-10-13); a transaction
code outside the SEC's list refuses it too. Every name and number here is
invented.
"""
import hashlib
import json

import pytest

from edgar_warehouse.rules import files
from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected
from tests.engine.test_sgml_container import document, submission

FOLDER = files.ROOT / "sources" / "sec.ownership"
XML, SGML = (files.load(FOLDER / f"ownership-{shape}.yaml") for shape in ("xml", "sgml"))
ACCESSION = "0000000000-26-000001"


def filing(*, date="2026-01-05", swap="0", code="P", director="1", coding=True, flag="0", root="ownershipDocument") -> bytes:
    coded = (f"<transactionCoding><transactionFormType>4</transactionFormType><transactionCode>{code}</transactionCode>"
             f"<equitySwapInvolved>{swap}</equitySwapInvolved></transactionCoding>") if coding else ""
    return f"""<?xml version="1.0"?>
<{root}>
 <schemaVersion>X0508</schemaVersion><documentType>4</documentType><periodOfReport>{date}</periodOfReport>
 <notSubjectToSection16>{flag}</notSubjectToSection16><aff10b5One>true</aff10b5One>
 <issuer><issuerCik>0000000001</issuerCik><issuerName>Example Widgets Inc</issuerName><issuerTradingSymbol>EXW</issuerTradingSymbol></issuer>
 <reportingOwner>
  <reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>Sample Holder</rptOwnerName></reportingOwnerId>
  <reportingOwnerRelationship><isDirector>{director}</isDirector></reportingOwnerRelationship>
 </reportingOwner>
 <nonDerivativeTable>
  <nonDerivativeTransaction>
   <securityTitle><value>Common Stock</value></securityTitle>
   <transactionDate><value>{date}</value></transactionDate>
   {coded}
   <transactionAmounts><transactionShares><value>100</value></transactionShares>
    <transactionPricePerShare><value>10.50</value></transactionPricePerShare>
    <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
   <postTransactionAmounts><sharesOwnedFollowingTransaction><value>1100</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
   <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
  </nonDerivativeTransaction>
 <nonDerivativeHolding>
   <securityTitle><value>Common Stock</value></securityTitle>
   <postTransactionAmounts><sharesOwnedFollowingTransaction><value>500</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
   <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature>
  </nonDerivativeHolding>
 </nonDerivativeTable>
 <footnotes><footnote id="F1">An invented footnote.</footnote></footnotes>
 <ownerSignature><signatureName>Sample Holder</signatureName><signatureDate>2026-01-06</signatureDate></ownerSignature>
</{root}>
""".encode()


def bare(body: bytes) -> dict:
    return SourceEngine(XML).read(body, context={"accession": ACCESSION}).tables


def wrapped(body: bytes) -> dict:
    sgml = submission(document(b"form4.xml", b"<XML>\n" + body + b"</XML>"), document(b"ex.txt", b"TEXT"),
                      header=f"ACCESSION NUMBER:\t{ACCESSION}\n".encode())
    return SourceEngine(SGML).read(sgml).tables


def test_both_shapes_declare_the_same_tables_and_references():
    for part in ("tables", "references", "reference_pins", "root", "limits"):
        assert XML["read"][part] == SGML["read"][part], part
    assert XML["read"]["context"]["accession"] == {"type": "text"}
    assert SGML["read"]["context"]["accession"] == {"type": "text", "sgml_header": "ACCESSION NUMBER"}


def test_both_shapes_read_the_same_rows():
    tables = bare(filing())
    assert tables == wrapped(filing())
    (row,) = tables["non_derivative_transaction"]
    assert (row["accession"], row["position"], row["transaction_date"], row["transaction_code"], row["equity_swap_involved"],
            row["transaction_shares"]) == (ACCESSION, 1, "2026-01-05", "P", False, "100")
    assert tables["reporting_owner"][0]["is_director"] is True
    assert tables["ownership_document"][0]["accession"] == ACCESSION
    assert tables["footnote"] == [{"accession": ACCESSION, "footnote_id": "F1", "text": "An invented footnote."}]


def test_a_date_with_an_offset_reads_as_its_calendar_date():
    tables = bare(filing(date="2026-01-05-05:00"))
    assert tables["ownership_document"][0]["period_of_report"] == "2026-01-05"
    assert tables["non_derivative_transaction"][0]["transaction_date"] == "2026-01-05"


@pytest.mark.parametrize("spelling, value", [("0", False), ("false", False), ("1", True), ("true", True)])
def test_the_four_boolean_spellings(spelling, value):
    assert bare(filing(swap=spelling))["non_derivative_transaction"][0]["equity_swap_involved"] is value


@pytest.mark.parametrize("changed", [{"swap": "N"}, {"director": "yes"}, {"code": "Q"}])
def test_a_fifth_spelling_or_an_unknown_code_refuses_the_filing(changed):
    with pytest.raises(SourceRejected) as refused:
        bare(filing(**changed))
    assert refused.value.code == "lookup_missing"


def test_an_absent_coding_reads_as_null():
    (row,) = bare(filing(coding=False))["non_derivative_transaction"]
    assert row["transaction_code"] is None and row["transaction_code_label"] is None
    assert row["equity_swap_involved"] is None


def test_the_codes_are_the_published_rdm_version_the_reading_pins():
    pin = XML["read"]["reference_pins"]["transaction_codes"]
    folder = files.ROOT / "reference" / "published" / pin["code_set"] / pin["version"]
    published = [json.loads(line) for line in (folder / "canonical.jsonl").read_text().splitlines()]
    assert json.loads((folder / "pin.json").read_text())["sha256"] == pin["sha256"]
    assert hashlib.sha256((folder / "canonical.jsonl").read_bytes()).hexdigest() == pin["sha256"]
    assert {row["code"]: row["label"] for row in published} == {
        code: row["label"] for code, row in XML["read"]["references"]["transaction_codes"].items()}


def test_the_filing_flags_and_a_holding_are_read():
    tables = bare(filing())
    document = tables["ownership_document"][0]
    assert (document["not_subject_to_section16"], document["aff10b5_one"], document["form3_holdings_reported"]) == (
        False, True, None)
    (holding,) = tables["non_derivative_holding"]
    assert (holding["position"], holding["shares_owned_following_transaction"],
            holding["direct_or_indirect_ownership"]) == (1, "500", "I")


def test_a_filing_flag_with_a_fifth_spelling_refuses():
    with pytest.raises(SourceRejected) as refused:
        bare(filing(flag="N"))
    assert refused.value.code == "lookup_missing"


def test_a_document_that_is_not_an_ownership_document_is_refused():
    with pytest.raises(SourceRejected) as refused:
        bare(filing(root="edgarSubmission"))
    assert refused.value.code == "wrong_root"
