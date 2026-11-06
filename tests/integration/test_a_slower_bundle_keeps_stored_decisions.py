"""Two bundles overlap: the one started first delivers a record the later one already mastered.

A bundle's `as_of` is fixed when it starts, so a decision stored since can carry
a later time. The batch writes after that decision, so the decision holds.
"""

from __future__ import annotations

from uuid import uuid4

from edgar_warehouse.mdm.merge import MergeStage
from edgar_warehouse.mdm.store import Store
from tests.integration.test_mdm_postgres import AT, bindings, documents, identity_and_binding, source

STARTED_EARLIER = "2025-12-31T23:00:00+00:00"
STARTED_LATER = "2026-01-01T00:00:00+00:00"


def apply(db, n, as_of, **kw):
    return MergeStage(Store(db.application)).apply(
        batch_id=f"work-{n}", run_id=str(uuid4()), policy_digest=db.policy, consumer="fixture",
        expected_checkpoint=n - 1, checkpoint=n, as_of=as_of, **kw,
    )


def test_a_batch_with_an_older_clock_leaves_a_stored_bind_and_its_master_whole(database):
    record = source(effective_at="2025-06-01T00:00:00+00:00")
    identity, bind = identity_and_binding(record)
    assert bind["at"] == AT == STARTED_LATER
    apply(database, 1, STARTED_LATER, assertions=[record], identities=[identity], decisions=[bind])
    before = documents(database, "entity")

    apply(database, 2, STARTED_EARLIER, assertions=[record])

    assert documents(database, "entity") == before
    master = before[0] if isinstance(before, list) else next(iter(before.values()))
    assert master["subjects"] == [record["subject"]]
    assert master["fields"]["name"]["value"] == "Acme"
    assert bindings(database, by_subject=True) == {record["subject"]: identity["entity_id"]}
