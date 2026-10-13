"""A batch that changes nothing queues nothing (017; Issue 20 slice 20c).

Merging records MDM already holds, under a new batch and consumer, commits the
batch and the consumer's checkpoint but queues no work for the journal, export
or graph publishers. A batch that changes a record still queues it.
"""
import json
from uuid import uuid4

from sqlalchemy import text

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store
from tests.integration import test_clean_mdm_postgres as core

postgres = core.postgres
database = core.database


def merge(db, batch, consumer, **kw):
    return MergeStage(Store(db.application)).apply(
        batch_id=batch, run_id=str(uuid4()), policy_digest=db.policy, consumer=consumer,
        expected_checkpoint=0, checkpoint=1, as_of=core.AS_OF, **kw)


def outbox(db, batch):
    with db.admin.connect() as conn:
        return sorted(conn.scalars(text("SELECT consumer FROM mdm.outbox WHERE batch_id=:b"), {"b": batch}))


def counts(db):
    with db.admin.connect() as conn:
        return {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in (
            "batch", "source_reading", "decision", "company", "current_record", "checkpoint")}


def test_merging_the_same_company_again_commits_but_queues_nothing(database):
    a = core.source("a", fields={"name": "Acme"})
    identity, bind = core.identity_and_binding(a)
    first = merge(database, "first", "fixture", assertions=[a], identities=[identity], decisions=[bind])
    assert first["changed"] is True and outbox(database, "first")
    before = counts(database)

    again = merge(database, "again", "fixture-again", assertions=[a])
    assert again["changed"] is False and not again["duplicate"]
    assert outbox(database, "again") == []
    # The batch is committed and the new consumer has read past it; nothing else is written.
    assert counts(database) == {**before, "batch": before["batch"] + 1, "checkpoint": before["checkpoint"] + 1}
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.run_batch WHERE batch_id='again'")) == 1


def test_a_batch_that_changes_a_company_is_queued(database):
    a = core.source("a", fields={"name": "Acme"})
    identity, bind = core.identity_and_binding(a)
    merge(database, "first", "fixture", assertions=[a], identities=[identity], decisions=[bind])
    renamed = core.source("a", revision=2, fields={"name": "Acme Holdings"})
    changed = merge(database, "renamed", "fixture-renamed", assertions=[renamed])
    assert changed["changed"] is True and outbox(database, "renamed") == outbox(database, "first")


def test_a_review_written_again_unchanged_keeps_the_batch_that_wrote_it(database):
    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, core.request(database), str(uuid4()))
    with database.application.begin() as conn:
        result = store.commit(conn, core.request(database, batch_id="batch-2", expected_generation=1,
                                                 consumer="other"), str(uuid4()))
    assert result["changed"] is False and outbox(database, "batch-2") == []
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT batch_id FROM mdm.current_record WHERE object_id='review-1'")) == "batch-1"
    with database.application.begin() as conn:
        result = store.commit(conn, core.request(database, batch_id="batch-3", expected_generation=2, consumer="third",
                                                 projections=[{"object_type": "review", "object_id": "review-1",
                                                               "body": {"reason": "evidence found"}}]), str(uuid4()))
    assert result["changed"] is True and outbox(database, "batch-3") == outbox(database, "batch-1")


def test_each_new_lookup_reads_through_an_index(database):
    """The questions write_batch now asks read no table in full: each plan,
    with sequential scans off, names its index. The Company questions are
    record_company_version's own (held by test_clean_lookup_indexes)."""
    lookups = {
        # Is this deferred record new (write_batch)?
        "set_aside_record_pkey": "SELECT 1 FROM mdm.set_aside_record s WHERE s.deferred_id=:id",
        # Is this record the one stored now (write_batch)?
        "current_record_pkey": "SELECT 1 FROM mdm.current_record c WHERE c.object_type='review' "
                               "AND c.object_id=:id AND c.body=CAST(:body AS jsonb)",
        # Did a repeated batch change anything (write_batch, a repeat save)?
        "outbox_pkey": "SELECT 1 FROM mdm.outbox WHERE batch_id=:id",
    }
    records = [core.source(f"c{n}", fields={"name": f"Company {n}"}) for n in range(300)]
    pairs = [core.identity_and_binding(r) for r in records]
    merge(database, "populate", "fixture", assertions=records, identities=[i for i, _ in pairs],
          decisions=[d for _, d in pairs])
    with database.application.begin() as conn:
        Store(database.application).commit(conn, core.request(
            database, batch_id="reviews", expected_generation=1, consumer="reviews",
            projections=[{"object_type": "review", "object_id": f"review-{n}", "body": {"reason": "check"}}
                         for n in range(300)]), str(uuid4()))
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE"))
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        for index, query in lookups.items():
            plan = "\n".join(conn.scalars(text("EXPLAIN " + query), {"id": str(uuid4()), "body": "{}"}))
            assert index in plan and "Seq Scan" not in plan, plan


def test_record_company_version_says_whether_it_wrote(database):
    """It alone decides when a Company is the same; write_batch asks it. The
    changed answer is held by a renamed Company being queued (above)."""
    a = core.source("a", fields={"name": "Acme"})
    identity, bind = core.identity_and_binding(a)
    merge(database, "first", "fixture", assertions=[a], identities=[identity], decisions=[bind])
    with database.admin.begin() as conn:
        body = conn.scalar(text("SELECT body FROM mdm.company WHERE valid_to IS NULL"))
        same = text("SELECT mdm.record_company_version(CAST(:b AS jsonb),'first',now())")
        assert conn.scalar(same, {"b": json.dumps(body, sort_keys=True)}) is False


def test_a_new_deferred_record_alone_is_a_change(database):
    """A batch whose only new row is a set-aside record changed something, but
    no record: change data capture (018) queues only the journal, which sends
    deferred records too; this policy's export and graph get nothing."""
    store = Store(database.application)
    review = {"object_type": "review", "object_id": "deferred-1", "body": {
        "deferred_id": "deferred-1", "open": True, "blocking": True, "retired": False}}
    with database.application.begin() as conn:
        store.commit(conn, core.request(database, projections=[review]), str(uuid4()))
    deferred = {"deferred_id": "deferred-1", "source_code": "fixture.primary", "publication_key": "p1",
                "record_locator": "$[0]", "schema_version": "1", "reason": "needs evidence",
                "raw_record": {}, "provenance": {}}
    with database.application.begin() as conn:
        result = store.commit(conn, core.request(
            database, batch_id="batch-2", expected_generation=1, consumer="other", projections=[review],
            deferred=[deferred], source_accounting={"normalized": 0, "deferred": 1, "total": 1}), str(uuid4()))
    assert result["changed"] is True and outbox(database, "batch-2") == []
    from edgar_warehouse.workers import mdm_publish
    assert json.loads(mdm_publish.receipt(store, "batch-2", "export"))["unchanged"] is True


def test_a_batch_that_changed_nothing_has_nothing_to_publish(database):
    """A publish unit frozen before the merge may name a batch that changed
    nothing: its receipt says there is nothing to publish. A changed batch with
    no row for a consumer, or a batch MDM never committed, is still refused."""
    import pytest

    from edgar_warehouse.workers import mdm_publish

    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, core.request(database), str(uuid4()))
        store.commit(conn, core.request(database, batch_id="batch-2", expected_generation=1, consumer="other"),
                     str(uuid4()))
    assert json.loads(mdm_publish.receipt(store, "batch-2", "export")) == {
        "version": 1, "batch_id": "batch-2", "consumer": "export", "unchanged": True}
    assert mdm_publish.receipt_if_unchanged(store, "batch-1", "export") is None  # queued, not delivered yet
    with pytest.raises(ValueError, match="no audit publication"):
        mdm_publish.receipt(store, "batch-1", "audit")
    with pytest.raises(ValueError, match="no export publication"):
        mdm_publish.receipt(store, "never-committed", "export")
