"""The CIK matching rule relies on an SEC record's CIK being its key
(company mastering ticket 15).

A bound record whose CIK changes would re-key its Company silently (see the
xfail in tests/integration/test_clean_cik_rule.py). The SEC reading cannot do
that while its record key and its CIK are one column in one format; a mapping
that separates them fails here first.
"""

from edgar_warehouse.mdm.clean import company_source
from edgar_warehouse.rules import files


def test_the_sec_record_key_is_its_cik():
    adapter = company_source.CONTRACT["adapter"]
    assert adapter["record_key"] == ["cik"]
    assert adapter["identifiers"] == {"cik": "cik"}
    assert adapter["record_key_format"] == adapter["identifier_formats"]["cik"] == "sec_cik"



def _issuers() -> dict[str, set[str]]:
    """Who issues each identifier: every kind's Identifier Contract sources,
    as the Merge Stage reads them (platform validation 05a). The LEI has no
    contract yet; GLEIF's Level 1 issues it."""
    issuers: dict[str, set[str]] = {"lei": {"gleif.level1.v1"}}
    for block in company_source.POLICY["kinds"].values():
        for namespace, contract in (block.get("identifiers") or {}).items():
            issuers.setdefault(namespace, set()).update(contract["sources"])
    return issuers


def test_each_feed_maps_only_the_identifiers_it_issues():
    """Operator, 2026-09-29 (ticket 15, question 2): only the issuer's own
    records count toward an identifier conflict. So a feed maps only an
    identifier some kind's Identifier Contract names it as issuing. A second
    kind's feed that reads SEC's CIK (Person) declares itself there, and the
    Merge Stage counts it across kinds (platform validation 05a). A feed that
    maps one it does not issue must bring a change to the conflict count."""
    issuers = _issuers()
    mapped = {}
    for folder in sorted((files.ROOT / "sources").iterdir()):
        for code, body in (files.source(folder.name).get("mdm") or {}).items():
            for namespace in ((body.get("contract") or {}).get("adapter") or {}).get("identifiers") or {}:
                mapped[(code, namespace)] = code in issuers.get(namespace, set())
    assert {("sec.submissions.company.v1", "cik"), ("gleif.level1.v1", "lei")} <= set(mapped)
    assert all(mapped.values()), {pair for pair, issued in mapped.items() if not issued}
