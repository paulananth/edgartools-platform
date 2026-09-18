"""Mandatory PostgreSQL 16 acceptance; prerequisites fail rather than skip."""

from __future__ import annotations

import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean.store import (
    Conflict,
    Store,
    migrate,
    register_dataset,
    register_policy,
)
from edgar_warehouse.mdm.migrations.runtime import _apply_source_registry_migration

IMAGE = "postgres:16-alpine"


def docker(*args, input=None):
    return subprocess.run(
        ["docker", *args], input=input, text=True, capture_output=True, check=True
    ).stdout.strip()


@dataclass
class Database:
    admin: object
    application: object
    policy: str
    registry: str


@pytest.fixture(scope="module")
def postgres():
    docker("image", "inspect", IMAGE)
    name = f"clean-mdm-test-{uuid4().hex[:10]}"
    docker(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-p",
        "127.0.0.1::5432",
        "-e",
        "POSTGRES_PASSWORD=test",
        IMAGE,
    )
    try:
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        admin = create_engine(
            f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres"
        )
        for _ in range(80):
            try:
                with admin.connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except DBAPIError:
                time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL did not become ready")
        with admin.begin() as conn:
            conn.execute(
                text(
                    "CREATE ROLE clean_application LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE"
                )
            )
        _apply_source_registry_migration(admin)
        app = create_engine(
            f"postgresql+psycopg2://clean_application:test@127.0.0.1:{port}/postgres"
        )
        yield admin, app
        app.dispose()
        admin.dispose()
    finally:
        docker("stop", name)


@pytest.fixture
def database(postgres):
    return initialize_database(*postgres)


def initialize_database(admin, app):
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mdm_v2 CASCADE"))
        conn.execute(text("DELETE FROM source_registry_coverage"))
        conn.execute(text("DELETE FROM source_registry_version"))
        version = str(uuid4())
        conn.execute(
            text(
                "INSERT INTO source_registry_version(version_id,status,operator_authorization_reference,activated_at) VALUES(:v,'active','offline-fixture',now())"
            ),
            {"v": version},
        )
        conn.execute(
            text("""INSERT INTO source_registry_coverage(version_id,source_family,coverage_action,acquisition_mode,completeness_policy,discovery_policy,coverage_start_date)
         VALUES(:v,'fixture','carry_forward','fixture','fixture','fixture','2026-01-01')"""),
            {"v": version},
        )
    assert migrate(admin, application_role="clean_application")["installed"]
    assert not migrate(admin, application_role="clean_application")["installed"]
    with admin.begin() as conn:
        policy = register_policy(
            conn,
            {
                "version": 1,
                "required_consumers": ["export", "graph"],
                "automatic_rules": [],
                "fields": {
                    "company": {
                        "name": {"sources": ["fixture.primary", "fixture.secondary"]},
                        "address": {
                            "sources": ["fixture.primary", "fixture.secondary"]
                        },
                    }
                },
            },
        )
        for code in ["fixture.primary", "fixture.secondary"]:
            register_dataset(
                conn,
                code,
                version,
                {
                    "provider": "test",
                    "family": "fixture",
                    "schema_version": "1",
                    "record_key": "key",
                    "publication_key": "version",
                    "effective_time": "effective_at",
                    "semantics": "patch",
                },
            )
    return Database(admin, app, policy, version)


def request(db, **changes):
    return {
        "batch_id": "batch-1",
        "expected_generation": 0,
        "consumer": "mastering/company",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "policy_digest": db.policy,
        "assertions": [],
        "identities": [],
        "decisions": [],
        "projections": [
            {
                "object_type": "review",
                "object_id": "review-1",
                "body": {"reason": "needs evidence"},
            }
        ],
        **changes,
    }


def test_atomic_commit_rollback_and_lost_ack(database):
    store = Store(database.application)
    run = str(uuid4())
    req = request(database)
    with pytest.raises(RuntimeError), database.application.begin() as conn:
        store.commit(conn, req, run)
        raise RuntimeError("process failed before commit")
    with database.application.connect() as conn:
        for table in [
            "batch",
            "projection",
            "publication",
            "checkpoint",
            "observation",
        ]:
            assert conn.scalar(text(f"SELECT count(*) FROM mdm_v2.{table}")) == 0
    with database.application.begin() as conn:
        first = store.commit(conn, req, run)
    another = str(uuid4())
    with database.application.begin() as conn:
        second = store.commit(conn, req, another)
    assert first["generation"] == second["generation"] == 1 and second["duplicate"]
    assert store.run_status(another) == {
        "batches": 1,
        "pending": 2,
        "publication_complete": False,
    }
    with (
        pytest.raises(DBAPIError, match="different content"),
        database.application.begin() as conn,
    ):
        store.commit(conn, {**req, "checkpoint": 2}, run)


def test_checkpoint_and_concurrent_generation_fencing(database):
    store = Store(database.application)

    def commit(key):
        try:
            with database.application.begin() as conn:
                store.commit(conn, request(database, batch_id=key), str(uuid4()))
            return "ok"
        except DBAPIError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(commit, ["a", "b"])) == ["ok", "stale"]
    with (
        pytest.raises(DBAPIError, match="checkpoint"),
        database.application.begin() as conn,
    ):
        store.commit(
            conn,
            request(database, batch_id="c", expected_generation=1),
            str(uuid4()),
        )


def test_permissions_immutable_evidence_and_migration_drift(database, monkeypatch):
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("DELETE FROM mdm_v2.projection"))
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("INSERT INTO mdm_v2.policy VALUES('x','{}')"))
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("CREATE TABLE mdm_v2.bypass(a int)"))
    with pytest.raises(DBAPIError, match="append-only"), database.admin.begin() as conn:
        conn.execute(text("DELETE FROM mdm_v2.policy"))
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda p, *a, **kw: (
            original(p, *a, **kw) + "\n"
            if p.name == "023_clean_mdm.sql"
            else original(p, *a, **kw)
        ),
    )
    with pytest.raises(Conflict, match="checksum"):
        migrate(database.admin, application_role="clean_application")


class Destination:
    def __init__(self):
        self.objects = {}
        self.fail = True

    def publish(self, key, payload, expected_hash):
        previous = self.objects.setdefault(key, (payload, expected_hash))
        assert previous == (payload, expected_hash)
        if self.fail:
            self.fail = False
            raise OSError("external success followed by lost acknowledgement")

    def verify(self, key, payload, expected_hash):
        assert self.objects[key] == (payload, expected_hash)
        return expected_hash


def test_export_and_graph_failure_recovery(database):
    store = Store(database.application)
    run = str(uuid4())
    with database.application.begin() as conn:
        store.commit(conn, request(database), run)
    export = Destination()
    graph = Destination()
    with pytest.raises(OSError):
        store.deliver_one("export", "worker", export)
    assert store.run_status(run)["pending"] == 2
    assert store.deliver_one("export", "worker", export)
    assert store.run_status(run)["pending"] == 1
    with pytest.raises(OSError):
        store.deliver_one("graph", "worker", graph)
    assert not store.run_status(run)["publication_complete"]
    assert store.deliver_one("graph", "worker", graph)
    assert store.run_status(run)["publication_complete"]
    assert not store.deliver_one("graph", "worker", graph)
    assert len(export.objects) == len(graph.objects) == 1


def test_publication_expired_worker_cannot_acknowledge(database):
    store = Store(database.application)
    with database.application.begin() as conn:
        store.commit(conn, request(database), str(uuid4()))
        first = conn.scalar(text("SELECT mdm_v2.claim_publication('export','old',300)"))
    with database.admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE mdm_v2.publication SET lease_until=now()-interval '1 second' WHERE consumer='export'"
            )
        )
    with database.application.begin() as conn:
        second = conn.scalar(
            text("SELECT mdm_v2.claim_publication('export','new',300)")
        )
    assert second["fence"] == first["fence"] + 1
    with (
        pytest.raises(DBAPIError, match="Stale publication fence"),
        database.application.begin() as conn,
    ):
        conn.execute(
            text("SELECT mdm_v2.finish_publication('batch-1','export',:f,:h,NULL)"),
            {"f": first["fence"], "h": first["payload_hash"]},
        )


def test_evidence_delivery_collision_rolls_back_every_effect(database):
    store = Store(database.application)
    run = str(uuid4())
    claim = {
        "assertion_id": "a",
        "source_code": "fixture.primary",
        "schema_version": "1",
        "record_key": "c1",
        "publication_key": "p1",
        "revision": 1,
        "effective_at": "2026-01-01T00:00:00Z",
        "fields": {"name": "Acme"},
    }
    with database.application.begin() as conn:
        store.commit(conn, request(database, assertions=[claim]), run)
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        store.commit(
            conn,
            request(
                database,
                batch_id="b2",
                expected_generation=1,
                expected_checkpoint=1,
                checkpoint=2,
                assertions=[
                    {**claim, "assertion_id": "b", "fields": {"name": "Other"}}
                ],
            ),
            run,
        )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.assertion")) == 1


from edgar_warehouse.mdm.clean.evidence import assertion, decision
from edgar_warehouse.mdm.clean.merge import MergeStage

AS_OF = "2026-09-18T00:00:00+00:00"
AT = "2026-01-01T00:00:00+00:00"


def source(key="c1", source_code="fixture.primary", revision=1, **kw):
    return assertion(
        source_code=source_code,
        record_key=key,
        publication_key=f"p{revision}",
        revision=revision,
        effective_at=AT,
        kind=kw.pop("kind", "company"),
        fields=kw.pop("fields", {"name": "Acme"}),
        **kw,
    )


def identity_and_binding(a, entity_id=None):
    entity_id = entity_id or str(uuid4())
    return {"entity_id": entity_id, "kind": a["kind"], "published_at": AT}, decision(
        "bind",
        actor="steward",
        reason="fixture source reviewed",
        at=AT,
        subject=a["subject"],
        entity_id=entity_id,
        evidence=[a["assertion_id"]],
    )


def apply(db, n, **kw):
    return MergeStage(Store(db.application)).apply(
        batch_id=f"work-{n}",
        run_id=kw.pop("run_id", str(uuid4())),
        policy_digest=db.policy,
        consumer="fixture",
        expected_checkpoint=n - 1,
        checkpoint=n,
        as_of=AS_OF,
        **kw,
    )


def documents(db, kind):
    with db.application.connect() as conn:
        return {
            r[0]: r[1]
            for r in conn.execute(
                text(
                    "SELECT object_id,body FROM mdm_v2.projection WHERE object_type=:kind"
                ),
                {"kind": kind},
            )
        }


def test_reviewed_binding_and_disabled_automatic_matching(database):
    a = source(identifiers={"cik": "1"})
    apply(database, 1, assertions=[a])
    assert not documents(database, "entity")
    assert any(
        v["reason"] == "binding_required" and v["open"]
        for v in documents(database, "review").values()
    )
    entity, bind = identity_and_binding(a)
    apply(database, 2, identities=[entity], decisions=[bind])
    assert (
        documents(database, "entity")[entity["entity_id"]]["fields"]["name"]["value"]
        == "Acme"
    )
    assert all(not r["open"] for r in documents(database, "review").values())
    with (
        database.admin.begin() as conn,
        pytest.raises(ValueError, match="No qualified"),
    ):
        register_policy(
            conn, {"required_consumers": ["export"], "automatic_rules": ["exact"]}
        )


def test_field_selection_reordered_corrections_clear_retract_and_provenance(database):
    a = source(fields={"name": "Primary", "address": {"street": "1 Main", "city": "A"}})
    b = source(
        source_code="fixture.secondary",
        fields={"name": "Secondary", "address": {"street": "2 Side", "city": "B"}},
    )
    entity, bind = identity_and_binding(a)
    _, bind_b = identity_and_binding(b, entity["entity_id"])
    apply(database, 1, assertions=[b, a], identities=[entity], decisions=[bind, bind_b])
    fields = documents(database, "entity")[entity["entity_id"]]["fields"]
    assert (
        fields["name"]["value"] == "Primary"
        and fields["name"]["conflicts"][0]["source_code"] == "fixture.secondary"
    )
    assert fields["address"]["value"] == {"street": "1 Main", "city": "A"}
    latest = source(revision=3, fields={"name": "Corrected"})
    older = source(revision=2, fields={"name": "Outdated"})
    apply(database, 2, assertions=[latest])
    apply(database, 3, assertions=[older])
    assert (
        documents(database, "entity")[entity["entity_id"]]["fields"]["name"]["value"]
        == "Corrected"
    )
    apply(database, 4, assertions=[source(revision=4, fields={"name": None})])
    assert (
        documents(database, "entity")[entity["entity_id"]]["fields"]["name"]["value"]
        == "Corrected"
    )
    apply(
        database, 5, assertions=[source(revision=5, fields={"name": {"op": "retract"}})]
    )
    assert (
        documents(database, "entity")[entity["entity_id"]]["fields"]["name"]["value"]
        == "Secondary"
    )


def test_incompatible_kinds_and_authoritative_conflicts_block_merge(database):
    a = source("a", identifiers={"cik": "1"})
    b = source("b", identifiers={"cik": "2"})
    i, da = identity_and_binding(a)
    j, db = identity_and_binding(b)
    apply(database, 1, assertions=[a, b], identities=[i, j], decisions=[da, db])
    merge = decision(
        "merge",
        actor="reviewer",
        reason="duplicate proposal",
        at="2026-02-01T00:00:00Z",
        left=i["entity_id"],
        right=j["entity_id"],
    )
    with pytest.raises(Conflict, match="authoritative"):
        apply(database, 2, decisions=[merge])
    c = source("p", kind="person")
    k, dc = identity_and_binding(c)
    apply(database, 2, assertions=[c], identities=[k], decisions=[dc])
    bad = decision(
        "merge",
        actor="reviewer",
        reason="bad proposal",
        at="2026-02-01T00:00:00Z",
        left=i["entity_id"],
        right=k["entity_id"],
    )
    with pytest.raises(Conflict, match="Incompatible"):
        apply(database, 3, decisions=[bad])


def test_merge_alias_reversal_preserves_later_evidence_and_exclusion(database):
    a = source("a", fields={"name": "First"})
    b = source("b", fields={"name": "Second"})
    i, da = identity_and_binding(a)
    j, db = identity_and_binding(b)
    j["published_at"] = "2026-01-02T00:00:00Z"
    apply(database, 1, assertions=[a, b], identities=[i, j], decisions=[da, db])
    merge = decision(
        "merge",
        actor="reviewer",
        reason="reviewed match",
        at="2026-02-01T00:00:00Z",
        left=i["entity_id"],
        right=j["entity_id"],
    )
    apply(database, 2, decisions=[merge])
    assert (
        documents(database, "entity")[j["entity_id"]]["canonical_id"] == i["entity_id"]
    )
    apply(
        database,
        3,
        assertions=[source("b", revision=2, fields={"name": "Later correction"})],
    )
    reverse = decision(
        "reverse",
        actor="reviewer",
        reason="separate entities proven",
        at="2026-03-01T00:00:00Z",
        target=merge["decision_id"],
    )
    apply(database, 4, decisions=[reverse])
    entities = documents(database, "entity")
    assert entities[i["entity_id"]]["fields"]["name"]["value"] == "First"
    assert entities[j["entity_id"]]["fields"]["name"]["value"] == "Later correction"
    repeated = decision(
        "merge",
        actor="reviewer",
        reason="same old evidence",
        at="2026-04-01T00:00:00Z",
        left=i["entity_id"],
        right=j["entity_id"],
    )
    with pytest.raises(Conflict, match="Exclusion"):
        apply(database, 5, decisions=[repeated])


def test_override_without_expiry_persists_and_disagreement_opens_review(database):
    a = source()
    i, bind = identity_and_binding(a)
    override = decision(
        "override",
        actor="reviewer",
        reason="verified correction",
        at="2026-02-01T00:00:00Z",
        subject=a["subject"],
        field="name",
        value="Steward name",
        evidence=[a["assertion_id"]],
    )
    apply(database, 1, assertions=[a], identities=[i], decisions=[bind, override])
    apply(database, 2, assertions=[source(revision=2, fields={"name": "Disagreement"})])
    assert (
        documents(database, "entity")[i["entity_id"]]["fields"]["name"]["value"]
        == "Steward name"
    )
    assert any(
        v["reason"] == "override_source_disagreement"
        for v in documents(database, "review").values()
    )
    revoke = decision(
        "revoke",
        actor="reviewer",
        reason="source correction now valid",
        at="2026-03-01T00:00:00Z",
        target=override["decision_id"],
    )
    apply(database, 3, decisions=[revoke])
    assert (
        documents(database, "entity")[i["entity_id"]]["fields"]["name"]["value"]
        == "Disagreement"
    )


def test_issuer_links_reproject_through_merge_and_reverse(database):
    a = source("a")
    b = source("b")
    instrument = source(
        "instrument",
        kind="security",
        relationships=[
            {"type": "ISSUED_BY", "target_subject": b["subject"], "valid_from": AT}
        ],
    )
    i, da = identity_and_binding(a)
    j, db = identity_and_binding(b)
    k, dk = identity_and_binding(instrument)
    apply(
        database,
        1,
        assertions=[a, b, instrument],
        identities=[i, j, k],
        decisions=[da, db, dk],
    )
    merge = decision(
        "merge",
        actor="reviewer",
        reason="reviewed",
        at="2026-02-01T00:00:00Z",
        left=i["entity_id"],
        right=j["entity_id"],
        survivor=i["entity_id"],
    )
    apply(database, 2, decisions=[merge])
    active = [
        e for e in documents(database, "relationship").values() if not e.get("retired")
    ]
    assert len(active) == 1 and active[0]["target_id"] == i["entity_id"]
    reverse = decision(
        "reverse",
        actor="reviewer",
        reason="wrong merge",
        at="2026-03-01T00:00:00Z",
        target=merge["decision_id"],
    )
    apply(database, 3, decisions=[reverse])
    active = [
        e for e in documents(database, "relationship").values() if not e.get("retired")
    ]
    assert len(active) == 1 and active[0]["target_id"] == j["entity_id"]


def test_hierarchy_cycles_invalid_intervals_and_parent_conflicts(database):
    a = source("a")
    b = source("b")
    c = source("c")
    a = source(
        "a",
        relationships=[
            {
                "type": "ACCOUNTING_PARENT",
                "target_subject": b["subject"],
                "valid_from": AT,
            }
        ],
    )
    b = source(
        "b",
        relationships=[
            {
                "type": "ACCOUNTING_PARENT",
                "target_subject": a["subject"],
                "valid_from": AT,
            }
        ],
    )
    c = source(
        "c",
        relationships=[
            {
                "type": "ACCOUNTING_PARENT",
                "target_subject": a["subject"],
                "valid_from": AT,
                "valid_to": "2025-01-01T00:00:00Z",
            }
        ],
    )
    pairs = [identity_and_binding(x) for x in [a, b, c]]
    apply(
        database,
        1,
        assertions=[a, b, c],
        identities=[i for i, d in pairs],
        decisions=[d for i, d in pairs],
    )
    assert not documents(database, "relationship")
    reasons = {r["reason"] for r in documents(database, "review").values()}
    assert {"hierarchy_cycle", "invalid_relationship_interval"} <= reasons


def test_dependent_merge_prevents_partial_reversal(database):
    sources = [source(x) for x in ["a", "b", "c"]]
    pairs = [identity_and_binding(x) for x in sources]
    apply(
        database,
        1,
        assertions=sources,
        identities=[i for i, d in pairs],
        decisions=[d for i, d in pairs],
    )
    ids = [i["entity_id"] for i, d in pairs]
    first = decision(
        "merge",
        actor="reviewer",
        reason="first",
        at="2026-02-01T00:00:00Z",
        left=ids[0],
        right=ids[1],
        survivor=ids[0],
    )
    apply(database, 2, decisions=[first])
    second = decision(
        "merge",
        actor="reviewer",
        reason="dependent",
        at="2026-03-01T00:00:00Z",
        left=ids[0],
        right=ids[2],
        survivor=ids[0],
        depends_on=[first["decision_id"]],
    )
    apply(database, 3, decisions=[second])
    reverse = decision(
        "reverse",
        actor="reviewer",
        reason="first was wrong",
        at="2026-04-01T00:00:00Z",
        target=first["decision_id"],
    )
    with pytest.raises(Conflict, match="Dependent merge"):
        apply(database, 4, decisions=[reverse])
    assert documents(database, "entity")[ids[2]]["canonical_id"] == ids[0]


def test_source_retirement_recomputes_from_remaining_evidence(database):
    a = source(fields={"name": "Primary"})
    b = source(source_code="fixture.secondary", fields={"name": "Secondary"})
    entity, first = identity_and_binding(a)
    _, second = identity_and_binding(b, entity["entity_id"])
    apply(
        database, 1, assertions=[a, b], identities=[entity], decisions=[first, second]
    )
    retirement = decision(
        "retire_source",
        actor="operator",
        reason="dataset withdrawn",
        at="2026-02-01T00:00:00Z",
        source_code="fixture.primary",
        evidence=["source-owner-withdrawal"],
    )
    apply(database, 2, decisions=[retirement])
    assert (
        documents(database, "entity")[entity["entity_id"]]["fields"]["name"]["value"]
        == "Secondary"
    )


def test_mirror_and_bookkeeping_across_three_real_databases(database):
    from edgar_warehouse.bookkeeping.models import PipelineRun
    from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
    from edgar_warehouse.mdm.clean.publication import JournalMirror, migrate_mirror

    # Existing bookkeeping schema is not redesigned. This fixture creates its
    # existing ORM table only; Clean MDM migrations above always use real SQL.
    suffix = uuid4().hex[:10]
    ledger_name = f"ledger_{suffix}"
    book_name = f"book_{suffix}"
    with database.admin.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {ledger_name}")
        conn.exec_driver_sql(f"CREATE DATABASE {book_name}")
    ledger_admin = create_engine(database.admin.url.set(database=ledger_name))
    ledger_app = create_engine(database.application.url.set(database=ledger_name))
    book = create_engine(database.admin.url.set(database=book_name))
    try:
        migrate_mirror(ledger_admin, application_role="clean_application")
        PipelineRun.__table__.create(book)
        with database.admin.begin() as conn:
            policy = register_policy(
                conn,
                {
                    "version": 1,
                    "required_consumers": ["journal"],
                    "automatic_rules": [],
                },
            )
        run = str(uuid4())
        store = Store(database.application)
        coordinator = RunCoordinator(book, store)
        coordinator.start(run, ["batch-1"], manifest_digest="frozen-input")
        with database.application.begin() as conn:
            store.commit(
                conn, request(database, policy_digest=policy, projections=[]), run
            )
        assert not coordinator.reconcile(run)["end_to_end_complete"]
        mirror = JournalMirror(ledger_app)
        original = mirror.publish

        def lose_ack(key, payload, h):
            original(key, payload, h)
            raise OSError("mirror committed but acknowledgement was lost")

        mirror.publish = lose_ack
        with pytest.raises(OSError):
            store.deliver_one("journal", "worker", mirror)
        assert not coordinator.reconcile(run)["end_to_end_complete"]
        mirror.publish = original
        assert store.deliver_one("journal", "worker", mirror)
        assert coordinator.reconcile(run)["end_to_end_complete"]
        assert coordinator.reconcile(run)["end_to_end_complete"]
        with ledger_app.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm_mirror.event")) == 1
            assert str(conn.scalar(text("SELECT run_id FROM mdm_mirror.event"))) == run
        with book.connect() as conn:
            assert conn.scalar(text("SELECT status FROM pipeline_run")) == "succeeded"
    finally:
        ledger_admin.dispose()
        ledger_app.dispose()
        book.dispose()
        with database.admin.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            conn.exec_driver_sql(f"DROP DATABASE {ledger_name}")
            conn.exec_driver_sql(f"DROP DATABASE {book_name}")


def test_authorized_clear_blocks_fallback_and_unknown_time_is_retained(database):
    with database.admin.begin() as conn:
        database.policy = register_policy(
            conn,
            {
                "version": 2,
                "required_consumers": ["export"],
                "automatic_rules": [],
                "fields": {
                    "company": {
                        "name": {
                            "sources": ["fixture.primary", "fixture.secondary"],
                            "clear_sources": ["fixture.primary"],
                        }
                    }
                },
            },
        )
    a = source()
    b = source(source_code="fixture.secondary", fields={"name": "Fallback"})
    entity, first = identity_and_binding(a)
    _, second = identity_and_binding(b, entity["entity_id"])
    apply(
        database, 1, assertions=[a, b], identities=[entity], decisions=[first, second]
    )
    apply(
        database, 2, assertions=[source(revision=2, fields={"name": {"op": "clear"}})]
    )
    winner = documents(database, "entity")[entity["entity_id"]]["fields"]["name"]
    assert winner["cleared"] and winner["value"] is None
    unknown = assertion(
        source_code="fixture.primary",
        record_key="unknown",
        publication_key="p1",
        revision=1,
        effective_at=None,
        kind="company",
        fields={"name": "Unknown effective date"},
    )
    apply(database, 3, assertions=[unknown])
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text(
                    "SELECT effective_at FROM mdm_v2.assertion WHERE assertion_id=:id"
                ),
                {"id": unknown["assertion_id"]},
            )
            is None
        )


def test_company_and_person_role_profiles_and_field_provenance(database):
    with database.admin.begin() as conn:
        database.policy = register_policy(
            conn,
            {
                "version": 2,
                "required_consumers": ["export"],
                "automatic_rules": [],
                "fields": {
                    "company": {
                        "name": {"sources": ["fixture.primary", "fixture.secondary"]}
                    }
                },
                "profile_fields": {
                    "adviser": {
                        "aum": {"sources": ["fixture.primary", "fixture.secondary"]}
                    }
                },
            },
        )
    adviser = {
        "role": "adviser",
        "authority": "IAPD",
        "registration": "123",
        "valid_from": AT,
        "fields": {"aum": "1000"},
    }
    audit = {
        "role": "audit_firm",
        "authority": "PCAOB",
        "registration": "456",
        "valid_from": AT,
    }
    a = source(profiles=[adviser, audit])
    b = source(
        source_code="fixture.secondary",
        profiles=[{**adviser, "fields": {"aum": "900"}}],
    )
    entity, first = identity_and_binding(a)
    _, second = identity_and_binding(b, entity["entity_id"])
    apply(
        database, 1, assertions=[a, b], identities=[entity], decisions=[first, second]
    )
    profiles = documents(database, "entity")[entity["entity_id"]]["profiles"]
    assert {p["role"] for p in profiles} == {"adviser", "audit_firm"}
    field = next(p for p in profiles if p["role"] == "adviser")["fields"]["aum"]
    assert (
        field["value"] == "1000"
        and field["winner"]["assertion_id"] == a["assertion_id"]
    )
    assert field["conflicts"][0]["value"] == "900"
    person = source("person", kind="person", profiles=[adviser, audit])
    pid, bind = identity_and_binding(person)
    apply(database, 2, assertions=[person], identities=[pid], decisions=[bind])
    assert [
        p["role"] for p in documents(database, "entity")[pid["entity_id"]]["profiles"]
    ] == ["adviser"]
    assert any(
        r["reason"] == "incompatible_profile"
        for r in documents(database, "review").values()
    )
    apply(
        database,
        3,
        assertions=[
            source(revision=2, profiles=[{**adviser, "fields": {"aum": None}}, audit])
        ],
    )
    selected = next(
        p
        for p in documents(database, "entity")[entity["entity_id"]]["profiles"]
        if p["role"] == "adviser"
    )["fields"]["aum"]
    assert selected["value"] == "1000"
    assert selected["winner"]["assertion_id"] == a["assertion_id"]
    apply(
        database,
        4,
        assertions=[
            source(
                revision=3,
                profiles=[{**adviser, "fields": {"aum": {"op": "retract"}}}, audit],
            )
        ],
    )
    selected = next(
        p
        for p in documents(database, "entity")[entity["entity_id"]]["profiles"]
        if p["role"] == "adviser"
    )["fields"]["aum"]
    assert selected["value"] == "900"
    assert selected["winner"]["assertion_id"] == b["assertion_id"]


def test_versioned_representative_fixture_and_alias_read_contract(database):
    from edgar_warehouse.mdm.clean.cli import batch_assertions, read_manifest
    from edgar_warehouse.mdm.clean.consumer import ContractReader

    fixture = Path(__file__).parents[1] / "fixtures" / "clean_mdm" / "v1"
    manifest, _, root = read_manifest(str(fixture / "manifest.json"))
    with database.admin.begin() as conn:
        assert (
            register_policy(conn, json.loads((fixture / "policy.json").read_text()))
            == manifest["policy_digest"]
        )
        register_dataset(
            conn,
            "fixture.representative",
            database.registry,
            json.loads((fixture / "dataset.json").read_text()),
        )
    store = Store(database.application)
    batch = manifest["batches"][0]
    evidence = batch_assertions(batch, root, store)
    MergeStage(store).apply(
        batch_id=batch["batch_id"],
        run_id=str(uuid4()),
        policy_digest=manifest["policy_digest"],
        consumer=batch["consumer"],
        expected_checkpoint=0,
        checkpoint=1,
        as_of=manifest["as_of"],
        assertions=evidence,
        identities=batch["identities"],
        decisions=batch["decisions"],
    )
    entities = documents(database, "entity")
    assert len(entities) == 10
    assert len({e["kind"] for e in entities.values()}) == 8
    assert len(documents(database, "relationship")) == 7
    assert not documents(database, "review")
    manager = next(
        e
        for e in entities.values()
        if e["fields"]["name"]["value"] == "Synthetic 13F Manager"
    )
    assert manager["profiles"] == []
    read = ContractReader(database.application).entity(manager["entity_id"])
    assert read["contract_version"] == 2
    assert (
        read["field_provenance"]["name"]["evidence"]["provenance"]["artifact_sha256"]
        == batch["input"]["sha256"]
    )
    # Identical business output after a duplicate delivery in a different root run.
    again = MergeStage(store).apply(
        batch_id=batch["batch_id"],
        run_id=str(uuid4()),
        policy_digest=manifest["policy_digest"],
        consumer=batch["consumer"],
        expected_checkpoint=0,
        checkpoint=1,
        as_of=manifest["as_of"],
        assertions=list(reversed(evidence)),
        identities=list(reversed(batch["identities"])),
        decisions=list(reversed(batch["decisions"])),
    )
    assert again["duplicate"] and documents(database, "entity") == entities


@pytest.fixture
def command_databases(database, monkeypatch):
    from edgar_warehouse.bookkeeping.models import PipelineRun
    from edgar_warehouse.mdm.clean.publication import migrate_mirror

    names = [f"clean_{kind}_{uuid4().hex[:10]}" for kind in ("book", "ledger")]
    with database.admin.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        for name in names:
            conn.exec_driver_sql(f"CREATE DATABASE {name}")
    book, ledger = [
        create_engine(database.admin.url.set(database=name)) for name in names
    ]
    try:
        PipelineRun.__table__.create(book)
        with book.begin() as conn:
            conn.execute(
                text("GRANT SELECT,INSERT,UPDATE ON pipeline_run TO clean_application")
            )
        migrate_mirror(ledger, application_role="clean_application")
        monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
        for key, engine in [
            ("MDM_DATABASE_URL", database.admin),
            ("BOOKKEEPING_DATABASE_URL", book),
            ("CHANGE_LEDGER_DATABASE_URL", ledger),
        ]:
            monkeypatch.setenv(key, engine.url.render_as_string(hide_password=False))
        yield book, ledger
    finally:
        book.dispose()
        ledger.dispose()
        with database.admin.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            for name in names:
                conn.exec_driver_sql(f"DROP DATABASE {name}")


def test_commands_resume_bounded_work_and_reconcile_all_consumers(
    database, command_databases, tmp_path, capsys
):
    import argparse

    from edgar_warehouse.mdm.cli import register_mdm_subparser

    parser = argparse.ArgumentParser()
    register_mdm_subparser(parser.add_subparsers())
    run = str(uuid4())

    def command(*args):
        parsed = parser.parse_args(["mdm", *args])
        return parsed.handler(parsed)

    with database.admin.begin() as conn:
        policy = register_policy(
            conn,
            {
                "version": 3,
                "automatic_rules": [],
                "required_consumers": ["export", "graph", "journal"],
                "fields": {"company": {"name": {"sources": ["fixture.primary"]}}},
            },
        )
    batches = []
    for n in range(3):
        a = source(f"command-{n}")
        entity, bind = identity_and_binding(a)
        batches.append(
            {
                "batch_id": f"command-{n}",
                "stage": "mastering" if n < 2 else "derive-relationships",
                "consumer": "fixture",
                "expected_checkpoint": n,
                "checkpoint": n + 1,
                "assertions": [a],
                "identities": [entity],
                "decisions": [bind],
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": 2,
                "policy_digest": policy,
                "as_of": AS_OF,
                "batches": batches,
            }
        )
    )
    common = ("--model", "clean", "--run-id", run)
    work = (*common, "--manifest", str(manifest), "--limit", "1")
    with pytest.raises(Conflict, match="preceding"):
        command("derive-relationships", *work)
    assert command("mastering", *work) == 0
    assert len(documents(database, "entity")) == 1
    assert command("mastering", *work) == 0
    assert len(documents(database, "entity")) == 2
    assert command("mastering", *work) == 0
    assert len(documents(database, "entity")) == 2
    assert command("reconcile", *common) == 2
    assert command("derive-relationships", *work) == 0
    assert command("publication-status", *common) == 2
    for consumer in ["export", "graph", "journal"]:
        assert (
            command(
                "publish",
                *common,
                "--consumer",
                consumer,
                "--contract-output",
                str(tmp_path / "published"),
                "--limit",
                "3",
            )
            == 0
        )
    assert command("reconcile", *common) == 0
    assert command("counts", "--model", "clean") == 0
    book, ledger = command_databases
    with book.connect() as conn:
        assert conn.scalar(text("SELECT status FROM pipeline_run")) == "succeeded"
    with ledger.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_mirror.event")) == 3
    # A stale success cannot survive reconciliation of unexpected committed work.
    apply(database, 4, run_id=run, assertions=[source("unexpected")])
    assert command("reconcile", *common) == 2
    with book.connect() as conn:
        assert conn.scalar(text("SELECT status FROM pipeline_run")) == "running"
        assert conn.scalar(text("SELECT completed_at FROM pipeline_run")) is None


def test_manifest_rejects_insufficient_or_zero_limit(
    database, command_databases, tmp_path
):
    from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator
    from edgar_warehouse.mdm.clean.cli import execute_manifest

    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "contract_version": 2,
                "policy_digest": database.policy,
                "as_of": AS_OF,
                "batches": [
                    {
                        "batch_id": "large",
                        "stage": "mastering",
                        "consumer": "fixture",
                        "expected_checkpoint": 0,
                        "checkpoint": 1,
                        "assertions": [source("one"), source("two")],
                    }
                ],
            }
        )
    )
    for limit, message in [(0, "1..1000"), (1, "at least 2")]:
        with pytest.raises(ValueError, match=message):
            execute_manifest(
                store,
                coordinator,
                path=str(manifest),
                run_id=str(uuid4()),
                stage="mastering",
                limit=limit,
            )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 0


def test_fresh_replay_preserves_business_results_across_batching_and_order(postgres):
    from edgar_warehouse.mdm.clean.consumer import ContractReader

    first = source("stable", fields={"name": "Initial"})
    secondary = source(
        "second", source_code="fixture.secondary", fields={"name": "Alternative"}
    )
    correction = source("stable", revision=2, fields={"name": "Corrected"})
    entity, bind = identity_and_binding(first)
    _, bind_second = identity_and_binding(secondary, entity["entity_id"])
    expected = None
    for chunks in [
        [[first, secondary, correction]],
        [[first], [secondary], [correction]],
        [[correction], [secondary], [first]],
    ]:
        db = initialize_database(*postgres)
        for n, chunk in enumerate(chunks, 1):
            # Retained steward evidence may arrive after a source correction.
            apply(db, n, assertions=chunk)
        apply(db, len(chunks) + 1, identities=[entity], decisions=[bind, bind_second])
        business = documents(db, "entity")
        assert all(not r["open"] for r in documents(db, "review").values())
        assert (
            ContractReader(db.application).entity(entity["entity_id"])["identity"]
            == business[entity["entity_id"]]
        )
        if expected is None:
            expected = business
        else:
            assert business == expected


def test_oversized_closure_rolls_back_every_effect(database):
    a = source()
    entity, bind = identity_and_binding(a)
    apply(database, 1, assertions=[a], identities=[entity], decisions=[bind])
    before = documents(database, "entity")
    with pytest.raises(Conflict, match="closure exceeds"):
        MergeStage(Store(database.application), closure_limit=1).apply(
            batch_id="too-large",
            run_id=str(uuid4()),
            policy_digest=database.policy,
            consumer="fixture",
            expected_checkpoint=1,
            checkpoint=2,
            as_of=AS_OF,
            assertions=[source(revision=2, fields={"name": "Changed"})],
        )
    assert documents(database, "entity") == before
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.assertion")) == 1


def test_retirement_closes_unbound_source_reviews(database):
    apply(database, 1, assertions=[source()])
    assert any(r["open"] for r in documents(database, "review").values())
    apply(
        database,
        2,
        decisions=[
            decision(
                "retire_source",
                actor="operator",
                reason="withdrawn",
                at="2026-02-01T00:00:00Z",
                source_code="fixture.primary",
                evidence=["withdrawal"],
            )
        ],
    )
    assert all(not r["open"] for r in documents(database, "review").values())


def test_conflicting_corrections_are_order_independent_and_history_survives(postgres):
    from edgar_warehouse.mdm.clean.consumer import ContractReader

    a = source("one", identifiers={"cik": "1"})
    b = source("two", identifiers={"cik": "1"})
    entity, first = identity_and_binding(a)
    _, second = identity_and_binding(b, entity["entity_id"])
    corrections = [
        source("one", revision=2, identifiers={"cik": "2"}, fields={"name": "Changed"}),
        source("two", revision=2, identifiers={"cik": "3"}),
    ]
    expected = None
    for ordered in [corrections, list(reversed(corrections))]:
        db = initialize_database(*postgres)
        apply(db, 1, assertions=[a, b], identities=[entity], decisions=[first, second])
        for n, correction in enumerate(ordered, 2):
            apply(db, n, assertions=[correction])
        current = documents(db, "entity")
        assert current[entity["entity_id"]]["status"] == "review"
        assert current[entity["entity_id"]]["fields"] == {}
        history = ContractReader(db.application).entity(
            entity["entity_id"], generation=1
        )
        assert history["identity"]["status"] == "accepted"
        assert history["identity"]["fields"]["name"]["value"] == "Acme"
        if expected is None:
            expected = current
        else:
            assert current == expected


def test_reversal_preview_rolls_back_and_matches_committed_replay(database):
    a, b = source("left"), source("right")
    left, bind_left = identity_and_binding(a)
    right, bind_right = identity_and_binding(b)
    apply(
        database,
        1,
        assertions=[a, b],
        identities=[left, right],
        decisions=[bind_left, bind_right],
    )
    merge = decision(
        "merge",
        actor="steward",
        reason="reviewed",
        at="2026-02-01T00:00:00Z",
        left=left["entity_id"],
        right=right["entity_id"],
    )
    apply(database, 2, decisions=[merge])
    before = documents(database, "entity")
    reverse = decision(
        "reverse",
        actor="steward",
        reason="separate legal persons",
        at="2026-03-01T00:00:00Z",
        target=merge["decision_id"],
    )
    preview = apply(database, 3, decisions=[reverse], preview=True)
    assert preview["preview"]
    assert documents(database, "entity") == before
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.publication")) == 4
        assert (
            conn.scalar(
                text("SELECT position FROM mdm_v2.checkpoint WHERE consumer='fixture'")
            )
            == 2
        )
    apply(database, 3, decisions=[reverse])
    expected = {
        p["object_id"]: p["body"]
        for p in preview["effects"]["projections"]
        if p["object_type"] == "entity"
    }
    assert documents(database, "entity") == expected


def test_attempt_history_retains_lost_ack_and_does_not_duplicate_effect(
    database, command_databases
):
    from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator

    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    run = str(uuid4())
    coordinator.start(run, ["work-1"], manifest_digest="attempt-test")
    a = source()
    entity, bind = identity_and_binding(a)

    def commit():
        return apply(
            database,
            1,
            run_id=run,
            assertions=[a],
            identities=[entity],
            decisions=[bind],
        )

    def lost_ack():
        commit()
        raise OSError("process lost commit acknowledgement")

    with pytest.raises(OSError):
        coordinator.execute(run, "work-1", lost_ack)
    assert coordinator.execute(run, "work-1", commit)["duplicate"]
    report = coordinator.reconcile(run)
    assert report["attempt_events"] == {"started": 2, "finished": 1, "error": 1}
    assert report["observed_batches"] == 1
    assert not report["end_to_end_complete"]
    publisher = Destination()
    publisher.fail = False
    for name in ["export", "graph"]:
        assert store.deliver_one(name, "worker", publisher)
    assert coordinator.reconcile(run)["end_to_end_complete"]
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("DELETE FROM mdm_v2.attempt_event"))
    with pytest.raises(DBAPIError, match="append-only"), database.admin.begin() as conn:
        conn.execute(text("DELETE FROM mdm_v2.attempt_event"))


def test_review_resolution_requires_its_later_publication_receipts(
    database, command_databases
):
    from edgar_warehouse.mdm.clean.bookkeeping import RunCoordinator

    store = Store(database.application)
    coordinator = RunCoordinator(command_databases[0], store)
    run = str(uuid4())
    coordinator.start(run, ["work-1"], manifest_digest="review-resolution")
    a = source()
    apply(database, 1, run_id=run, assertions=[a])
    sink = Destination()
    sink.fail = False
    for consumer in ["export", "graph"]:
        store.deliver_one(consumer, "worker", sink)
    assert coordinator.reconcile(run)["unresolved_reviews"] == 1
    entity, bind = identity_and_binding(a)
    apply(database, 2, identities=[entity], decisions=[bind])
    report = coordinator.reconcile(run)
    assert report["unresolved_reviews"] == 0
    assert report["pending_publications"] == 2
    assert not report["end_to_end_complete"]
    for consumer in ["export", "graph"]:
        store.deliver_one(consumer, "worker", sink)
    assert coordinator.reconcile(run)["end_to_end_complete"]


def test_temporal_parents_separate_ownership_reported_and_calculated(database):
    a, b, c = source("child"), source("parent-one"), source("parent-two")

    def edge(kind, target, start=AT, end=None):
        return {
            "type": kind,
            "target_subject": target["subject"],
            "valid_from": start,
            "valid_to": end,
            "scope": "consolidated",
        }

    ownership = [edge("OWNERSHIP_PARENT", b), edge("OWNERSHIP_PARENT", c)]
    reported = edge("REPORTED_ULTIMATE_PARENT", b)
    initial = source(
        "child",
        relationships=[
            *ownership,
            reported,
            edge("ACCOUNTING_PARENT", b),
            edge("ACCOUNTING_PARENT", c),
        ],
    )
    pairs = [identity_and_binding(x) for x in [initial, b, c]]
    apply(
        database,
        1,
        assertions=[initial, b, c],
        identities=[i for i, _ in pairs],
        decisions=[d for _, d in pairs],
    )
    active = [
        e for e in documents(database, "relationship").values() if not e.get("retired")
    ]
    assert [e["type"] for e in active].count("OWNERSHIP_PARENT") == 2
    assert not any(
        e["type"] in {"ACCOUNTING_PARENT", "CALCULATED_ULTIMATE_PARENT"} for e in active
    )
    assert any(
        r["reason"] == "conflicting_accounting_parents" and r["open"]
        for r in documents(database, "review").values()
    )
    boundary = "2026-02-01T00:00:00Z"
    correction = source(
        "child",
        revision=2,
        relationships=[
            *ownership,
            reported,
            edge("ACCOUNTING_PARENT", b, end=boundary),
            edge("ACCOUNTING_PARENT", c, start=boundary),
        ],
    )
    reverse_direction = source(
        "parent-one",
        revision=2,
        relationships=[edge("ACCOUNTING_PARENT", a, start=boundary)],
    )
    apply(database, 2, assertions=[correction, reverse_direction])
    active = [
        e for e in documents(database, "relationship").values() if not e.get("retired")
    ]
    assert not any(r["open"] for r in documents(database, "review").values())
    assert any(
        e["type"] == "REPORTED_ULTIMATE_PARENT"
        and not e["derived"]
        and e["target_id"] == pairs[1][0]["entity_id"]
        for e in active
    )
    derived = [e for e in active if e["type"] == "CALCULATED_ULTIMATE_PARENT"]
    assert len(derived) == 2
    assert all(
        e["derived"] and e["target_id"] == pairs[2][0]["entity_id"] and e["path"]
        for e in derived
    )


def test_version_two_api_auth_history_pagination_and_profile_provenance(
    database, monkeypatch
):
    from fastapi.testclient import TestClient

    from edgar_warehouse.mdm.api import auth
    from edgar_warehouse.mdm.api.main import create_app
    from edgar_warehouse.mdm.api.routers.clean import get_reader
    from edgar_warehouse.mdm.clean.consumer import ContractReader

    monkeypatch.delenv("MDM_ENABLE_V2_API", raising=False)
    assert not any(r.path.startswith("/api/v2/") for r in create_app().routes)
    monkeypatch.setenv("MDM_ENABLE_V2_API", "1")
    monkeypatch.setattr(auth, "_SECRET_CACHE", {"offline-test-key"})
    with database.admin.begin() as conn:
        database.policy = register_policy(
            conn,
            {
                "version": 3,
                "automatic_rules": [],
                "required_consumers": ["export", "graph"],
                "fields": {"company": {"name": {"sources": ["fixture.primary"]}}},
                "profile_fields": {
                    "adviser": {"aum": {"sources": ["fixture.primary"]}}
                },
            },
        )
    profile = {
        "role": "adviser",
        "authority": "IAPD",
        "registration": "123",
        "valid_from": AT,
        "fields": {"aum": "1000"},
    }
    a = source("api-one", profiles=[profile])
    b = source("api-two")
    left, first = identity_and_binding(a, "10000000-0000-4000-8000-000000000001")
    right, second = identity_and_binding(b, "20000000-0000-4000-8000-000000000002")
    apply(
        database,
        1,
        assertions=[a, b],
        identities=[left, right],
        decisions=[first, second],
    )
    app = create_app()
    app.dependency_overrides[get_reader] = lambda: ContractReader(database.application)
    with TestClient(app) as client:
        endpoint = f"/api/v2/mdm/entities/{left['entity_id']}"
        assert client.get(endpoint).status_code == 401
        client.headers["X-API-Key"] = "offline-test-key"
        body = client.get(endpoint).json()
        assert body["projection"]["as_of"] == AS_OF
        assert body["projection"]["generation"] == 1
        assert body["projection"]["policy_digest"] == database.policy
        assert (
            body["contract_version"] == 2 and body["canonical_id"] == left["entity_id"]
        )
        profile_id = body["identity"]["profiles"][0]["profile_id"]
        assert (
            body["profile_field_provenance"][profile_id]["aum"]["evidence"][
                "assertion_id"
            ]
            == a["assertion_id"]
        )
        first_page = client.get("/api/v2/mdm/objects/entity?limit=1").json()
        assert (
            first_page["generation"] == 1
            and first_page["next_after"] == left["entity_id"]
        )
        apply(
            database,
            2,
            assertions=[source("api-two", revision=2, fields={"name": "Changed"})],
        )
        second_page = client.get(
            "/api/v2/mdm/objects/entity",
            params={"limit": 1, "generation": 1, "after": first_page["next_after"]},
        ).json()
        assert second_page["next_after"] is None
        assert second_page["items"][0]["body"]["fields"]["name"]["value"] == "Acme"
        assert client.get(endpoint + "?generation=999").status_code == 404
        assert client.get("/api/v2/mdm/objects/entity?limit=1001").status_code == 422
        merge = decision(
            "merge",
            actor="steward",
            reason="reviewed",
            at="2026-02-01T00:00:00Z",
            left=left["entity_id"],
            right=right["entity_id"],
        )
        apply(database, 3, decisions=[merge])
        alias_endpoint = f"/api/v2/mdm/entities/{right['entity_id']}"
        assert client.get(alias_endpoint).json()["canonical_id"] == left["entity_id"]
        assert (
            client.get(alias_endpoint + "?generation=1").json()["canonical_id"]
            == right["entity_id"]
        )
