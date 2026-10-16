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


def relationship(n, valid_to=None):
    return {"object_type": "relationship", "object_id": f"rel-{n}",
            "body": {"relationship_id": f"rel-{n}", "type": "IS_INSIDER", "valid_to": valid_to}}


def test_a_consumer_gets_only_the_records_a_batch_inserted_or_changed(database):
    save(database, 0, [review(1), review(2), relationship(1)])
    first = sent(database, "batch-1")
    assert first["contract_version"] == 3 and first["forced"] is False
    assert [(o["object_id"], o["change"]) for o in first["objects"]] == [
        ("review-1", "insert"), ("review-2", "insert"), ("rel-1", "insert")]
    # A relationship that ends is an update whose body says so (MDM keeps no deletes).
    save(database, 1, [review(1), review(2, "evidence found"), review(3), relationship(1, "2026-10-01")])
    second = sent(database, "batch-2")
    assert [(o["object_id"], o["change"], o["body"].get("reason", o["body"].get("valid_to"))) for o in second["objects"]] == [
        ("review-2", "update", "evidence found"), ("review-3", "insert", "needs evidence"), ("rel-1", "update", "2026-10-01")]
    # The same records again: the batch is committed, and no consumer gets anything.
    result = save(database, 2, [review(1), review(2, "evidence found"), review(3), relationship(1, "2026-10-01")])
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
    save(database, 1, [review(1), review(2), relationship(1)])
    save(database, 2, [review(1), review(2), relationship(1)])  # nothing changed: nothing sent
    assert sent(database, "batch-3") is None
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


def test_a_snapshot_page_reads_only_its_own_records(database):
    """Each page reads its records by their keys: a page late in the snapshot reads
    about a page of rows from each table, not every row before it."""
    from edgar_warehouse.mdm.clean.merge import MergeStage

    records = [core.source(f"c{n:03}", fields={"name": f"Company {n}"}) for n in range(60)]
    pairs = [core.identity_and_binding(r) for r in records]
    MergeStage(Store(database.application)).apply(
        batch_id="companies", run_id=str(uuid4()), policy_digest=database.policy, consumer="fixture",
        expected_checkpoint=0, checkpoint=1, as_of=core.AS_OF, assertions=records,
        identities=[i for i, _ in pairs], decisions=[d for _, d in pairs])
    save(database, 1, [review(n) for n in range(60)])
    with database.admin.connect() as conn:
        ids = sorted(conn.scalars(text("SELECT entity_id::text FROM mdm.company WHERE valid_to IS NULL")))
    with database.admin.begin() as conn:
        conn.execute(text("ANALYZE"))
    reads = text("SELECT relname, coalesce(seq_scan,0), coalesce(idx_tup_fetch,0) FROM pg_stat_xact_user_tables "
                 "WHERE schemaname='mdm' AND relname IN ('company','company_alias','current_record')")
    with database.application.begin() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        before = {r[0]: r[1:] for r in conn.execute(reads)}  # the counters include this backend's earlier work
        conn.scalar(text("SELECT mdm.force_publish('export',CAST(:r AS uuid),1,'entity',:a,5)"),
                    {"r": str(uuid4()), "a": ids[40]})
        after = {r[0]: r[1:] for r in conn.execute(reads)}
    for table, (scans, fetched) in after.items():
        # No table read in full, and at most a page and one more row from each.
        assert scans == before[table][0] and fetched - before[table][1] <= 6, (table, before, after)


def test_a_full_last_page_is_the_last_page(database):
    save(database, 0, [review(n) for n in range(4)])
    first = force(database, str(uuid4()), 1, ("", ""), 4)
    assert first["records"] == 4 and first["next"] is None


def test_a_missing_row_before_018_is_still_refused(database):
    """A batch whose records went out to other consumers has a row for each; one
    missing for a consumer the batch had is refused, not taken as unchanged."""
    save(database, 0, [review(1)])
    with database.admin.begin() as conn:
        conn.execute(text("DELETE FROM mdm.outbox_event WHERE batch_id='batch-1' AND consumer='graph'"))
        conn.execute(text("DELETE FROM mdm.outbox WHERE batch_id='batch-1' AND consumer='graph'"))
    with pytest.raises(ValueError, match="no graph publication"):
        mdm_publish.receipt(Store(database.application), "batch-1", "graph")


def test_a_changed_record_is_read_from_the_projections_expanded_once(database):
    """Ticket 77: outbox_delivery expands a batch's projections once. Reading
    each changed record out of the whole batch document decompressed the
    document once per record (81 of 88 seconds of a 1,000-record save)."""
    with database.admin.connect() as conn:
        view = conn.scalar(text("SELECT pg_get_viewdef('mdm.outbox_delivery'::regclass)"))
    assert "WITH ORDINALITY" in view
    assert "(c.\"position\")::integer - 1" not in view and "c.position::int - 1" not in view
