"""Step 3 of mastering: every identifier a record states is searched together, and a name only when no identifier finds.

Invented records under the real rules on PostgreSQL 16. The limits of each Identifier Contract (issuer, forward,
reverse) are proved in tests/mdm/test_identifier_lists.py and tests/mdm/test_cik_contract.py.
"""

from edgar_warehouse.mdm import adapters
from tests.integration import test_mdm_postgres as core
from tests.support import masters

ADV, SEC, CUSTODIANS = "iapd.adv.filings.v2", "sec.company.v1", "iapd.adv.custodians.v1"
LEI = "9999000000EXAMPLE016"  # invented


def company(code, key, identifiers, name, **more):
    return core.source(key=key, source_code=code, kind="company", fields={"name": name}, identifiers=identifiers, **more)


def test_a_record_stating_two_identifiers_is_searched_on_both_together(database):
    holds_cik = masters.seed(database.application, [company(SEC, "0000999101", {"cik": "0000999101"}, "Holds The Cik")])
    masters.seed(database.application, [company(ADV, "f0", {"crd": "999102"}, "Holds The Crd")])
    assert len(masters.bodies(database.application)) == 2
    # Control: a filing stating only the CIK finds the one Company holding it and joins it, with no review.
    joined = masters.seed(database.application, [company(ADV, "f-cik", {"cik": "0000999101"}, "States The Cik")])
    assert joined[("f-cik")] == holds_cik["0000999101"] and masters.reviews(database.application) == []
    # A filing stating both finds two golden records, each through one identifier alone: it joins neither and goes to
    # review (step 4); had only the CIK been searched, it would have joined the first without notice.
    both = masters.seed(database.application, [company(ADV, "f-both", {"cik": "0000999101", "crd": "999102"}, "States Both")])
    assert both.get("f-both") is None
    assert "conflicting_identifiers" in masters.reviews(database.application)
    assert len(masters.bodies(database.application)) == 2


def test_a_name_is_tried_only_when_no_identifier_finds_a_golden_record(database):
    named = masters.seed(database.application, [company(SEC, "0000999103", {"cik": "0000999103"}, "Example Name Holdings Inc",
        cross_references={"name_id": adapters._name_id("Example Name Holdings Inc")})])
    held_lei = masters.seed(database.application, [company(CUSTODIANS, f"lei:{LEI}", {"lei": LEI}, "Other Name Ltd")])
    # The custodian record states a LEI one Company holds and a name another Company holds: the identifier decides.
    found = masters.seed(database.application, [company(CUSTODIANS, "second", {"lei": LEI}, "Example Name Holdings Inc",
        cross_references={"name_id": adapters._name_id("Example Name Holdings Inc")})])
    assert found["second"] == held_lei[f"lei:{LEI}"] != named["0000999103"]
    assert masters.reviews(database.application) == []
