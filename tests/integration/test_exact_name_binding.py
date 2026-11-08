"""Real PG16: a record with only a name joins the one Company holding that name (ticket 01).

The exact-name family on invented records through the Merge Stage. The rule is the real policy's (iapd-adv-custodian-name, on):
- a record carrying only a name id joins the one Company whose other-source record carries it;
- it waits when no Company holds the name, and is joined when a holder arrives later;
- it goes to review, and joins nothing, when two Companies hold the name;
- it never creates a Company, and a second pass changes nothing.
"""

from __future__ import annotations

import copy

from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration.test_openfigi_security import bound
from tests.mdm import policy_layers
from tests.support import masters

FILINGS, CUSTODIANS = "iapd.adv.filings.v2", "iapd.adv.custodians.v1"
NAME_ONE, NAME_TWO, NAME_NONE = "a1" * 32, "b2" * 32, "c3" * 32  # invented name ids (64 hex)
def policy_body() -> dict:
    """The real policy: the rule is declared and on in it (ticket 01)."""
    return copy.deepcopy(policy_layers.with_rules_on(files.policy(), "company", "iapd-adv-crd"))


def adviser(crd: str, name_id: str) -> dict:
    return core.source(key=f"F{crd}", source_code=FILINGS, kind="company", fields={}, identifiers={"crd": crd},
                       cross_references={"name_id": name_id})


def custodian(key: str, name_id: str) -> dict:
    return core.source(key=key, source_code=CUSTODIANS, kind="company", fields={}, cross_references={"name_id": name_id})


def companies(database) -> int:
    return len([v for v in masters.bodies(database.application).values()
                if v["kind"] == "company" and v.get("status") != "alias"])


def load(database, batches):
    policy = policy_body()
    for records in batches:
        masters.seed(database.application, records, policy)
    return policy


def test_a_name_held_by_one_company_attaches_the_record_and_makes_no_company(database):
    load(database, [[adviser("900001", NAME_ONE), adviser("900002", NAME_TWO)],
                    [custodian("name:ONE", NAME_ONE), custodian("name:NONE", NAME_NONE)]])
    assert companies(database) == 2
    assert bound(database, CUSTODIANS, "name:ONE") == bound(database, FILINGS, "F900001") is not None
    assert bound(database, CUSTODIANS, "name:NONE") is None  # no Company holds it: it waits


def test_a_record_that_waited_is_joined_when_its_holder_arrives_later(database):
    load(database, [[custodian("name:ONE", NAME_ONE)], [adviser("900001", NAME_ONE)]])
    assert companies(database) == 1
    assert bound(database, CUSTODIANS, "name:ONE") == bound(database, FILINGS, "F900001") is not None


def test_a_name_held_by_two_companies_goes_to_review_and_joins_neither(database):
    load(database, [[adviser("900001", NAME_ONE), adviser("900002", NAME_ONE)], [custodian("name:ONE", NAME_ONE)]])
    assert companies(database) == 2
    assert bound(database, CUSTODIANS, "name:ONE") is None
    assert "ambiguous_name_match" in masters.reviews(database.application)


def test_a_second_pass_of_the_same_records_changes_nothing(database):
    first = [adviser("900001", NAME_ONE)]
    second = [custodian("name:ONE", NAME_ONE), custodian("name:NONE", NAME_NONE)]
    policy = load(database, [first, second])
    before = (companies(database), bound(database, CUSTODIANS, "name:ONE"), bound(database, CUSTODIANS, "name:NONE"))
    masters.seed(database.application, [*first, *second], policy)
    assert (companies(database), bound(database, CUSTODIANS, "name:ONE"), bound(database, CUSTODIANS, "name:NONE")) == before
