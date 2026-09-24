"""Real PG16: identifier-only matching rules (company mastering ticket 04).

A record whose CIK is already on exactly one Company joins it; a new CIK
creates one Company; an LEI rule that says `wait` leaves the record in the
Stage; an identifier on two Companies, or two identifiers pointing at two
Companies, never binds. Every automatic proposal is assessed first (Q13), a
redelivered batch returns its first result, and a run that proposed a new
Company re-checks under the Merge Stage lock before minting it.

The activations below are **fixture** activations: the contracts' verification
blocks are shape only. Nothing in the production policy activates a matching
rule before the operator approves its digest (ticket 06).
"""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean import assessment
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_clean_activation import CIK_CONTRACT, CIK_RULE

postgres = core.postgres
database = core.database

APPLE_CIK = "0000320193"
APPLE_LEI = "HWUPKR0MPOU8FGXBT394"
LEI_RULE = {
    **CIK_RULE,
    "rule_id": "company-lei",
    "on_no_match": "wait",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "lei"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "lei"}},
    ],
}
LEI_CONTRACT = {
    **CIK_CONTRACT,
    "authority": "GLEIF",
    "normalizer": "normalize_identifier@lei-v1",
}


def matching_policy(database, *, active=True):
    body = {
        "version": "identifier-binding-test",
        "required_consumers": ["export", "graph"],
        "automatic_rules": [],
        "kinds": {
            "company": {
                "version": "company-test",
                "defaults": {
                    "sources": ["fixture.primary", "fixture.secondary"],
                    "allow_unknown_effective": True,
                },
                "rules": [CIK_RULE, LEI_RULE],
                "identifiers": {"cik": CIK_CONTRACT, "lei": LEI_CONTRACT},
            }
        },
    }
    if active:
        body["automatic_rules"] = [
            {
                "kind": "company",
                "family": "binding",
                "rule_id": rule["rule_id"],
                "rule_version": rule["version"],
                "verdict": "bind",
                "activation": "deterministic",
            }
            for rule in (CIK_RULE, LEI_RULE)
        ]
    with database.admin.begin() as conn:
        return register_policy(conn, copy.deepcopy(body))


def record(key, source_code="fixture.primary", **identifiers):
    return core.source(
        key=key,
        source_code=source_code,
        fields={"name": f"Company {key}"},
        identifiers=identifiers,
    )


def load(database, policy, batch, *assertions, consumer="load", checkpoint=1):
    return MergeStage(Store(database.application)).apply(
        batch_id=batch,
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer=consumer,
        expected_checkpoint=checkpoint - 1,
        checkpoint=checkpoint,
        as_of=core.AS_OF,
        assertions=list(assertions),
    )


def companies(database):
    return {
        k: v
        for k, v in core.documents(database, "entity").items()
        if v["kind"] == "company"
    }


def open_reviews(database):
    return [v for v in core.documents(database, "review").values() if v.get("open")]


def assessments(database):
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM mdm_v2.assessment"))


def test_a_new_cik_creates_one_company_and_a_second_record_joins_it(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE_CIK]}
    # A second record from another dataset carrying the same CIK joins it.
    load(
        database,
        policy,
        "b2",
        record("b", "fixture.secondary", cik=APPLE_CIK),
        checkpoint=2,
    )
    after = companies(database)
    assert list(after) == [only["entity_id"]]
    assert len(after[only["entity_id"]]["subjects"]) == 2
    # Q13: both automatic proposals were assessed before they committed.
    assert assessments(database) == 2
    with database.application.connect() as conn:
        actors = conn.execute(
            text("SELECT body->>'actor' FROM mdm_v2.decision WHERE operation='bind'")
        ).scalars()
        assert sorted(actors) == ["rule:company-cik@2026-09-24"] * 2


def test_a_second_record_joins_whichever_order_they_arrive_in(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("b", "fixture.secondary", cik=APPLE_CIK))
    load(database, policy, "b2", record("a", cik=APPLE_CIK), checkpoint=2)
    assert len(companies(database)) == 1


def test_many_new_records_with_one_cik_create_one_company(database):
    """Ticket 03 decision 3: forty filings, one Company, not forty."""
    policy = matching_policy(database)
    load(
        database,
        policy,
        "b1",
        record("a", cik=APPLE_CIK),
        record("b", "fixture.secondary", cik=APPLE_CIK),
    )
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 2


def test_an_unmatched_lei_waits_in_the_stage(database):
    """Operator, 2026-09-24: an unlinked GLEIF record creates no Company."""
    policy = matching_policy(database)
    load(database, policy, "b1", record("g", "fixture.secondary", lei=APPLE_LEI))
    assert companies(database) == {}
    assert [r["reason"] for r in open_reviews(database)] == ["binding_required"]
    assert assessments(database) == 0


def test_an_lei_already_on_a_company_joins_it(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK, lei=APPLE_LEI))
    load(
        database,
        policy,
        "b2",
        record("g", "fixture.secondary", lei=APPLE_LEI),
        checkpoint=2,
    )
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}


def test_a_redelivered_batch_returns_its_first_result(database):
    """Lost acknowledgement: the rule's fresh ids must not break redelivery."""
    policy = matching_policy(database)
    command = {
        "batch_id": "b1",
        "run_id": str(uuid4()),
        "policy_digest": policy,
        "consumer": "load",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "as_of": core.AS_OF,
        "assertions": [record("a", cik=APPLE_CIK)],
    }
    stage = MergeStage(Store(database.application))
    first = stage.apply(**command)
    again = stage.apply(**{**command, "run_id": str(uuid4())})
    assert again["duplicate"] and again["generation"] == first["generation"]
    assert len(companies(database)) == 1


def test_an_identifier_on_two_companies_never_binds(database):
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    a, b = record("a", cik=APPLE_CIK), record("b", "fixture.secondary", cik=APPLE_CIK)
    left, bind_a = core.identity_and_binding(a)
    right, bind_b = core.identity_and_binding(b)
    stage.apply(
        batch_id="seed",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="seed",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[a, b],
        identities=[left, right],
        decisions=[bind_a, bind_b],
    )
    load(database, policy, "b1", record("c", cik=APPLE_CIK))
    assert len(companies(database)) == 2
    assert "ambiguous_identifier" in {r["reason"] for r in open_reviews(database)}


def test_a_cik_and_an_lei_pointing_at_two_companies_never_bind(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    load(
        database,
        policy,
        "b2",
        record("b", cik="0000789019", lei=APPLE_LEI),
        checkpoint=2,
    )
    load(
        database,
        policy,
        "b3",
        record("c", "fixture.secondary", cik=APPLE_CIK, lei=APPLE_LEI),
        checkpoint=3,
    )
    assert len(companies(database)) == 2
    assert "conflicting_identifiers" in {r["reason"] for r in open_reviews(database)}


def test_a_concurrent_run_cannot_create_a_second_company_for_one_cik(database):
    """B is assessed to create a Company; A creates it first; B must not."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    late = {
        "batch_id": "late",
        "run_id": str(uuid4()),
        "policy_digest": policy,
        "consumer": "late",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "as_of": core.AS_OF,
        "assertions": [record("b", "fixture.secondary", cik=APPLE_CIK)],
    }
    proposed = stage.propose(**late)
    assert len(proposed["identities"]) == 1
    prepared = stage.assess(**late, automatic=proposed)
    load(database, policy, "early", record("a", cik=APPLE_CIK), consumer="early")
    with pytest.raises(assessment.StaleAssessment):
        stage.apply_assessment(prepared["assessment_id"], run_id=late["run_id"])
    # The retry re-proposes against the Company that now exists.
    stage.apply(**{**late, "run_id": str(uuid4())})
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 2


def test_without_an_activation_nothing_matches_automatically(database):
    policy = matching_policy(database, active=False)
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    assert companies(database) == {}
    assert assessments(database) == 0
