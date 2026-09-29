"""Real PG16: the CIK matching rule as `rules/` declares it (company mastering
ticket 15).

Ticket 04 proved the mechanics on fixture rules. These tests run the
production Mastering Policy (`company_source.POLICY`) as the operator's
approval would change it and nothing else: the Identifier Contract's three
approval fields filled and one `deterministic` activation for `company-cik`.
The stamps here are a fixture, not the approval.
"""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean import company_source
from edgar_warehouse.mdm.clean.activation import check_policy
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database

SEC = "sec.submissions.company.v1"
GLEIF = "gleif.level1.v1"
APPLE, MICROSOFT = "0000320193", "0000789019"


def approved() -> dict:
    """The production policy with only what an approval adds."""
    body = copy.deepcopy(company_source.POLICY)
    body["kinds"]["company"]["identifiers"]["cik"]["verification"].update(
        approved_by="operator",
        approved_at="2026-09-29T12:00:00Z",
        reason="fixture approval: ticket 15 PG16 proof, not the operator's",
    )
    body["automatic_rules"].append(
        {
            "kind": "company",
            "family": "binding",
            "rule_id": "company-cik",
            "rule_version": "2026-09-24",
            "verdict": "bind",
            "activation": "deterministic",
        }
    )
    check_policy(body)
    return body


def register(database, body) -> str:
    # The registry pins each dataset a record comes from. Its reading is the
    # fixture's: the subject here is the rule, not the SEC or GLEIF reading.
    for code in (SEC, GLEIF):
        core.register_reading(database, code, core.contract_body())
    with database.admin.begin() as conn:
        return register_policy(conn, copy.deepcopy(body))


def sec(cik, revision=1, key=None, name="Apple Inc."):
    return core.source(
        key=key or cik,
        source_code=SEC,
        revision=revision,
        fields={"name": name},
        identifiers={"cik": cik},
    )


def load(database, policy, batch, *assertions, checkpoint=1):
    return MergeStage(Store(database.application)).apply(
        batch_id=batch,
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="load",
        expected_checkpoint=checkpoint - 1,
        checkpoint=checkpoint,
        as_of=core.AS_OF,
        assertions=list(assertions),
    )


def companies(database):
    return {
        k: v
        for k, v in core.documents(database, "entity").items()
        if v["kind"] == "company" and v.get("status") != "alias"
    }


def operations(database):
    with database.application.connect() as conn:
        return sorted(conn.execute(text("SELECT operation FROM mdm_v2.decision")).scalars())


def test_the_committed_policy_matches_nothing_until_approved(database):
    policy = register(database, company_source.POLICY)
    load(database, policy, "b1", sec(APPLE))
    assert companies(database) == {}
    assert operations(database) == []


def test_each_cik_is_one_company_and_a_rerun_changes_nothing(database):
    policy = register(database, approved())
    first = load(database, policy, "b1", sec(APPLE), sec(MICROSOFT, name="Microsoft Corp"))
    made = companies(database)
    assert sorted(c["identifiers"]["cik"] for c in made.values()) == [[APPLE], [MICROSOFT]]
    # The same batch delivered again returns its first result, marked so.
    again = load(database, policy, "b1", sec(APPLE), sec(MICROSOFT, name="Microsoft Corp"))
    assert again == {**first, "duplicate": True}
    # A new revision of the same record keeps its Company; nothing is created.
    load(database, policy, "b2", sec(APPLE, revision=2, name="Apple Inc"), checkpoint=2)
    assert companies(database).keys() == made.keys()
    assert operations(database) == ["bind", "bind"]


def test_a_cik_never_lands_on_two_companies(database):
    # Two records carrying one CIK, in one batch and in the next: one Company.
    policy = register(database, approved())
    load(database, policy, "b1", sec(APPLE), sec(APPLE, key="0000000001"))
    load(database, policy, "b2", sec(APPLE, key="0000000002"), checkpoint=2)
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE]} and len(only["subjects"]) == 3


def test_a_company_whose_records_disagree_waits_and_gains_no_record(database):
    # Conflicting identifiers: its members name two CIKs, so the Company waits
    # in review, and a record carrying either CIK waits in the Stage
    # (operator, 2026-09-29, question 1).
    policy = register(database, approved())
    load(database, policy, "b1", sec(APPLE), sec(APPLE, key="0000000001"))
    load(database, policy, "b2", sec(MICROSOFT, revision=2, key="0000000001"), checkpoint=2)
    (held,) = companies(database).values()
    assert held["status"] == "review"
    assert held["identifiers"] == {"cik": [APPLE, MICROSOFT]}
    load(database, policy, "b3", sec(MICROSOFT, name="Microsoft Corp"), checkpoint=3)
    assert list(companies(database)) == [held["entity_id"]]
    assert len(companies(database)[held["entity_id"]]["subjects"]) == 2
    reviews = [r for r in core.documents(database, "review").values() if r.get("open")]
    assert "suspended_identifier" in {r["reason"] for r in reviews}


def test_reordered_delivery_ends_in_the_same_company(database):
    policy = register(database, approved())
    load(database, policy, "b1", sec(APPLE, revision=2, name="Apple Inc"))
    load(database, policy, "b2", sec(APPLE, revision=1), checkpoint=2)
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE]}
    assert only["fields"]["name"]["value"] == "Apple Inc"
    assert operations(database) == ["bind"]


@pytest.mark.xfail(
    strict=True,
    reason="Engine gap (ticket 15, Found): a bound record whose CIK changes re-keys "
    "its Company silently, and another filer with the new CIK joins it. The SEC "
    "reading cannot produce it: its record key is its CIK "
    "(tests/mdm/test_clean_cik_contract.py). The fix is Q9's rebuild from trusted "
    "evidence, not yet ticketed.",
)
def test_a_record_that_changes_its_cik_is_held_in_review(database):
    policy = register(database, approved())
    load(database, policy, "b1", sec(APPLE))
    load(database, policy, "b2", sec(MICROSOFT, revision=2, key=APPLE), checkpoint=2)
    load(database, policy, "b3", sec(MICROSOFT, name="Microsoft Corp"), checkpoint=3)
    held = [c for c in companies(database).values() if c["status"] == "review"]
    assert len(held) == 1 and len(held[0]["subjects"]) == 1


def test_the_cik_rule_never_consolidates_and_never_name_matches(database):
    policy = register(database, approved())
    # Two filers with one name stay two Companies; a GLEIF record with that
    # name waits, because the name rules are declared and switched off.
    gleif = core.source(
        key="HWUPKR0MPOU8FGXBT394",
        source_code=GLEIF,
        fields={"name": "Apple Inc."},
        identifiers={"lei": "HWUPKR0MPOU8FGXBT394"},
    )
    load(database, policy, "b1", sec(APPLE), sec(MICROSOFT, name="Apple Inc."), gleif)
    assert len(companies(database)) == 2
    assert operations(database) == ["bind", "bind"]
