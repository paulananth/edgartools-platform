from datetime import date

import pytest

from edgar_warehouse.application.auditor_evidence import (
    parse_auditor_evidence,
    parse_pcaob_firm_registry,
)
from edgar_warehouse.application.errors import WarehouseRuntimeError


def test_parse_complete_direct_ixbrl_triplet_for_audited_period():
    html = """
    <html><body>
      <xbrli:context id="D2024"><xbrli:period><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
      <h2>Report of Independent Registered Public Accounting Firm</h2>
      <dei:AuditorName contextRef="D2024">Ernst &amp; Young LLP</dei:AuditorName>
      <dei:AuditorFirmId contextRef="D2024">00042</dei:AuditorFirmId>
      <dei:AuditorLocation contextRef="D2024">San Jose, California</dei:AuditorLocation>
      <p>October 25, 2024</p>
    </body></html>
    """
    result = parse_auditor_evidence(
        accession_number="0000320193-24-000123", registrant_cik=320193,
        form_type="10-K", document_name="aapl-20240928.htm", content=html,
        audited_period_end=date(2024, 9, 28), filing_date=date(2024, 11, 1),
        source_sha256="abc123",
    )
    assert result.outcome == "applicable_loaded"
    assert result.row is not None
    assert result.row.pcaob_firm_id == "42"
    assert result.row.evidence_source == "sec_ixbrl"
    assert result.row.report_date == date(2024, 10, 25)
    assert result.row.raw_locator == "context:D2024"


def test_incomplete_ixbrl_triplet_fails_closed():
    html = """
    <dei:AuditorName contextRef="D2024">Example LLP</dei:AuditorName>
    <dei:AuditorFirmId contextRef="D2024">123</dei:AuditorFirmId>
    """
    with pytest.raises(WarehouseRuntimeError, match="incomplete auditor triplet"):
        parse_auditor_evidence(
            accession_number="a", registrant_cik=1, form_type="10-K",
            document_name="a.htm", content=html,
            audited_period_end=date(2024, 12, 31), filing_date=date(2025, 2, 1),
            source_sha256="hash",
        )


def test_bounded_independent_auditor_report_signature_fallback():
    text = """
    REPORT OF INDEPENDENT REGISTERED PUBLIC ACCOUNTING FIRM
    We have audited the accompanying financial statements.
    PCAOB Firm ID: 1042
    /s/ Long Tail CPAs
    Boise, Idaho
    February 14, 2025
    """
    result = parse_auditor_evidence(
        accession_number="annual", registrant_cik=1, form_type="10-K",
        document_name="annual.htm", content=text,
        audited_period_end=date(2024, 12, 31), filing_date=date(2025, 2, 15),
        source_sha256="hash",
    )
    assert result.row is not None
    assert result.row.evidence_source == "sec_auditor_report"


def test_real_inline_xbrl_triplet_uses_name_attribute_and_report_date():
    content = """
    <html><body>
      <h2>Report of Independent Registered Public Accounting Firm</h2>
      <ix:nonNumeric name="dei:AuditorName" contextRef="D2024">Long Tail CPAs</ix:nonNumeric>
      <ix:nonNumeric name="dei:AuditorFirmId" contextRef="D2024">1042</ix:nonNumeric>
      <ix:nonNumeric name="dei:AuditorLocation" contextRef="D2024">Boston, MA</ix:nonNumeric>
      <p>February 14, 2025</p>
    </body></html>
    """

    result = parse_auditor_evidence(
        accession_number="annual-2024",
        registrant_cik=1001,
        form_type="10-KT",
        document_name="annual.htm",
        content=content,
        audited_period_end=date(2024, 12, 31),
        filing_date=date(2025, 2, 20),
        source_sha256="abc123",
    )

    assert result.outcome == "applicable_loaded"
    assert result.row is not None
    assert result.row.pcaob_firm_id == "1042"
    assert result.row.report_date == date(2025, 2, 14)
    assert result.row.report_date == date(2025, 2, 14)


def test_pcaob_registry_parser_keeps_full_identity_set_and_aliases():
    csv_data = b"Firm ID,Firm Name,City,State,Country,Status\n42,Ernst & Young LLP,New York,NY,US,Active\n1042,Long Tail CPAs,Boise,ID,US,Active\n"
    rows = parse_pcaob_firm_registry(
        csv_data, snapshot_uri="https://example/pcaob.csv", snapshot_sha256="sha"
    )
    assert [row.pcaob_firm_id for row in rows] == ["42", "1042"]
    assert rows[1].canonical_name == "Long Tail CPAs"
    assert rows[1].snapshot_sha256 == "sha"
