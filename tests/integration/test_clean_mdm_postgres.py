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
    register_policy,
)
from tests.support.rules_authority import register_dataset

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
    port = None
    try:
        port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
        admin = create_engine(
            f"postgresql+psycopg2://postgres:test@127.0.0.1:{port}/postgres"
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
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
        app = create_engine(
            f"postgresql+psycopg2://clean_application:test@127.0.0.1:{port}/postgres"
        )
        yield admin, app
        app.dispose()
        admin.dispose()
    finally:
        docker("stop", name)
        # The next module's container may be given the same port.
        if port:
            _templates.pop(int(port), None)


# Each module's first test migrates a template database once (checking a
# second migration installs nothing); every test then gets its own copy of
# it, which Postgres makes in well under a second. Migrating per test cost
# about 3.4 seconds each (company mastering ticket 23).
TEMPLATE = "clean_template"
_templates: dict[int, tuple[str, str]] = {}


def _template(admin, app) -> tuple[str, str]:
    port = admin.url.port
    if port not in _templates:
        with admin.execution_options(isolation_level="AUTOCOMMIT").connect() as conn:
            conn.execute(text(f"CREATE DATABASE {TEMPLATE}"))
        admin_t = create_engine(admin.url.set(database=TEMPLATE))
        app_t = create_engine(app.url.set(database=TEMPLATE))
        try:
            built = initialize_database(admin_t, app_t)
        finally:
            # A template is copied only while nobody is connected to it.
            admin_t.dispose()
            app_t.dispose()
        _templates[port] = (built.policy, built.registry)
    return _templates[port]


@pytest.fixture
def database(postgres):
    admin, app = postgres
    policy, registry = _template(admin, app)
    name = f"clean_{uuid4().hex[:12]}"
    server = admin.execution_options(isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {name} TEMPLATE {TEMPLATE}"))
    admin_db = create_engine(admin.url.set(database=name))
    app_db = create_engine(app.url.set(database=name))
    try:
        yield Database(admin_db, app_db, policy, registry)
    finally:
        admin_db.dispose()
        app_db.dispose()
        with server.connect() as conn:
            conn.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))


def initialize_database(admin, app):
    with admin.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS mdm CASCADE"))
        version = str(uuid4())
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
                    "publication_families": ["golden_copy", "opencorporates"],
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
            "current_record",
            "outbox",
            "checkpoint",
            "run_batch",
        ]:
            assert conn.scalar(text(f"SELECT count(*) FROM mdm.{table}")) == 0
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
        conn.execute(text("DELETE FROM mdm.current_record"))
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("INSERT INTO mdm.policy VALUES('x','{}')"))
    with pytest.raises(DBAPIError), database.application.begin() as conn:
        conn.execute(text("CREATE TABLE mdm.bypass(a int)"))
    with pytest.raises(DBAPIError, match="append-only"), database.admin.begin() as conn:
        conn.execute(text("DELETE FROM mdm.policy"))
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda p, *a, **kw: (
            original(p, *a, **kw) + "\n"
            if p.name == "001_mdm.sql"
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
        first = conn.scalar(text("SELECT mdm.claim_outbox('export','old',300)"))
    with database.admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE mdm.outbox SET lease_until=now()-interval '1 second' WHERE consumer='export'"
            )
        )
    with database.application.begin() as conn:
        second = conn.scalar(
            text("SELECT mdm.claim_outbox('export','new',300)")
        )
    assert second["fence"] == first["fence"] + 1
    with (
        pytest.raises(DBAPIError, match="Stale publication fence"),
        database.application.begin() as conn,
    ):
        conn.execute(
            text("SELECT mdm.finish_outbox('batch-1','export',:f,:h,NULL)"),
            {"f": first["fence"], "h": first["payload_hash"]},
        )


def test_evidence_delivery_collision_rolls_back_every_effect(database):
    store = Store(database.application)
    run = str(uuid4())
    claim = {
        "assertion_id": "a",
        "source_code": "fixture.primary",
        "schema_version": "1",
        # Every stored reading names its kind and subject; the latest-only
        # Stage keys on them (ticket 10).
        "kind": "company",
        "subject": "c1-subject",
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
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.source_reading")) == 1


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
    """Current objects of one type. Entities come from `current_entity`,
    which holds the Companies (ticket 17); the rest from `projection`."""
    query = (
        "SELECT object_id,body FROM mdm.current_entity"
        if kind == "entity"
        else "SELECT object_id,body FROM mdm.current_record WHERE object_type=:kind"
    )
    with db.application.connect() as conn:
        return {r[0]: r[1] for r in conn.execute(text(query), {"kind": kind})}


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
        pytest.raises(ValueError, match="must be an object naming a rule"),
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
                    "SELECT effective_at FROM mdm.source_reading WHERE assertion_id=:id"
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
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.source_reading")) == 1


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
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm.outbox")) == 4
        assert (
            conn.scalar(
                text("SELECT position FROM mdm.checkpoint WHERE consumer='fixture'")
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


def assessment_command(db, **changes):
    a = source()
    identity, binding = identity_and_binding(a)
    return {
        "batch_id": "assessed-company",
        "run_id": str(uuid4()),
        "policy_digest": db.policy,
        "consumer": "assessed-company",
        "expected_checkpoint": 0,
        "checkpoint": 1,
        "as_of": AS_OF,
        "assertions": [a],
        "identities": [identity],
        "decisions": [binding],
        **changes,
    }


def test_identity_assessment_is_durable_before_master_and_resumes(database):
    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    prepared = stage.assess(**command)
    assert prepared["before"] == []
    # A new connection sees the assessment but no master/checkpoint/outbox.
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.match_proposal")) == 1
        for table in (
            "batch",
            "source_reading",
            "master_entity",
            "decision",
            "current_record",
            "checkpoint",
            "outbox",
        ):
            assert conn.scalar(text(f"SELECT count(*) FROM mdm.{table}")) == 0
    assert stage.assess(**command)["assessment_id"] == prepared["assessment_id"]
    result = stage.apply_assessment(prepared["assessment_id"], run_id=command["run_id"])
    assert result["generation"] == 1
    duplicate = stage.apply(**{**command, "run_id": str(uuid4())})
    assert duplicate["duplicate"]
    with database.application.connect() as conn:
        events = (
            conn.execute(
                text("SELECT event FROM mdm.match_proposal_event ORDER BY event_id")
            )
            .scalars()
            .all()
        )
        assert events == ["ready", "observed", "applied"]
        assert (
            conn.scalar(text("SELECT effects->>'assessment_id' FROM mdm.batch"))
            == prepared["assessment_id"]
        )
    stage.apply(
        **{
            **command,
            "batch_id": "fields-only",
            "expected_checkpoint": 1,
            "checkpoint": 2,
            "identities": [],
            "decisions": [],
            "assertions": [source(revision=2, fields={"name": "New name"})],
        }
    )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.match_proposal")) == 1


def test_assessment_stale_dependency_and_unrelated_progress(database):
    from edgar_warehouse.mdm.clean.assessment import StaleAssessment

    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    candidate = stage.assess(**command)
    apply(database, 1, assertions=[source("unrelated")])
    # Global generation changed; the assessed Company and its checkpoint did not.
    assert (
        stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])[
            "generation"
        ]
        == 2
    )
    b = source(source_code="fixture.secondary")
    _, bind_b = identity_and_binding(b, command["identities"][0]["entity_id"])
    next_command = {
        **command,
        "batch_id": "link-second",
        "expected_checkpoint": 1,
        "checkpoint": 2,
        "identities": [],
        "assertions": [b],
        "decisions": [bind_b],
    }
    candidate = stage.assess(**next_command)
    assert any(
        p["object_type"] == "entity" and p["body"]["fields"]["name"]["value"] == "Acme"
        for p in candidate["before"]
    )
    apply(database, 2, assertions=[source(revision=2, fields={"name": "Corrected"})])
    with pytest.raises(StaleAssessment):
        stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text("SELECT count(*) FROM mdm.batch WHERE batch_id='link-second'")
            )
            == 0
        )
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.match_proposal_event WHERE event='superseded'"
                )
            )
            == 1
        )
    refreshed = stage.assess(**next_command)
    assert refreshed["assessment_id"] != candidate["assessment_id"]
    stage.apply_assessment(refreshed["assessment_id"], run_id=command["run_id"])


def test_rejected_identity_proposal_retains_veto_without_master_change(database):
    a, b = source("a", identifiers={"cik": "1"}), source("b", identifiers={"cik": "2"})
    i, da = identity_and_binding(a)
    j, db = identity_and_binding(b)
    apply(database, 1, assertions=[a, b], identities=[i, j], decisions=[da, db])
    merge = decision(
        "merge",
        actor="steward",
        reason="candidate",
        at=AS_OF,
        left=i["entity_id"],
        right=j["entity_id"],
    )
    before = documents(database, "entity")
    with pytest.raises(Conflict, match="authoritative"):
        apply(database, 2, decisions=[merge])
    with database.application.connect() as conn:
        rejected = conn.execute(
            text(
                "SELECT assessment_id,body FROM mdm.match_proposal WHERE body->>'outcome'='rejected'"
            )
        ).one()
        assert rejected[1]["command"]["decisions"] == [merge]
        assert "authoritative" in rejected[1]["vetoes"][0]
        assert set(rejected[1]["retained"]["assertion_ids"]) == {
            a["assertion_id"],
            b["assertion_id"],
        }
    with pytest.raises(Conflict, match="Rejected"):
        MergeStage(Store(database.application)).apply_assessment(
            rejected[0], run_id=str(uuid4())
        )
    assert documents(database, "entity") == before


def test_assessment_application_failure_rolls_back_applied_event(database, monkeypatch):
    store = Store(database.application)
    stage = MergeStage(store)
    command = assessment_command(database)
    candidate = stage.assess(**command)
    commit = store.commit

    def fail_after_sql(*args, **kwargs):
        commit(*args, **kwargs)
        raise RuntimeError("crash before transaction commit")

    monkeypatch.setattr(store, "commit", fail_after_sql)
    with pytest.raises(RuntimeError, match="crash"):
        stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.match_proposal_event WHERE event='applied'"
                )
            )
            == 0
        )
        assert conn.scalar(text("SELECT count(*) FROM mdm.match_proposal")) == 1
    monkeypatch.setattr(store, "commit", commit)
    stage.apply_assessment(candidate["assessment_id"], run_id=command["run_id"])


def test_assessment_sql_fences_bypass_stale_and_modified_effects(database):
    from edgar_warehouse.mdm.clean.store import canonical

    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    candidate = stage.assess(**command)
    effects = {**candidate["effects"], "expected_generation": 0}
    with (
        pytest.raises(DBAPIError, match="ready assessment"),
        database.application.begin() as conn,
    ):
        stage.store.commit(conn, effects, command["run_id"])
    assessed = {**effects, "assessment_id": candidate["assessment_id"]}
    with (
        pytest.raises(DBAPIError, match="differs from assessed"),
        database.application.begin() as conn,
    ):
        stage.store.commit(conn, {**assessed, "projections": []}, command["run_id"])
    # The capability requires a previously committed assessment, even for the
    # privileged runtime API; staging plus application in one txn is rejected.
    body = {k: v for k, v in candidate.items() if k != "assessment_id"}
    body["rule_version"] = "same-transaction-test"
    with (
        pytest.raises(DBAPIError, match="ready assessment"),
        database.application.begin() as conn,
    ):
        key = conn.scalar(
            text("SELECT mdm.record_match_proposal(:body,CAST(:run AS uuid))"),
            {"body": canonical(body), "run": command["run_id"]},
        )
        stage.store.commit(conn, {**effects, "assessment_id": key}, command["run_id"])
    apply(database, 1, assertions=[source(revision=2)])
    with (
        pytest.raises(DBAPIError, match="Stale identity assessment"),
        database.application.begin() as conn,
    ):
        stage.store.commit(
            conn, {**assessed, "expected_generation": 1}, command["run_id"]
        )


def test_preview_capability_cannot_commit_or_leak_assessments(database):
    from edgar_warehouse.mdm.clean.store import canonical

    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    preview = stage.apply(**command, preview=True)
    # Commit the caller transaction deliberately: SQL preview still persists none.
    with database.application.begin() as conn:
        conn.execute(
            text("SELECT mdm.preview_batch(:body,CAST(:run AS uuid))"),
            {"body": canonical(preview["effects"]), "run": command["run_id"]},
        )
    with database.application.connect() as conn:
        for table in (
            "batch",
            "match_proposal",
            "match_proposal_event",
            "master_entity",
            "checkpoint",
            "outbox",
        ):
            assert conn.scalar(text(f"SELECT count(*) FROM mdm.{table}")) == 0
    for function in ("write_batch",):
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            database.application.begin() as conn,
        ):
            conn.execute(
                text(f"SELECT mdm.{function}('{{}}',CAST(:run AS uuid))"),
                {"run": command["run_id"]},
            )


def test_assessment_history_permissions_and_concurrent_lost_ack(database):
    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    prepared = stage.assess(**command)

    def deliver(_):
        return stage.apply_assessment(prepared["assessment_id"], run_id=str(uuid4()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, range(2)))
    assert sorted(r["duplicate"] for r in results) == [False, True]
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.match_proposal_event WHERE event='applied'"
                )
            )
            == 1
        )
    for table in ("match_proposal", "match_proposal_event"):
        with (
            pytest.raises(DBAPIError, match="permission denied"),
            database.application.begin() as conn,
        ):
            conn.execute(text(f"DELETE FROM mdm.{table}"))
        with (
            pytest.raises(DBAPIError, match="append-only"),
            database.admin.begin() as conn,
        ):
            conn.execute(text(f"DELETE FROM mdm.{table}"))


def test_automatic_progression_reassesses_a_concurrent_correction(
    database, monkeypatch
):
    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    original = stage.apply_assessment
    raced = False

    def race_once(key, *, run_id):
        nonlocal raced
        if not raced:
            raced = True
            apply(
                database, 1, assertions=[source(revision=2, fields={"name": "Current"})]
            )
        return original(key, run_id=run_id)

    monkeypatch.setattr(stage, "apply_assessment", race_once)
    result = stage.apply(**command)
    assert result["generation"] == 2
    entity = command["identities"][0]["entity_id"]
    assert documents(database, "entity")[entity]["fields"]["name"]["value"] == "Current"
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.match_proposal")) == 2
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.match_proposal_event WHERE event='superseded'"
                )
            )
            == 1
        )
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.match_proposal_event WHERE event='applied'"
                )
            )
            == 1
        )


def test_assessment_resume_uses_timezone_independent_dependency_snapshot(database):
    stage = MergeStage(Store(database.application))
    command = assessment_command(database)
    stage.apply(**command)
    b = source(source_code="fixture.secondary")
    _, bind_b = identity_and_binding(b, command["identities"][0]["entity_id"])
    prepared = stage.assess(
        **{
            **command,
            "batch_id": "second-timezone",
            "expected_checkpoint": 1,
            "checkpoint": 2,
            "identities": [],
            "assertions": [b],
            "decisions": [bind_b],
        }
    )
    other = create_engine(
        database.application.url,
        connect_args={"options": "-c timezone=America/New_York"},
    )
    try:
        result = MergeStage(Store(other)).apply_assessment(
            prepared["assessment_id"], run_id=command["run_id"]
        )
        assert result["generation"] == 2
    finally:
        other.dispose()


def family_metadata(family, publication="p1"):
    # Synthetic proof checks persistence/fencing, not live source completeness.
    return {
        "source_family": "fixture",
        "publication_family": family,
        "committed_publication": publication,
        "continuity_proof": {"rule_version": "fixture-1", "inventory_digest": "a" * 64},
    }


def test_family_checkpoints_isolate_progress_and_atomic_failure(database):
    stage = MergeStage(Store(database.application))
    first = assessment_command(database, **family_metadata("golden_copy"))
    candidate = stage.assess(**first)
    other = {
        **first,
        **family_metadata("opencorporates"),
        "batch_id": "mapping",
        "assertions": [],
        "identities": [],
        "decisions": [],
    }
    stage.apply(**other)
    # Same consumer, independent family: staged Golden Copy remains usable.
    stage.apply_assessment(candidate["assessment_id"], run_id=first["run_id"])
    with database.application.connect() as conn:
        state = conn.execute(
            text(
                "SELECT publication_family,position,committed_publication,continuity_proof FROM mdm.checkpoint ORDER BY publication_family"
            )
        ).all()
        assert [(r[0], r[1], r[2]) for r in state] == [
            ("golden_copy", 1, "p1"),
            ("opencorporates", 1, "p1"),
        ]
        assert all(r[3] == first["continuity_proof"] for r in state)
    with pytest.raises(DBAPIError, match="checkpoint"):
        stage.apply(**{**other, "batch_id": "stale-mapping", "checkpoint": 2})
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
        assert conn.execute(
            text("SELECT position FROM mdm.checkpoint ORDER BY publication_family")
        ).scalars().all() == [1, 1]
    stage.apply(
        **{
            **other,
            **family_metadata("opencorporates", "p2"),
            "batch_id": "mapping-2",
            "expected_checkpoint": 1,
            "checkpoint": 2,
        }
    )
    with database.application.connect() as conn:
        assert conn.execute(
            text("SELECT position FROM mdm.checkpoint ORDER BY publication_family")
        ).scalars().all() == [1, 2]
    assert stage.apply(**other)["duplicate"]


def test_family_checkpoint_keeps_legacy_cursor_and_guards_partial_metadata(database):
    stage = MergeStage(Store(database.application))
    command = assessment_command(database, assertions=[], identities=[], decisions=[])
    stage.apply(**command)
    stage.apply(**{**command, **family_metadata("golden_copy"), "batch_id": "scoped"})
    with database.application.connect() as conn:
        assert conn.execute(
            text(
                "SELECT source_family,publication_family,position FROM mdm.checkpoint ORDER BY source_family"
            )
        ).all() == [("", "", 1), ("fixture", "golden_copy", 1)]
    with pytest.raises(ValueError, match="both families"):
        stage.apply(**{**command, "source_family": "fixture"})
    with pytest.raises(DBAPIError, match="Unknown publication family"):
        stage.apply(
            **{
                **command,
                **family_metadata("unregistered"),
                "batch_id": "unknown-family",
            }
        )
    with (
        pytest.raises(DBAPIError, match="checkpoint_scope"),
        database.application.begin() as conn,
    ):
        stage.store.commit(
            conn,
            request(
                database,
                batch_id="missing-proof",
                expected_generation=2,
                source_family="fixture",
                publication_family="golden_copy",
                committed_publication="p1",
            ),
            command["run_id"],
        )
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2


# --- Company mastering ticket 01: a mapping may be corrected ------------------
# Real PG16 against migration 031. A re-read of one publication under a
# corrected mapping must add a row beside its predecessor: before the ticket's
# amendments a changed reading raised on the revision guard and an unchanged
# one collided on assertion_id, so neither could ever be stored.


def reread(a, *, mapping_version, **changes):
    """The same record and publication, read again under a later mapping."""
    return assertion(
        source_code=a["source_code"],
        record_key=a["record_key"],
        publication_key=a["publication_key"],
        revision=a["revision"],
        effective_at=a["effective_at"],
        kind=a["kind"],
        fields=changes.pop("fields", a["fields"]),
        mapping_version=mapping_version,
        **changes,
    )


def register_reading(database, code, body):
    with database.admin.begin() as conn:
        register_dataset(conn, code, database.registry, body)
    with database.application.connect() as conn:
        return conn.scalar(
            text(
                "SELECT max(mapping_version) FROM mdm.dataset_mapping WHERE source_code=:c"
            ),
            {"c": code},
        )


def contract_body(**changes):
    return {
        "provider": "test",
        "family": "fixture",
        "publication_families": ["golden_copy", "opencorporates"],
        "schema_version": "1",
        "record_key": "key",
        "publication_key": "version",
        "effective_time": "effective_at",
        "semantics": "patch",
        **changes,
    }


def test_a_re_read_adds_a_row_and_the_newer_reading_wins(database):
    """The behaviour ticket 01 exists for, end to end."""
    first = source(key="reread-1", fields={"name": "Acme Hlds"})
    identity, binding = identity_and_binding(first)
    apply(database, 1, assertions=[first], identities=[identity], decisions=[binding])
    assert (
        documents(database, "entity")[identity["entity_id"]]["fields"]["name"]["value"]
        == "Acme Hlds"
    )
    assert (
        register_reading(
            database, "fixture.primary", contract_body(semantics="snapshot")
        )
        == 2
    )

    corrected = reread(first, mapping_version=2, fields={"name": "Acme Holdings"})
    assert corrected["assertion_id"] != first["assertion_id"]
    assert corrected["subject"] == first["subject"]
    apply(database, 2, assertions=[corrected])

    with database.application.connect() as conn:
        stored = conn.execute(
            text("""SELECT assertion_id,mapping_version FROM mdm.source_reading
            WHERE record_key='reread-1' ORDER BY mapping_version""")
        ).all()
    # Both readings retained; neither row was rewritten and nothing was pruned.
    assert [r[1] for r in stored] == [1, 2]
    assert {r[0] for r in stored} == {first["assertion_id"], corrected["assertion_id"]}
    # The subject never moved, so the Company keeps its identity and its id.
    entity = documents(database, "entity")[identity["entity_id"]]
    assert entity["fields"]["name"]["value"] == "Acme Holdings"
    assert (
        entity["fields"]["name"]["winner"]["assertion_id"] == corrected["assertion_id"]
    )


def test_a_re_read_that_changes_nothing_is_still_a_second_row(database):
    """The silent-drop half: same content, later reading, distinct assertion."""
    first = source(key="reread-2")
    apply(database, 1, assertions=[first])
    assert (
        register_reading(
            database, "fixture.primary", contract_body(semantics="snapshot")
        )
        == 2
    )
    same = reread(first, mapping_version=2)
    assert same["assertion_id"] != first["assertion_id"]
    apply(database, 2, assertions=[same])
    with database.application.connect() as conn:
        assert (
            conn.scalar(
                text(
                    "SELECT count(*) FROM mdm.source_reading WHERE record_key='reread-2'"
                )
            )
            == 2
        )


def test_one_revision_published_twice_is_still_refused(database):
    """The guard keeps the defect it was written for."""
    first = source(key="reread-3", fields={"name": "Acme"})
    contradictory = assertion(
        source_code=first["source_code"],
        record_key=first["record_key"],
        publication_key=first["publication_key"],
        revision=first["revision"],
        effective_at=first["effective_at"],
        kind=first["kind"],
        fields={"name": "Not Acme"},
    )
    apply(database, 1, assertions=[first])
    with pytest.raises(Conflict, match="contradictory publications"):
        apply(database, 2, assertions=[contradictory])


def test_a_reading_the_store_does_not_know_is_refused(database):
    """An assertion may not claim a mapping version nobody registered."""
    unregistered = source(key="reread-4", mapping_version=7)
    with pytest.raises(DBAPIError, match="Unsupported source schema"):
        apply(database, 1, assertions=[unregistered])


def test_registering_a_corrected_mapping_keeps_every_earlier_reading(database):
    assert register_reading(database, "fixture.secondary", contract_body()) == 1
    assert register_reading(database, "fixture.secondary", contract_body()) == 1
    assert (
        register_reading(
            database, "fixture.secondary", contract_body(semantics="snapshot")
        )
        == 2
    )
    with database.application.connect() as conn:
        readings = conn.execute(
            text("""SELECT mapping_version,body->>'semantics' FROM mdm.dataset_mapping
            WHERE source_code='fixture.secondary' ORDER BY mapping_version""")
        ).all()
    assert readings == [(1, "patch"), (2, "snapshot")]
    # The registered dataset row itself is append-only and never rewritten.
    with pytest.raises(DBAPIError, match="append-only"), database.admin.begin() as conn:
        conn.execute(text("UPDATE mdm.dataset SET body='{}'::jsonb"))
    with (
        pytest.raises(DBAPIError, match="append-only"),
        database.admin.begin() as conn,
    ):
        conn.execute(text("UPDATE mdm.dataset_mapping SET mapping_version=9"))


def test_a_change_that_would_move_a_record_identity_needs_a_new_source_code(database):
    """Ticket 01 decision 5: the engine compares the protected parts itself."""
    register_reading(database, "fixture.primary", contract_body())
    for change in (
        {"record_key": "other_key"},
        {"publication_key": "other_version"},
        {"adapter": {"record_key": ["b"], "version": "v1"}},
        {"adapter": {"record_key": ["a"], "record_key_format": "lei", "version": "v1"}},
        {
            "adapter": {
                "record_key": ["a"],
                "identifiers": {"lei": "lei"},
                "version": "v1",
            }
        },
    ):
        with (
            pytest.raises(Conflict, match="Dataset identity is immutable"),
            database.admin.begin() as conn,
        ):
            register_dataset(
                conn, "fixture.primary", database.registry, contract_body(**change)
            )


def test_a_corrected_mapping_reaches_the_adapter_that_reads_the_source(database):
    """Registering a reading is worth nothing if no reader ever uses it.

    The store writes every reading, but the adapters used to load the contract
    from mdm.dataset, which migration 023 froze at the first registration,
    and to call normalize with no reading at all. Both readings then produced
    byte-identical assertion ids: the collision the feature exists to prevent.
    """
    from edgar_warehouse.mdm.clean.cli import batch_assertions, read_manifest

    fixture = Path(__file__).parents[1] / "fixtures" / "clean_mdm" / "v1"
    contract = json.loads((fixture / "dataset.json").read_text())
    manifest, _, root = read_manifest(str(fixture / "manifest.json"))
    with database.admin.begin() as conn:
        register_policy(conn, json.loads((fixture / "policy.json").read_text()))
        register_dataset(conn, "fixture.representative", database.registry, contract)
    store = Store(database.application)
    batch = manifest["batches"][0]

    first = batch_assertions(batch, root, store)
    assert all("mapping_version" not in a for a in first)

    with database.admin.begin() as conn:
        register_dataset(
            conn,
            "fixture.representative",
            database.registry,
            {**contract, "semantics": "snapshot"},
        )
    corrected = batch_assertions(batch, root, store)
    assert {a["mapping_version"] for a in corrected} == {2}
    # Same records and publication, so the subjects stand and no Company moves;
    # only the assertion ids differ, which is what lets both readings be stored.
    assert [a["subject"] for a in corrected] == [a["subject"] for a in first]
    assert not {a["assertion_id"] for a in corrected} & {
        a["assertion_id"] for a in first
    }


def test_a_registry_version_bump_alone_is_not_a_new_reading(database):
    """Nothing in the mapping changed, so no reading is minted and no id forks."""
    with database.admin.begin() as conn:
        register_dataset(conn, "fixture.primary", database.registry, contract_body())
        later = str(uuid4())
    with (
        pytest.raises(Conflict, match="registry version bump is not a new reading"),
        database.admin.begin() as conn,
    ):
        register_dataset(conn, "fixture.primary", later, contract_body())


def test_a_deferred_record_and_an_assertion_agree_on_the_reading(database):
    """Both come out of one read of one artifact, so both must be accepted.

    The assertion path checks the schema against the reading that produced it
    (migration 031). The deferred path checked it against mdm.dataset, which
    migration 023 froze at the first registration, so a corrected mapping had
    its assertions accepted and its deferred records refused.
    """
    from edgar_warehouse.mdm.clean.evidence import deferred_record

    assert (
        register_reading(database, "fixture.primary", contract_body(schema_version="2"))
        == 2
    )
    a = source(key="agree-1", mapping_version=2, schema_version="2")
    d = deferred_record(
        source_code="fixture.primary",
        publication_key="p1",
        record_locator="line:9",
        schema_version="2",
        reason="invalid_field_shape",
        raw_record={"key": "agree-2"},
        provenance={"adapter_version": "v1"},
    )
    apply(database, 1, assertions=[a], deferred=[d])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.source_reading")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.set_aside_record")) == 1


def test_a_deferred_record_for_an_unregistered_schema_is_still_refused(database):
    from edgar_warehouse.mdm.clean.evidence import deferred_record

    d = deferred_record(
        source_code="fixture.primary",
        publication_key="p1",
        record_locator="line:9",
        schema_version="not-a-registered-schema",
        reason="invalid_field_shape",
        raw_record={"key": "agree-3"},
        provenance={"adapter_version": "v1"},
    )
    with pytest.raises(DBAPIError, match="Unknown deferred dataset contract"):
        apply(database, 1, deferred=[d])


def test_a_deferred_record_that_defers_again_under_a_later_reading_is_one_row(database):
    """A deferred body carries no reading, so a re-read is the same evidence.

    This is why the reading is not added to the deferred body: its natural key
    is (source_code, publication_key, record_locator), which a re-read reuses,
    so a second body would collide with the first rather than sit beside it.
    """
    from edgar_warehouse.mdm.clean.evidence import deferred_record

    d = deferred_record(
        source_code="fixture.primary",
        publication_key="p1",
        record_locator="line:9",
        schema_version="1",
        reason="invalid_field_shape",
        raw_record={"key": "agree-4"},
        provenance={"adapter_version": "v1"},
    )
    apply(database, 1, deferred=[d])
    register_reading(database, "fixture.primary", contract_body(semantics="snapshot"))
    apply(database, 2, deferred=[d])
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.set_aside_record")) == 1
