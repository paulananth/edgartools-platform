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
    """Who issues each identifier: the Identifier Contract's sources where one
    is declared. The LEI has no contract yet; GLEIF's Level 1 issues it."""
    declared = company_source.POLICY["kinds"]["company"]["identifiers"]
    return {"lei": {"gleif.level1.v1"}} | {ns: set(c["sources"]) for ns, c in declared.items()}


def test_each_feed_maps_only_the_identifiers_it_issues():
    """Operator, 2026-09-29 (ticket 15, question 2): only the issuer's own
    records count toward an identifier conflict. Today no feed maps an
    identifier it does not issue, so the Merge Stage's conflict count has not
    been changed. A feed that starts to must bring that change with it."""
    issuers = _issuers()
    mapped = {}
    for folder in sorted((files.ROOT / "sources").iterdir()):
        for code, body in (files.source(folder.name).get("mdm") or {}).items():
            for namespace in ((body.get("contract") or {}).get("adapter") or {}).get("identifiers") or {}:
                mapped[(code, namespace)] = code in issuers.get(namespace, set())
    assert mapped == {("sec.submissions.company.v1", "cik"): True, ("gleif.level1.v1", "lei"): True}
