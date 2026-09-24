"""Real PG16: the activation check at registration and again per batch."""

from __future__ import annotations

import copy
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import (
    Conflict,
    Store,
    canonical,
    digest,
    register_policy,
)
from tests.integration import test_clean_mdm_postgres as core
from tests.mdm.test_clean_activation import RULE, entry, policy, proof

postgres = core.postgres
database = core.database


def test_a_rule_version_cannot_be_reused_for_different_steps(database):
    """§10 check 9, against what the store already holds."""
    with database.admin.begin() as conn:
        register_policy(conn, policy())
    edited = copy.deepcopy(RULE)
    edited["steps"][0]["when"][0]["args"]["values"] = ["operating", "other"]
    with (
        database.admin.begin() as conn,
        pytest.raises(Conflict, match="company/sec-company@2026-09-24"),
    ):
        register_policy(conn, policy(rules=[edited]))
    edited["version"] = "2026-09-25"
    with database.admin.begin() as conn:
        register_policy(conn, policy(rules=[edited]))


def test_an_activated_policy_registers_and_merges(database):
    with database.admin.begin() as conn:
        key = register_policy(conn, policy(automatic=[entry()]))
    result = MergeStage(Store(database.application)).apply(
        batch_id="activated-policy",
        run_id=str(uuid4()),
        policy_digest=key,
        consumer="activation-test",
        expected_checkpoint=0,
        checkpoint=1,
        as_of=core.AS_OF,
    )
    assert result == {
        "batch_id": "activated-policy",
        "duplicate": False,
        "generation": 1,
    }


def test_a_body_that_bypassed_registration_is_refused_per_batch(database):
    """An owner-inserted body with a proof that does not reproduce never merges."""
    body = policy(automatic=[entry(proof=proof(lower_bound=0.9999))])
    key = digest(body)
    with database.admin.begin() as conn:
        conn.execute(
            text("INSERT INTO mdm_v2.policy VALUES(:k,CAST(:b AS jsonb))"),
            {"k": key, "b": canonical(body)},
        )
    with pytest.raises(Conflict, match="does not reproduce"):
        MergeStage(Store(database.application)).apply(
            batch_id="bypassed-policy",
            run_id=str(uuid4()),
            policy_digest=key,
            consumer="activation-test",
            expected_checkpoint=0,
            checkpoint=1,
            as_of=core.AS_OF,
        )
