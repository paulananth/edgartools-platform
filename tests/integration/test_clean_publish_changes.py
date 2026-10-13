"""mdm.publish as change data capture, and force publish (018; ticket 22).

Operator, 2026-10-13: "MDM publish can implement cdc aka change data capture
only publish what truly changed", "There has to be a force publish to publish
all records" (the current snapshot). Every consumer but the journal gets only
the records a batch inserted or changed; force publish sends every current
record, in pages, marked forced, and changes no master data.
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import payloads
from edgar_warehouse.mdm.clean.store import Store
from edgar_warehouse.workers import mdm_publish
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_outbox_names_batch import Destination, journal_policy

postgres = core.postgres
database = core.database


def review(n, reason="needs evidence"):
    return {"object_type": "review", "object_id": f"review-{n}", "body": {"reason": reason}}


def save(database, generation, projections, **changes):
    with database.application.begin() as conn:
        return Store(database.application).commit(conn, core.request(
            database, batch_id=f"batch-{generation + 1}", expected_generation=generation,
            consumer=f"consumer-{generation + 1}", projections=projections, **changes), str(uuid4()))


def sent(database, batch, consumer="export"):
    """What the publisher sends for that row, checked against the hash MDM kept."""
    with database.application.connect() as conn:
        row = conn.execute(text("SELECT * FROM mdm.outbox_input WHERE batch_id=:b AND consumer=:c"),
                           {"b": batch, "c": consumer}).mappings().first()
    return None if row is None else payloads.prepare(row)


def master_data(database):
    with database.admin.connect() as conn:
        return {t: conn.scalar(text(f"SELECT count(*) FROM mdm.{t}")) for t in (
            "current_record", "company", "company_alias", "decision", "source_reading", "checkpoint")}


def test_a_consumer_gets_only_the_records_a_batch_inserted_or_changed(database):
    save(database, 0, [review(1), review(2)])
    first = sent(database, "batch-1")
    assert first["contract_version"] == 3 and first["forced"] is False
    assert [(o["object_id"], o["change"]) for o in first["objects"]] == [("review-1", "insert"), ("review-2", "insert")]
    save(database, 1, [review(1), review(2, "evidence found"), review(3)])
    second = sent(database, "batch-2")
    assert [(o["object_id"], o["change"], o["body"]) for o in second["objects"]] == [
        ("review-2", "update", {"reason": "evidence found"}), ("review-3", "insert", {"reason": "needs evidence"})]
    # The same records again: the batch is committed, and no consumer gets anything.
    result = save(database, 2, [review(1), review(2, "evidence found"), review(3)])
    assert result["changed"] is False and sent(database, "batch-3") is None
    assert json.loads(mdm_publish.receipt(Store(database.application), "batch-3", "graph"))["unchanged"] is True


def test_the_journal_keeps_the_whole_batch(database):
    policy = journal_policy(database)
    save(database, 0, [review(1), review(2)], policy_digest=policy)
    save(database, 1, [review(1), review(2, "evidence found")], policy_digest=policy)
    journal = sent(database, "batch-2", "journal")
    assert journal["contract_version"] == 2 and [o["object_id"] for o in journal["objects"]] == ["review-1", "review-2"]
    assert [o["object_id"] for o in sent(database, "batch-2")["objects"]] == ["review-2"]


def test_a_delivered_change_publishes_once(database):
    save(database, 0, [review(1)])
    sink, store = Destination(), Store(database.application)
    assert store.deliver_one("export", "worker", sink) and not store.deliver_one("export", "again", sink)
    payload, _ = sink.sent["export/batch-1"]
    assert [o["change"] for o in payload["objects"]] == ["insert"]


def force(database, run, page, after, size):
    with database.application.begin() as conn:
        return conn.scalar(text("SELECT mdm.force_publish(:c,CAST(:r AS uuid),:p,:t,:i,:n)"),
                           {"c": "export", "r": run, "p": page, "t": after[0], "i": after[1], "n": size})


def test_force_publish_sends_every_current_record_in_pages_and_changes_nothing(database):
    a = core.source("a", fields={"name": "Acme"})
    identity, bind = core.identity_and_binding(a)
    from edgar_warehouse.mdm.clean.merge import MergeStage
    MergeStage(Store(database.application)).apply(
        batch_id="company", run_id=str(uuid4()), policy_digest=database.policy, consumer="fixture",
        expected_checkpoint=0, checkpoint=1, as_of=core.AS_OF, assertions=[a], identities=[identity],
        decisions=[bind])
    save(database, 1, [review(1), review(2)])
    save(database, 2, [review(1), review(2)])  # nothing changed: nothing sent
    before = master_data(database)
    run, after, page, pages = str(uuid4()), ("", ""), 1, []
    while True:
        result = force(database, run, page, after, 2)
        pages.append(result)
        if result["next"] is None:
            break
        after, page = (result["next"]["object_type"], result["next"]["object_id"]), page + 1
    objects = [o for p in pages for o in sent(database, p["batch_id"])["objects"]]
    with database.admin.connect() as conn:
        current = conn.execute(text(
            "SELECT object_type,object_id FROM mdm.current_record UNION ALL "
            "SELECT 'entity',entity_id::text FROM mdm.company WHERE valid_to IS NULL ORDER BY 1,2")).all()
    assert [(o["object_type"], o["object_id"]) for o in objects] == [tuple(r) for r in current]
    assert {o["change"] for o in objects} == {"snapshot"}
    assert all(sent(database, p["batch_id"])["forced"] is True for p in pages)
    assert master_data(database) == before
    # A retry of a page returns it unchanged; the journal and an unknown consumer are refused.
    assert force(database, run, 1, ("", ""), 2) == {**pages[0], "duplicate": True}
    for consumer in ("journal", "audit"):
        with database.application.begin() as conn, pytest.raises(DBAPIError, match="journal|does not require"):
            conn.scalar(text("SELECT mdm.force_publish(:c,CAST(:r AS uuid),1,'','',10)"), {"c": consumer, "r": run})
    # The pages deliver through the same claim and verify path as any batch.
    sink, store = Destination(), Store(database.application)
    delivered = 0
    while store.deliver_one("export", "worker", sink):
        delivered += 1
    assert all(f"export/{p['batch_id']}" in sink.sent for p in pages)


def test_rows_queued_before_018_still_send_the_whole_batch(postgres, monkeypatch):
    from edgar_warehouse.mdm.clean import store as module
    from edgar_warehouse.mdm.clean.store import migrate

    admin, app = postgres
    with monkeypatch.context() as patch:
        patch.setattr(module, "MIGRATIONS", module.MIGRATIONS[:module.MIGRATIONS.index("018_publish_changed_records.sql")])
        patch.setattr(module, "RUNTIME_FUNCTIONS", tuple(f for f in module.RUNTIME_FUNCTIONS
                                                       if not f.startswith("force_publish")))
        database = core.initialize_database(admin, app)
    save(database, 0, [review(1), review(2)])
    with database.admin.connect() as conn:
        before = conn.execute(text("SELECT consumer,payload_hash FROM mdm.outbox ORDER BY consumer")).all()
    assert not migrate(database.admin, application_role="clean_application")["installed"]
    with database.admin.connect() as conn:
        assert conn.execute(text("SELECT consumer,payload_hash FROM mdm.outbox ORDER BY consumer")).all() == before
        assert set(conn.scalars(text("SELECT contract_version FROM mdm.outbox"))) == {2}
    old = sent(database, "batch-1")
    assert old["contract_version"] == 2 and [o["object_id"] for o in old["objects"]] == ["review-1", "review-2"]
    save(database, 1, [review(1), review(2, "evidence found")])
    assert [o["object_id"] for o in sent(database, "batch-2")["objects"]] == ["review-2"]


def test_each_change_is_read_by_its_key(database):
    save(database, 0, [review(n) for n in range(300)])
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE"))
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(conn.scalars(text(
            "EXPLAIN SELECT position,change FROM mdm.batch_change WHERE batch_id='batch-1' ORDER BY position")))
        assert "batch_change_pkey" in plan and "Seq Scan" not in plan, plan


def test_the_force_publish_command_writes_the_pages_and_a_publish_manifest(database, tmp_path, monkeypatch, capsys):
    import argparse

    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean import cli

    save(database, 0, [review(n) for n in range(5)])
    monkeypatch.setenv("MDM_DATABASE_URL", database.application.url.render_as_string(hide_password=False))
    monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
    args = argparse.Namespace(consumer="graph", output=str(tmp_path / "forced"), page_size=2, run_id=None,
                              step="graph-publication")
    assert cli.force_publish(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["pages"] == 3 and report["records"] == 5 and report["forced"] is True
    units = Artifacts().json(report["manifest"])["steps"]["graph-publication"]
    assert [u["keys"]["consumer"] for u in units] == ["graph"] * 3
    # The same run again gives the same pages and manifest.
    assert cli.force_publish(argparse.Namespace(**{**vars(args), "run_id": report["run_id"]})) == 0
    assert json.loads(capsys.readouterr().out)["manifest"] == report["manifest"]
