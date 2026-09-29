"""The CIK matching rule relies on an SEC record's CIK being its key
(company mastering ticket 15).

A bound record whose CIK changes would re-key its Company silently (see the
xfail in tests/integration/test_clean_cik_rule.py). The SEC reading cannot do
that while its record key and its CIK are one column in one format; a mapping
that separates them fails here first.
"""

from edgar_warehouse.mdm.clean import company_source, gleif_source


def test_the_sec_record_key_is_its_cik():
    adapter = company_source.CONTRACT["adapter"]
    assert adapter["record_key"] == ["cik"]
    assert adapter["identifiers"] == {"cik": "cik"}
    assert adapter["record_key_format"] == adapter["identifier_formats"]["cik"] == "sec_cik"


def test_each_feed_maps_only_the_identifiers_it_issues():
    """Operator, 2026-09-29 (ticket 15, question 2): only the issuer's own
    records count toward an identifier conflict. Today no feed maps an
    identifier it does not issue, so the Merge Stage's conflict count has not
    been changed. A feed that starts to must bring that change with it."""
    assert set(company_source.CONTRACT["adapter"]["identifiers"]) == {"cik"}
    for member in ("level1", "relationships", "reporting_exceptions"):
        mapped = gleif_source.dataset_contract(member)["adapter"].get("identifiers") or {}
        assert set(mapped) <= {"lei"}, member
