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
                      "confidential_omission": True}
