"""Real PG16: a Form ADV adviser joins the SEC Company holding the CIK its filing lists (Item 1.D(3)).

The rule is the real policy's (iapd-adv-cik, on), on invented records through the Merge Stage:
- an adviser's filing joins the one Company holding its CIK, in either order of arrival;
- a filing that lists CIKs two Companies hold (an adviser's own and a fund's) goes to review and merges nothing;
- a CIK no Company holds goes onto the adviser its CRD creates;
- a second pass changes nothing.
"""

from __future__ import annotations

import copy

from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration.test_openfigi_security import bound
from tests.mdm import policy_layers
from tests.support import masters

FILINGS, COMPANIES = "iapd.adv.filings.v2", "sec.company.v1"
ADVISER_CIK, FUND_CIK, NEW_CIK = "0000900001", "0000900002", "0000900003"


def policy_body() -> dict:
    return copy.deepcopy(policy_layers.with_rules_on(files.policy(), "company", "iapd-adv-crd"))


def adviser(crd: str, *ciks: str) -> dict:
    return core.source(key=f"F{crd}", source_code=FILINGS, kind="company", fields={},
                       identifiers={"crd": crd, "cik": list(ciks)})


def company(cik: str) -> dict:
    return core.source(key=cik, source_code=COMPANIES, kind="company", fields={}, identifiers={"cik": cik})


def companies(database) -> int:
    return len([v for v in masters.bodies(database.application).values()
                if v["kind"] == "company" and v.get("status") != "alias"])


def load(database, batches):
    policy = policy_body()
    for records in batches:
        masters.seed(database.application, records, policy)
    return policy


def test_an_adviser_joins_the_company_holding_its_cik_whichever_arrives_first(database):
    load(database, [[company(ADVISER_CIK)], [adviser("100001", ADVISER_CIK)],
                    [adviser("100002", NEW_CIK)], [company(NEW_CIK)]])
    assert companies(database) == 2
    assert bound(database, FILINGS, "F100001") == bound(database, COMPANIES, ADVISER_CIK) is not None
    assert bound(database, FILINGS, "F100002") == bound(database, COMPANIES, NEW_CIK) is not None


def test_a_filing_listing_the_ciks_of_two_companies_goes_to_review_and_merges_nothing(database):
    load(database, [[company(ADVISER_CIK), company(FUND_CIK)], [adviser("100001", ADVISER_CIK, FUND_CIK)]])
    assert companies(database) == 2
    assert bound(database, FILINGS, "F100001") is None
    assert "conflicting_identifiers" in masters.reviews(database.application)


def test_a_second_pass_of_the_same_records_changes_nothing(database):
    records = [company(ADVISER_CIK), adviser("100001", ADVISER_CIK), adviser("100002", NEW_CIK)]
    policy = load(database, [records[:1], records[1:]])
    before = (companies(database), bound(database, FILINGS, "F100001"), bound(database, FILINGS, "F100002"))
    masters.seed(database.application, records, policy)
    assert (companies(database), bound(database, FILINGS, "F100001"), bound(database, FILINGS, "F100002")) == before
    assert before[0] == 2
