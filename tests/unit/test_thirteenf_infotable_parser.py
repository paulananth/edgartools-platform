from edgar_warehouse.parsers.thirteenf import parse_thirteenf

_NORMAL_INFOTABLE = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>Air Liquide SA</nameOfIssuer>
    <titleOfClass>CS</titleOfClass>
    <cusip>009126202</cusip>
    <value>224152</value>
    <shrsOrPrnAmt>
      <sshPrnamt>5413</sshPrnamt>
      <sshPrnamtType>SH</sshPrnamtType>
    </shrsOrPrnAmt>
    <investmentDiscretion>SOLE</investmentDiscretion>
    <votingAuthority>
      <Sole>5413</Sole>
      <Shared>0</Shared>
      <None>0</None>
    </votingAuthority>
  </infoTable>
</informationTable>
"""

# Minimal reproduction of the real production filing (accession
# 0002000324-25-002721, MANNING & NAPIER ADVISORS LLC, CIK 62039, 2026-07-20
# gatev3 failure): the document declares xmlns:xsi before the real content
# namespace and no default namespace, using an ns1: prefix throughout.
_XSI_FIRST_NAMESPACE_INFOTABLE = """<?xml version="1.0" encoding="UTF-8"?>
<ns1:informationTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <ns1:infoTable>
    <ns1:nameOfIssuer>Air Liquide SA</ns1:nameOfIssuer>
    <ns1:titleOfClass>CS</ns1:titleOfClass>
    <ns1:cusip>009126202</ns1:cusip>
    <ns1:value>224152</ns1:value>
    <ns1:shrsOrPrnAmt>
      <ns1:sshPrnamt>5413</ns1:sshPrnamt>
      <ns1:sshPrnamtType>SH</ns1:sshPrnamtType>
    </ns1:shrsOrPrnAmt>
    <ns1:investmentDiscretion>SOLE</ns1:investmentDiscretion>
    <ns1:votingAuthority>
      <ns1:Sole>5413</ns1:Sole>
      <ns1:Shared>0</ns1:Shared>
      <ns1:None>0</ns1:None>
    </ns1:votingAuthority>
  </ns1:infoTable>
</ns1:informationTable>
"""

_GENUINELY_EMPTY_INFOTABLE = """<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
</informationTable>
"""


def test_normal_single_namespace_infotable_parses() -> None:
    result = parse_thirteenf(
        infotable_xml=_NORMAL_INFOTABLE,
        cik=62039,
        accession_number="0002000324-25-000001",
        period_of_report="2025-06-30",
    )
    rows = result["sec_thirteenf_holding"]
    assert len(rows) == 1
    assert rows[0]["issuer_name"] == "Air Liquide SA"
    assert rows[0]["shares_held"] == 5413.0


def test_xsi_first_namespace_infotable_recovers_holdings() -> None:
    """Regression: edgar.thirteenf.parsers.infotable_xml.parse_infotable_xml
    picks the namespace via nsmap.get(None) or list(nsmap.values())[0]. When
    xmlns:xsi is declared before the real content namespace and there is no
    default namespace, lxml's nsmap lists xsi first, the fallback picks the
    wrong namespace, findall(.//infoTable) matches nothing, and edgartools
    silently returns an empty DataFrame for a filing with real holdings.
    parse_thirteenf must recover the holdings via the xsi-stripped fallback
    rather than reporting zero rows for a non-empty filing."""
    result = parse_thirteenf(
        infotable_xml=_XSI_FIRST_NAMESPACE_INFOTABLE,
        cik=62039,
        accession_number="0002000324-25-002721",
        period_of_report="2025-06-30",
    )
    rows = result["sec_thirteenf_holding"]
    assert len(rows) == 1
    assert rows[0]["issuer_name"] == "Air Liquide SA"
    assert rows[0]["cusip"] == "009126202"
    assert rows[0]["shares_held"] == 5413.0
    assert rows[0]["market_value"] == 224152.0


def test_genuinely_empty_infotable_stays_empty() -> None:
    """The xsi-stripped fallback must never fabricate holdings: a filing with
    no infoTable elements at all (e.g. full confidential-treatment omission)
    must still report zero rows, with or without the xsi declaration."""
    result = parse_thirteenf(
        infotable_xml=_GENUINELY_EMPTY_INFOTABLE,
        cik=62039,
        accession_number="0002000324-25-000002",
        period_of_report="2025-06-30",
    )
    assert result["sec_thirteenf_holding"] == []

    xsi_variant = _GENUINELY_EMPTY_INFOTABLE.replace(
        '<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">',
        '<ns1:informationTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable">',
    ).replace("</informationTable>", "</ns1:informationTable>")
    result = parse_thirteenf(
        infotable_xml=xsi_variant,
        cik=62039,
        accession_number="0002000324-25-000003",
        period_of_report="2025-06-30",
    )
    assert result["sec_thirteenf_holding"] == []
