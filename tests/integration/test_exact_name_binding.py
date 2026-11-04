"""Real PG16: a record with only a name joins the one Company holding that name (ticket 01).

The exact-name family on invented records through the Merge Stage. The rule is added to a copy of
the policy only (the real policy declares none yet):
- a record carrying only a name id joins the one Company whose other-source record carries it;
- it waits when no Company holds the name, and is joined when a holder arrives later;
- it goes to review, and joins nothing, when two Companies hold the name;
- it never creates a Company, and a second pass changes nothing.
"""

from __future__ import annotations

import copy

from edgar_warehouse.mdm.merge import MergeStage
from edgar_warehouse.mdm.store import Store, register_policy
from edgar_warehouse.rules import files
from tests.integration import test_mdm_postgres as core
from tests.integration import test_nport_link_start as nport
from tests.integration.test_openfigi_security import bound
from tests.mdm import policy_layers

FILINGS, CUSTODIANS = "iapd.adv.filings.v1", "iapd.adv.custodians.v1"
NAME_ONE, NAME_TWO, NAME_NONE = "a1" * 32, "b2" * 32, "c3" * 32  # invented name ids (64 hex)
RULE = {"rule_id": "iapd-adv-custodian-name", "version": "2026-11-04.exact-name", "family": "exact_name_binding",
        "source": CUSTODIANS, "holder_sources": [FILINGS], "applies_to_verdict": "company", "emits": ["bind"],
        "key": "name_id@1", "on_no_match": "wait", "on_several": "review"}
ENTRY = {"kind": "company", "family": "exact_name_binding", "rule_id": RULE["rule_id"], "rule_version": RULE["version"],
         "verdict": "bind", "activation": "exact_name",
         "proof": {"names": 3, "attached": 1, "review": 1, "waiting": 1, "second_pass_changed_nothing": True,
                   "approved_by": "fixture", "approved_at": "2026-11-04T00:00:00Z", "reason": "fixture proof"}}


def policy_body() -> dict:
    body = policy_layers.with_rules_on(files.policy(), "company", "iapd-adv-crd")
    body = copy.deepcopy(body)
    body["kinds"]["company"]["rules"].append(copy.deepcopy(RULE))
    body["automatic_rules"].append(copy.deepcopy(ENTRY))
    return body


def adviser(crd: str, name_id: str) -> dict:
    return core.source(key=f"F{crd}", source_code=FILINGS, kind="company", fields={}, identifiers={"crd": crd},
                       cross_references={"name_id": name_id})


def custodian(key: str, name_id: str) -> dict:
    return core.source(key=key, source_code=CUSTODIANS, kind="company", fields={}, cross_references={"name_id": name_id})


def companies(database) -> int:
    return len([v for v in core.documents(database, "entity").values() if v["kind"] == "company" and v.get("status") != "alias"])


def load(database, batches):
    for code in (FILINGS, CUSTODIANS):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        policy = register_policy(conn, policy_body())
    stage = MergeStage(Store(database.application))
    for number, records in enumerate(batches, 1):
        nport.apply(stage, policy, f"batch-{number}", records, number)
    return stage, policy


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
    assert "ambiguous_name_match" in [r["reason"] for r in core.documents(database, "review").values() if r.get("open")]


def test_a_second_pass_of_the_same_records_changes_nothing(database):
    first = [adviser("900001", NAME_ONE)]
    second = [custodian("name:ONE", NAME_ONE), custodian("name:NONE", NAME_NONE)]
    stage, policy = load(database, [first, second])
    before = (companies(database), bound(database, CUSTODIANS, "name:ONE"), bound(database, CUSTODIANS, "name:NONE"))
    nport.apply(stage, policy, "again", [*first, *second], 3)
    assert (companies(database), bound(database, CUSTODIANS, "name:ONE"), bound(database, CUSTODIANS, "name:NONE")) == before
