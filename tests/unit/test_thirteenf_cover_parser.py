from edgar_warehouse.parsers.thirteenf_cover import parse_thirteenf_cover


def test_parse_restatement_cover_metadata() -> None:
    result = parse_thirteenf_cover("""
      <edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">
        <headerData><filerInfo><periodOfReport>03-31-2024</periodOfReport></filerInfo></headerData>
        <formData><coverPage><reportCalendarOrQuarter>03-31-2024</reportCalendarOrQuarter>
          <isAmendment>true</isAmendment><amendmentType>RESTATEMENT</amendmentType>
          <confidentialOmitted>false</confidentialOmitted>
        </coverPage></formData>
      </edgarSubmission>
    """)
    assert result["amendment_type"] == "restatement"
    assert result["confidential_omission"] is False


def test_parse_added_holdings_cover_metadata() -> None:
    result = parse_thirteenf_cover("""
      <edgarSubmission><isAmendment>true</isAmendment>
      <amendmentType>NEW HOLDINGS</amendmentType><confidentialOmitted>true</confidentialOmitted>
      </edgarSubmission>
    """)
    assert result == {"is_amendment": True, "amendment_type": "added_holdings",
                      "confidential_omission": True, "period_of_report": None}


def test_cover_extracts_period_of_report_in_both_formats() -> None:
    """Production regression (gatev2 run, 2026-07-19): all 101,444 13F freeze
    candidates carry NULL report_date (quarterly indexes have none), and the
    ingest passed "" into a DuckDB DATE column — ConversionException killed
    the batch and the execution. The cover page's periodOfReport is the
    authoritative period source; it arrives as MM-DD-YYYY (normalized to ISO)
    and must be None (never "") when absent."""
    base = (
        '<edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">'
        "<headerData><filerInfo><periodOfReport>{p}</periodOfReport>"
        "</filerInfo></headerData><formData><coverPage>"
        "<isAmendment>false</isAmendment></coverPage></formData>"
        "</edgarSubmission>"
    )
    assert parse_thirteenf_cover(base.format(p="06-30-2024"))["period_of_report"] == "2024-06-30"
    assert parse_thirteenf_cover(base.format(p="2024-06-30"))["period_of_report"] == "2024-06-30"
    assert parse_thirteenf_cover(base.format(p="2024/06/30"))["period_of_report"] == "2024-06-30"
    absent = base.replace("<periodOfReport>{p}</periodOfReport>", "")
    assert parse_thirteenf_cover(absent)["period_of_report"] is None
