"""Real PG16: correcting a wrong SEC-to-GLEIF link (company mastering ticket 13).

A name rule binds a GLEIF record to the Company its SEC record holds. When
the rule is found wrong, its version stops being switched on, and a
correction batch revokes every standing bind it made (`correction.py`). The
Stage clears the record's binding in the same transaction (migration 041),
the Company's dated row closes and a row without GLEIF's values opens, and
the record waits, or binds again under an approved rule. The same rule
version never relinks that pair.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import correction
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Conflict, Store
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_name_matching import (
    APPLE_CIK,
    APPLE_LEI,
    POSTCODE_RULE,
    STATE_RULE,
    companies,
    gleif,
    load,
    name_policy,
    sec,
)

postgres = core.postgres
database = core.database
AT = "2026-09-19T00:00:00+00:00"  # after the fixture loads (core.AS_OF)


def policy_body(database, digest):
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT body FROM mdm_v2.policy WHERE digest=:d"), {"d": digest})


def correct(database, policy, batch, checkpoint, *, extra=()):
    """The correction batch a rerun makes: revoke each stale bind."""
    body = policy_body(database, policy)
    with database.application.connect() as conn:
        stale = correction.stale_bindings(conn, body, limit=100)
        revocations = [
            correction.revocation(conn, b, policy_digest=policy, actor="operator",
                                  reason=f"rule {b['rule_id']}@{b['rule_version']} is no longer switched on", at=AT)
            for b in stale
        ]
    decisions = revocations + list(extra)
    MergeStage(Store(database.application)).apply(
        batch_id=batch, run_id=str(uuid4()), policy_digest=policy, consumer="load",
        expected_checkpoint=checkpoint - 1, checkpoint=checkpoint, as_of=AT, decisions=decisions,
    )
    return decisions


def stage_entity(database, subject):
    with database.application.connect() as conn:
        return conn.scalar(text("SELECT entity_id::text FROM mdm_v2.stage_record WHERE subject=:s"), {"s": subject})


def versions(database, entity):
    with database.application.connect() as conn:
        return [dict(r) for r in conn.execute(text(
            "SELECT lei, jurisdiction, valid_to IS NULL AS current FROM mdm_v2.company "
            "WHERE entity_id=CAST(:e AS uuid) ORDER BY from_generation"), {"e": entity}).mappings()]


def linked(database, names=(STATE_RULE, POSTCODE_RULE)):
    wrong = name_policy(database, names=names)
    load(database, wrong, "sec", sec())
    load(database, wrong, "gleif", gleif(), checkpoint=2)
    (company,) = companies(database)
    assert company["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}
    return wrong, company["entity_id"]


def test_a_wrong_link_is_revoked_and_the_record_waits(database):
    _wrong, entity = linked(database)
    fixed = name_policy(database, active=False)  # the rule is found wrong
    (revocation,) = correct(database, fixed, "correct", 3)
    assert revocation["rule_id"] in {STATE_RULE["rule_id"], POSTCODE_RULE["rule_id"]}
    assert revocation["policy"] == fixed and revocation["subject"] == gleif()["subject"]
    (company,) = companies(database)
    assert company["identifiers"] == {"cik": [APPLE_CIK]}
    assert stage_entity(database, gleif()["subject"]) is None
    # SEC alone, then joined by GLEIF; the joined row closed and one without
    # GLEIF's values opened.
    rows = versions(database, entity)
    assert [r["lei"] for r in rows] == [None, APPLE_LEI, None]
    assert [r["current"] for r in rows] == [False, False, True]


def test_a_rerun_finds_nothing_left_to_correct(database):
    _wrong, _entity = linked(database)
    fixed = name_policy(database, active=False)
    correct(database, fixed, "correct", 3)
    assert correct(database, fixed, "correct-again", 4) == []


def test_the_same_rule_version_never_relinks_the_pair(database):
    # Only the rule that made the link: another approved rule may relink.
    wrong, _entity = linked(database, names=(STATE_RULE,))
    correct(database, name_policy(database, active=False), "correct", 3)
    # The wrong rule is switched on again and the record arrives again, after
    # the correction (a batch replays the journal as of its own date).
    MergeStage(Store(database.application)).apply(
        batch_id="gleif-again", run_id=str(uuid4()), policy_digest=wrong, consumer="load",
        expected_checkpoint=3, checkpoint=4, as_of="2026-09-20T00:00:00+00:00", assertions=[gleif()],
    )
    (company,) = companies(database)
    assert company["identifiers"] == {"cik": [APPLE_CIK]}
    assert stage_entity(database, gleif()["subject"]) is None


def test_a_new_rule_version_binds_the_record_again_in_the_same_batch(database):
    _wrong, entity = linked(database)
    renewed = [{**rule, "version": "2026-09-30.1"} for rule in (STATE_RULE, POSTCODE_RULE)]
    fixed = name_policy(database, names=renewed)
    (_revocation,) = correct(database, fixed, "correct", 3)
    (company,) = companies(database)
    assert company["identifiers"] == {"cik": [APPLE_CIK], "lei": [APPLE_LEI]}
    assert stage_entity(database, gleif()["subject"]) == entity
    with database.application.connect() as conn:
        binds = [r[0] for r in conn.execute(text(
            "SELECT body->>'rule_version' FROM mdm_v2.decision WHERE operation='bind' "
            "AND body->>'subject'=:s ORDER BY body->>'at'"), {"s": gleif()["subject"]})]
    assert binds[-1] == "2026-09-30.1"


def test_a_correction_delivered_twice_changes_nothing(database):
    _wrong, entity = linked(database)
    fixed = name_policy(database, active=False)
    decisions = correct(database, fixed, "correct", 3)
    MergeStage(Store(database.application)).apply(
        batch_id="correct", run_id=str(uuid4()), policy_digest=fixed, consumer="load",
        expected_checkpoint=2, checkpoint=3, as_of=AT, decisions=decisions,
    )
    assert len(versions(database, entity)) == 3


def test_a_bind_revoked_twice_is_refused(database):
    _wrong, _entity = linked(database)
    fixed = name_policy(database, active=False)
    (first,) = correct(database, fixed, "correct", 3)
    with database.application.connect() as conn:
        (bind,) = [r[0] for r in conn.execute(text(
            "SELECT body FROM mdm_v2.decision WHERE decision_id=:d"), {"d": first["target"]})]
        second = correction.revocation(conn, bind, policy_digest=fixed, actor="operator",
                                       reason="revoked again", at="2026-09-20T00:00:00+00:00")
    with pytest.raises((Conflict, DBAPIError), match="already revoked"):
        MergeStage(Store(database.application)).apply(
            batch_id="twice", run_id=str(uuid4()), policy_digest=fixed, consumer="load",
            expected_checkpoint=3, checkpoint=4, as_of="2026-09-20T00:00:00+00:00", decisions=[second],
        )
