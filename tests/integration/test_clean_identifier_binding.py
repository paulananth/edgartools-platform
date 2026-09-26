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
import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import assessment
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Conflict, Store, register_policy
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_clean_activation import CIK_CONTRACT, CIK_RULE

postgres = core.postgres
database = core.database

APPLE_CIK = "0000320193"
APPLE_LEI = "HWUPKR0MPOU8FGXBT394"
# fixture.primary stands for SEC (it issues CIKs), fixture.secondary for GLEIF
# (it issues LEIs). Only the issuer's record creates a Company; any record may
# join one through an identifier the issuer's record established (Q14).
CIK_MINT = {**CIK_RULE, "source": "fixture.primary"}
# A rule that only joins may come from any source, so it names none.
UNSCOPED_RULE = {k: v for k, v in CIK_RULE.items() if k != "source"}
CIK_JOIN = {**UNSCOPED_RULE, "rule_id": "company-cik-join", "on_no_match": "wait"}
LEI_RULE = {
    **UNSCOPED_RULE,
    "rule_id": "company-lei",
    "on_no_match": "wait",
    "when": [
        {"primitive": "identifier_match@1", "args": {"namespace": "lei"}},
        {"primitive": "identifier_cardinality@1", "args": {"namespace": "lei"}},
    ],
}
CIK_ISSUED = {**CIK_CONTRACT, "sources": ["fixture.primary"]}
LEI_CONTRACT = {
    **CIK_CONTRACT,
    "authority": "GLEIF",
    "sources": ["fixture.secondary"],
    "normalizer": "normalize_identifier@lei-v1",
}
RULES = (CIK_MINT, CIK_JOIN, LEI_RULE)


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
                "rules": list(RULES),
                "identifiers": {"cik": CIK_ISSUED, "lei": LEI_CONTRACT},
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
            for rule in RULES
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
        # SEC's record created the Company; the other dataset's record joined.
        assert sorted(actors) == [
            "rule:company-cik-join@2026-09-24",
            "rule:company-cik@2026-09-24",
        ]


def test_a_record_that_is_not_the_issuer_waits_until_the_issuer_arrives(database):
    """Only SEC's own record creates a Company from a CIK (Q14)."""
    policy = matching_policy(database)
    other = record("b", "fixture.secondary", cik=APPLE_CIK)
    load(database, policy, "b1", other)
    assert companies(database) == {}
    load(database, policy, "b2", record("a", cik=APPLE_CIK), checkpoint=2)
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 1
    # Its next delivery finds the Company the issuer's record created.
    load(database, policy, "b3", other, checkpoint=3)
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 2


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


def test_a_record_carrying_both_ids_does_not_attach_its_lei(database):
    """Q14: an LEI does not become a CIK crosswalk because both values exist."""
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK, lei=APPLE_LEI))
    gleif = record("g", "fixture.secondary", lei=APPLE_LEI)
    load(database, policy, "b2", gleif, checkpoint=2)
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 1


def test_a_hand_matched_record_does_not_attach_its_lei_within_the_batch(database):
    """Ticket 11, gap 2: Q14 holds inside one batch too.

    The caller binds an SEC record that also carries an LEI; a GLEIF record
    with that LEI in the same batch must not join through it.
    """
    policy = matching_policy(database)
    sec = record("a", cik=APPLE_CIK, lei=APPLE_LEI)
    gleif = record("g", "fixture.secondary", lei=APPLE_LEI)
    identity, bind = core.identity_and_binding(sec)
    MergeStage(Store(database.application)).apply(
        batch_id="b1",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="load",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[sec, gleif],
        identities=[identity],
        decisions=[bind],
    )
    (only,) = companies(database).values()
    assert len(only["subjects"]) == 1


def test_an_lei_held_through_its_issuers_record_lets_another_record_join(database):
    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (company,) = companies(database)
    # Stands in for ticket 08: the GLEIF record is linked to the Company.
    gleif = record("g", "fixture.secondary", lei=APPLE_LEI)
    _, link = core.identity_and_binding(gleif, company)
    MergeStage(Store(database.application)).apply(
        batch_id="link",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="link",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[gleif],
        decisions=[link],
    )
    load(
        database,
        policy,
        "b2",
        record("g2", "fixture.secondary", lei=APPLE_LEI),
        checkpoint=2,
    )
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}
    assert len(only["subjects"]) == 3


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
    a, b = record("a", cik=APPLE_CIK), record("b2", cik=APPLE_CIK)
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
    load(database, policy, "b2", record("m", cik="0000789019"), checkpoint=2)
    _apple, microsoft = sorted(
        companies(database).values(), key=lambda c: c["identifiers"]["cik"][0]
    )
    # Microsoft holds the LEI through its issuer's record.
    gleif = record("g", "fixture.secondary", lei=APPLE_LEI)
    _, link = core.identity_and_binding(gleif, microsoft["entity_id"])
    MergeStage(Store(database.application)).apply(
        batch_id="link",
        run_id=str(uuid4()),
        policy_digest=policy,
        consumer="link",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
        assertions=[gleif],
        decisions=[link],
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
        "assertions": [record("b", cik=APPLE_CIK)],
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


def test_migration_035_applies_to_a_populated_store(postgres):
    """CLAUDE.md: a migration is tested over real rows, in production's order.

    A store at 034 already holds an assessment of a caller's binding. 035
    replaces the function that records assessments; the old one must survive,
    and a rule's proposal, kept beside the command, must then be accepted.
    """
    from unittest import mock

    import edgar_warehouse.mdm.clean.store as store_module

    admin, app = postgres
    names = list(store_module.CLEAN_MDM_MIGRATIONS)
    through_034 = tuple(n for n in names if n < "035")
    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", through_034):
        database = core.initialize_database(admin, app)
        company = core.source(key="pop-1", fields={"name": "Acme"})
        identity, binding = core.identity_and_binding(company)
        core.apply(
            database,
            1,
            assertions=[company],
            identities=[identity],
            decisions=[binding],
        )
        assert assessments(database) == 1
    core.migrate(admin, application_role="clean_application")
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM mdm_v2.migration WHERE name LIKE '035%'")
            )
            == 1
        )
    assert assessments(database) == 1
    policy = matching_policy(database)
    load(database, policy, "after-035", record("new", cik=APPLE_CIK), consumer="after")
    assert assessments(database) == 2
    assert len(companies(database)) == 2


def _issuer_conflict(database, policy, *also):
    """A Company whose two SEC records came to name two CIKs (Q9's contradiction).

    a creates the Company from its CIK; b, another record from the CIK's
    issuing source, joins it through the same CIK; b's next reading names a
    different CIK. Returns the Company and the batch's other results.
    """
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    load(database, policy, "b2", record("b", cik=APPLE_CIK), checkpoint=2)
    (company,) = companies(database)
    moved = core.source("b", revision=2, identifiers={"cik": "0000000002"})
    load(database, policy, "b3", moved, *also, checkpoint=3)
    return company


def test_a_contradiction_does_not_fail_a_batch_that_binds_elsewhere(database):
    """Ticket 04: the Merge Stage refuses a new identity decision that would
    bind or merge *into* a conflicted Company, not every decision in the
    batch. The conflicting reading and an unrelated new Company commit
    together; the conflicted Company waits in review."""
    policy = matching_policy(database)
    unrelated = record("d", cik="0000000005")
    company = _issuer_conflict(database, policy, unrelated)
    after = companies(database)
    assert after[company]["status"] == "review"
    (new,) = [c for c in after.values() if c["entity_id"] != company]
    assert new["identifiers"] == {"cik": ["0000000005"]}


def test_a_company_in_conflict_review_is_not_joined_and_the_batch_commits(database):
    """Ticket 04, suspended identifiers (Q9 read with Q14).

    A contradiction suspends the affected link: a Company in review for an
    authoritative identifier conflict gives a rule no authority to join
    another record to it. That record waits with a review, and the rest of
    the batch commits.
    """
    policy = matching_policy(database)
    company = _issuer_conflict(database, policy)
    assert companies(database)[company]["status"] == "review"
    # A new record carrying the conflicted Company's CIK, beside an unrelated one.
    late = core.source(
        "c", source_code="fixture.secondary", identifiers={"cik": APPLE_CIK}
    )
    unrelated = record("d", cik="0000000005")
    load(database, policy, "b4", late, unrelated, checkpoint=4)
    after = companies(database)
    assert late["subject"] not in after[company]["subjects"]
    (new,) = [c for c in after.values() if c["entity_id"] != company]
    assert new["identifiers"] == {"cik": ["0000000005"]}
    waiting = [r for r in open_reviews(database) if r.get("subject") == late["subject"]]
    assert {r["reason"] for r in waiting} >= {"suspended_identifier"}


def _command(policy, batch, *assertions, consumer=None, as_of=None):
    return {
        "batch_id": batch,
        "run_id": str(uuid4()),
        "policy_digest": policy,
        "consumer": consumer or batch,
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "as_of": as_of or core.AS_OF,
        "assertions": list(assertions),
    }


def test_a_join_is_rechecked_when_another_company_acquires_the_identifier(database):
    """Ticket 04: a join to a stored Company is re-checked under the lock.

    The assessment's snapshot covers the Company itself, not a *different*
    Company acquiring the same CIK meanwhile; only the re-check sees that.
    """
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    joiner = core.source(
        "b", source_code="fixture.secondary", identifiers={"cik": APPLE_CIK}
    )
    late = _command(policy, "late", joiner)
    proposed = stage.propose(**late)
    assert [j["raw"] for j in proposed["joins"]] == [APPLE_CIK]
    prepared = stage.assess(**late, automatic=proposed)
    # Meanwhile a steward gives the same CIK to a second Company.
    other = record("a2", cik=APPLE_CIK)
    identity, bind = core.identity_and_binding(other)
    stage.apply(
        **_command(policy, "steward", other),
        identities=[identity],
        decisions=[bind],
    )
    with pytest.raises(assessment.StaleAssessment):
        stage.apply_assessment(prepared["assessment_id"], run_id=late["run_id"])
    # The retry sees two holders and binds nothing.
    stage.apply(**{**late, "run_id": str(uuid4())})
    assert not any(
        joiner["subject"] in c["subjects"] for c in companies(database).values()
    )
    assert "ambiguous_identifier" in {r["reason"] for r in open_reviews(database)}


def test_an_orphaned_assessment_is_closed_when_its_batch_commits(database):
    """Ticket 04: a crash between assessment and apply leaves no open assessment."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    late = _command(policy, "late", record("a", cik=APPLE_CIK))
    # A run assesses, then crashes before applying.
    orphan = stage.assess(**late, automatic=stage.propose(**late))["assessment_id"]
    # The next run proposes again, with fresh ids, and commits the batch.
    stage.apply(**{**late, "run_id": str(uuid4())})
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE_CIK]}
    with database.application.connect() as conn:
        events = conn.execute(
            text(
                "SELECT event, batch_id FROM mdm_v2.assessment_event "
                "WHERE assessment_id=:a ORDER BY event_id"
            ),
            {"a": orphan},
        ).all()
        still_open = conn.scalar(
            text("""SELECT count(*) FROM mdm_v2.assessment a
            WHERE a.body->>'outcome'='ready' AND NOT EXISTS(
              SELECT 1 FROM mdm_v2.assessment_event e WHERE e.assessment_id=a.assessment_id
              AND e.event IN ('applied','superseded'))""")
        )
    assert [tuple(e) for e in events][-1] == ("superseded", "late")
    assert still_open == 0


def published(database) -> list:
    """Each Company identity's publish time, oldest first."""
    with database.application.connect() as conn:
        return list(
            conn.scalars(
                text(
                    "SELECT published_at FROM mdm_v2.identity "
                    "WHERE kind='company' ORDER BY published_at"
                )
            )
        )


def test_a_late_batch_publishes_its_new_company_after_the_newest(database):
    """Ticket 04: the earliest-published Company survives a merge, so a rule's
    new Company is never published before one already stored. A batch
    delivered late (an older as_of) still creates its Company, published
    just after the newest; reordered delivery keeps working."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (first,) = published(database)
    late = _command(
        policy, "late", record("m", cik="0000789019"), as_of="2026-01-01T00:00:00+00:00"
    )
    stage.apply(**late)
    assert len(companies(database)) == 2
    older, newer = published(database)
    assert older == first and newer > first


def test_a_newer_company_committed_meanwhile_makes_a_proposal_stale(database):
    """Ticket 04: under the lock, a proposal whose new Company would now be
    published at or before a stored one is re-assessed with a fresh time."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    early = _command(
        policy,
        "early",
        record("m", cik="0000789019"),
        as_of="2026-01-01T00:00:00+00:00",
    )
    prepared = stage.assess(**early, automatic=stage.propose(**early))
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    with pytest.raises(assessment.StaleAssessment):
        stage.apply_assessment(prepared["assessment_id"], run_id=early["run_id"])
    stage.apply(**{**early, "run_id": str(uuid4())})
    first, second = published(database)
    assert second > first


def test_the_sql_refuses_a_backdated_new_company_too(database):
    """The same refusal holds in commit_batch (040), past the Python check."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    early = _command(
        policy,
        "early",
        record("m", cik="0000789019"),
        as_of="2026-01-01T00:00:00+00:00",
    )
    key = stage.assess(**early, automatic=stage.propose(**early))["assessment_id"]
    # A later Company commits before the early batch applies.
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    with database.application.connect() as conn:
        effects = conn.scalar(
            text(
                "SELECT body->'effects' FROM mdm_v2.assessment WHERE assessment_id=:k"
            ),
            {"k": key},
        )
        generation = conn.scalar(text("SELECT max(generation) FROM mdm_v2.batch"))
    request = {**effects, "assessment_id": key, "expected_generation": generation}
    with (
        pytest.raises(
            DBAPIError, match="published at or before an identity of its kind"
        ),
        database.application.begin() as conn,
    ):
        conn.execute(
            text("SELECT mdm_v2.commit_batch(:r, CAST(:run AS uuid))"),
            {"r": json.dumps(request), "run": str(uuid4())},
        )


def test_two_runs_at_once_create_one_company_for_one_cik(database):
    """Ticket 04: real threads and separate connections, not an interleaving.

    Both runs are assessed to create a Company for one CIK before either
    applies; the Merge Stage lock lets one create it, and the other, stale,
    re-assesses and joins it.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    policy = matching_policy(database)
    commands = [
        _command(policy, "run-a", record("a", cik=APPLE_CIK)),
        _command(policy, "run-b", record("b", "fixture.secondary", cik=APPLE_CIK)),
    ]
    # b is not the issuer, so only a may create; give b an issuer record too.
    commands[1]["assertions"].append(record("c", cik=APPLE_CIK))
    both_assessed = threading.Barrier(2)

    def run(command):
        stage = MergeStage(Store(database.application))
        prepared = stage.assess(**command, automatic=stage.propose(**command))
        both_assessed.wait(timeout=30)
        try:
            stage.apply_assessment(prepared["assessment_id"], run_id=command["run_id"])
            return "applied"
        except assessment.StaleAssessment:
            stage.apply(**{**command, "run_id": str(uuid4())})
            return "re-assessed"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, c) for c in commands]
        outcomes = {
            c["batch_id"]: f.result(timeout=120) for c, f in zip(commands, futures)
        }
    assert sorted(outcomes.values()) == ["applied", "re-assessed"]
    (only,) = companies(database).values()
    assert only["identifiers"] == {"cik": [APPLE_CIK]}
    assert len(only["subjects"]) == 3


def test_migration_040_applies_to_a_populated_store(postgres):
    """CLAUDE.md: over real rows, in production's order.

    A store at 039 holds a committed Company and an orphaned assessment left
    by a crash. After 040 the Company survives, the next commit of the
    orphan's batch closes it, and a late batch's new Company is published
    after the newest.
    """
    from unittest import mock

    import edgar_warehouse.mdm.clean.store as store_module

    admin, app = postgres
    names = list(store_module.CLEAN_MDM_MIGRATIONS)
    through_039 = tuple(n for n in names if n < "040")
    with mock.patch.object(store_module, "CLEAN_MDM_MIGRATIONS", through_039):
        database = core.initialize_database(admin, app)
        policy = matching_policy(database)
        load(database, policy, "b1", record("a", cik=APPLE_CIK))
        stage = MergeStage(Store(database.application))
        late = _command(policy, "late", record("m", cik="0000789019"))
        orphan = stage.assess(**late, automatic=stage.propose(**late))["assessment_id"]
    core.migrate(admin, application_role="clean_application")
    assert len(companies(database)) == 1
    stage = MergeStage(Store(database.application))
    stage.apply(**{**late, "run_id": str(uuid4())})
    assert len(companies(database)) == 2
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm_v2.assessment_event "
                    "WHERE assessment_id=:a AND event='superseded'"
                ),
                {"a": orphan},
            )
            == 1
        )
    # A batch delivered late still creates its Company, published after the newest.
    stage.apply(
        **_command(
            policy,
            "old",
            record("x", cik="0000000009"),
            as_of="2026-01-01T00:00:00+00:00",
        )
    )
    times = published(database)
    assert len(times) == 3 and times[-1] > times[-2]


def test_a_join_rechecks_every_identifier_that_pointed_at_its_company(database):
    """A join resting on a CIK and an LEI is stale when *either* moves."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (company,) = companies(database)
    gleif = record("g", "fixture.secondary", lei=APPLE_LEI)
    _, link = core.identity_and_binding(gleif, company)
    stage.apply(**_command(policy, "link", gleif), decisions=[link])
    both = record("b", "fixture.secondary", cik=APPLE_CIK, lei=APPLE_LEI)
    late = _command(policy, "late", both)
    proposed = stage.propose(**late)
    assert sorted(j["namespace"] for j in proposed["joins"]) == ["cik", "lei"]
    prepared = stage.assess(**late, automatic=proposed)
    # The CIK, not the LEI, moves: a second Company acquires it.
    other = record("a2", cik=APPLE_CIK)
    identity, bind = core.identity_and_binding(other)
    stage.apply(
        **_command(policy, "steward", other), identities=[identity], decisions=[bind]
    )
    with pytest.raises(assessment.StaleAssessment):
        stage.apply_assessment(prepared["assessment_id"], run_id=late["run_id"])


def test_a_bind_into_a_conflicted_company_is_still_refused(database):
    """Only binds *elsewhere* commit beside a conflict; one into it does not."""
    policy = matching_policy(database)
    company = _issuer_conflict(database, policy)
    joiner = record("j", "fixture.secondary")
    _, bind = core.identity_and_binding(joiner, company)
    with pytest.raises(Conflict, match="unresolved authoritative identifier"):
        MergeStage(Store(database.application)).apply(
            **_command(policy, "into", joiner), decisions=[bind]
        )


def test_new_companies_of_one_batch_share_a_floor_of_their_own_kind(database):
    """The floor reads identities of the new Company's kind only."""
    policy = matching_policy(database)
    stage = MergeStage(Store(database.application))
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (first,) = published(database)
    # A Person identity published far later does not raise the Company floor.
    person = core.source("p", kind="person", fields={"name": "Someone"})
    identity, bind = core.identity_and_binding(person)
    identity["published_at"] = "2030-01-01T00:00:00+00:00"
    stage.apply(
        **_command(policy, "person", person), identities=[identity], decisions=[bind]
    )
    load(
        database,
        policy,
        "b2",
        record("m", cik="0000789019"),
        record("n", cik="0001018724"),
        checkpoint=2,
    )
    _, second, third = published(database)
    assert second == third  # one batch, one publish time
    assert first < second < datetime.fromisoformat("2030-01-01T00:00:00+00:00")


def test_the_earlier_committed_company_survives_a_merge(database):
    """Why the floor exists: after a late batch, the Company committed first is
    still the earliest published, so a default merge keeps its ID."""
    from edgar_warehouse.mdm.clean.evidence import decision
    from edgar_warehouse.mdm.clean.identity import replay

    policy = matching_policy(database)
    load(database, policy, "b1", record("a", cik=APPLE_CIK))
    (first_company,) = companies(database)
    MergeStage(Store(database.application)).apply(
        **_command(
            policy,
            "late",
            record("m", cik="0000789019"),
            as_of="2026-01-01T00:00:00+00:00",
        )
    )
    with database.application.connect() as conn:
        identities = [
            dict(r)
            for r in conn.execute(
                text(
                    "SELECT entity_id::text, kind, published_at::text "
                    "FROM mdm_v2.identity WHERE kind='company'"
                )
            ).mappings()
        ]
    left, right = (i["entity_id"] for i in identities)
    merge = decision(
        "merge",
        actor="steward",
        reason="fixture",
        at=core.AS_OF,
        left=left,
        right=right,
    )
    state = replay(identities, [merge], "2026-12-31T00:00:00+00:00")
    assert state.canonical[left] == state.canonical[right] == first_company
