"""The same prepared-effect storage contract against every real engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
import time
from xml.etree import ElementTree
from collections import Counter
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.schema import CreateSchema
from sqlalchemy.exc import DBAPIError


def batch(api, **overrides):
    args = dict(
        batch="batch-one",
        run="run-one",
        scope="fixture-stream",
        pins={"policy": "fixture-policy-v1"},
        assessment={"outcome": "ready", "fixture": True},
        expected_generation=0,
        expected_checkpoint=0,
        checkpoint=1,
        objects=(
            api.Effect(
                "company", "invented-organization", {"name": "Invented Organization"}
            ),
            api.Effect(
                "person", "invented-individual", {"name": "Invented Individual"}
            ),
            api.Effect(
                "unrelated-fixture-type", "third", {"arbitrary": [None, "", True]}
            ),
        ),
        consumers=("fixture-export", "fixture-journal"),
        payload=b'{"fixture":"publication"}',
        evidence=(api.Effect("fixture-evidence", "one", {"revision": 1}),),
    )
    return api.PreparedBatch(**{**args, **overrides})


def count(adapter, table):
    with adapter.engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(adapter.tables[table]))


def test_native_policy_registration_uses_the_selected_engine_and_transaction(database, storage_api):
    """Exercise the actual native registration caller, not an opaque effect."""
    from edgar_warehouse.mdm.clean.store import current_reading, reading_at, register_policy
    from tests.support.rules_authority import register_dataset

    admin, runtime, role = database
    metadata, tables = storage_api.native_registry_model(admin.dialect.name)
    with admin.begin() as conn:
        if metadata.schema:
            conn.execute(CreateSchema(metadata.schema))
        metadata.create_all(conn)
        quote = admin.dialect.identifier_preparer.quote
        principal = f"'{role}'@'%'" if admin.dialect.name == "mysql" else quote(role)
        if admin.dialect.name == "postgresql":
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {quote(metadata.schema)} TO {principal}")
        for table in tables.values():
            name = admin.dialect.identifier_preparer.format_table(table)
            conn.execute(text(f"GRANT SELECT ON {name} TO {principal}"))
    policy = {"version": "native-registry-proof", "required_consumers": ["fixture"], "automatic_rules": []}
    with pytest.raises(RuntimeError, match="interrupt registration"), admin.begin() as conn:
        register_policy(conn, policy)
        raise RuntimeError("interrupt registration")
    with admin.begin() as conn:
        assert storage_api.registered_policies(conn) == []
        first = register_policy(conn, policy)
        assert register_policy(conn, dict(policy)) == first
        assert storage_api.registered_policies(conn) == [policy]
        version = str(uuid4())
        contract = {"provider": "fixture", "family": "fixture", "schema_version": "1",
                    "record_key": "key", "publication_key": "revision", "effective_time": "effective_at", "semantics": "patch"}
        register_dataset(conn, "fixture.records", version, contract)
        initial = current_reading(conn, "fixture.records")
        assert initial[0] == 1 and initial[1]["schema_version"] == "1"
        assert current_reading(conn, "fixture.absent") is None
    revised = {**contract, "schema_version": "2"}
    revised_version = str(uuid4())
    with pytest.raises(RuntimeError, match="interrupt mapping"), admin.begin() as conn:
        register_dataset(conn, "fixture.records", str(uuid4()), revised)
        raise RuntimeError("interrupt mapping")
    with admin.begin() as conn:
        assert current_reading(conn, "fixture.records") == initial
        register_dataset(conn, "fixture.records", revised_version, revised)
        register_dataset(conn, "fixture.records", revised_version, revised)
        assert current_reading(conn, "fixture.records")[0] == 2
        assert current_reading(conn, "fixture.records")[1]["schema_version"] == "2"
        assert reading_at(conn, "fixture.records", 1) == initial
    with runtime.connect() as conn:
        assert storage_api.registered_policies(conn) == [policy]
    with pytest.raises(DBAPIError), runtime.begin() as conn:
        register_policy(conn, {**policy, "version": "forbidden-runtime-registration"})
    concurrent = {**policy, "version": "concurrent-registration"}

    def register(_):
        with admin.begin() as conn:
            return register_policy(conn, concurrent)

    with ThreadPoolExecutor(max_workers=4) as pool:
        digests = list(pool.map(register, range(8)))
    assert len(set(digests)) == 1
    with admin.connect() as conn:
        assert len(storage_api.registered_policies(conn)) == 2


def test_generically_persists_all_requested_and_unrelated_types(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer-one")
    result = runtime.apply(request, lease)
    assert result == {
        "generation": 1,
        "duplicate": False,
        "changed": True,
        "checkpoint": 1,
    }
    actual = runtime.read([(e.type, e.id) for e in request.objects])
    assert len(actual) == 3
    for effect in request.objects:
        assert actual[(effect.type, effect.id)]["body"] == storage_api.document(
            effect.body
        )
        assert actual[(effect.type, effect.id)]["version"] == 1
    assert runtime.checkpoint(request.scope) == 1
    assert count(owner, "evidence") == 1
    assert count(owner, "outbox") == 2


def test_replay_does_not_repeat_history_or_publication(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer")
    runtime.apply(request, lease)
    before = {
        name: count(owner, name)
        for name in ("batch", "history", "current", "outbox", "evidence")
    }
    replay = runtime.apply(request, lease)
    assert replay["duplicate"] and replay["generation"] == 1
    assert {name: count(owner, name) for name in before} == before
    with pytest.raises(storage_api.AdapterError, match="batch_content_collision"):
        runtime.apply(replace(request, payload=b'{"different":true}'), lease)


def test_exact_bytes_and_numeric_temporal_boundaries_survive(adapters, storage_api):
    _, runtime, _ = adapters
    body = (
        '{"integer":1267650600228229401496703205499,"decimal":1.23000000000000000000001,'
        '"null":null,"empty":"","instant":"9999-12-31T23:59:59.999999+00:00",'
        '"unicode":"\u03a9\U0001f30d"}'
    ).encode()
    request = batch(
        storage_api, objects=(storage_api.Effect("arbitrary-\u03a9", "case-A", body),)
    )
    lease = runtime.claim(request.scope, "writer")
    runtime.apply(request, lease)
    stored = runtime.read([("arbitrary-\u03a9", "case-A")])[
        ("arbitrary-\u03a9", "case-A")
    ]
    assert stored["body"] == body and stored["body_hash"] == sha256(body).hexdigest()
    assert runtime.read([("arbitrary-\u03a9", "case-a")]) == {}


def test_changed_effects_version_history_and_unchanged_pass(adapters, storage_api):
    owner, runtime, _ = adapters
    initial = batch(storage_api)
    lease = runtime.claim(initial.scope, "writer")
    runtime.apply(initial, lease)
    change = replace(
        initial,
        batch="batch-two",
        expected_generation=1,
        expected_checkpoint=1,
        checkpoint=2,
        objects=(
            storage_api.Effect(
                initial.objects[0].type,
                initial.objects[0].id,
                {"name": "Updated Fixture"},
                1,
            ),
        ),
        evidence=(),
    )
    assert runtime.apply(change, lease)["changed"]
    assert len(runtime.history(change.objects[0].type, change.objects[0].id)) == 2
    unchanged = replace(
        change,
        batch="batch-three",
        expected_generation=2,
        expected_checkpoint=2,
        checkpoint=3,
        objects=(replace(change.objects[0], expected_version=2),),
    )
    assert not runtime.apply(unchanged, lease)["changed"]
    assert count(owner, "outbox") == 4
    assert (
        runtime.read([(change.objects[0].type, change.objects[0].id)])[
            (change.objects[0].type, change.objects[0].id)
        ]["version"]
        == 2
    )
    assert runtime.apply(initial, lease)["duplicate"]
    assert runtime.checkpoint(initial.scope) == 3 and runtime.generation() == 3


def test_stale_generation_checkpoint_version_and_pins_do_not_write(
    adapters, storage_api
):
    owner, runtime, _ = adapters
    initial = batch(storage_api)
    lease = runtime.claim(initial.scope, "writer")
    runtime.apply(initial, lease)
    follow = replace(
        initial,
        batch="follow",
        expected_checkpoint=1,
        checkpoint=2,
        objects=(),
        evidence=(),
    )
    cases = [
        (follow, 0, "stale_generation"),
        (replace(follow, expected_checkpoint=0), 1, "stale_checkpoint"),
        (replace(follow, objects=initial.objects), 1, "stale_object_version"),
        (replace(follow, pins={"policy": "other"}), 1, "frozen_pins_changed"),
    ]
    for request, generation, error in cases:
        with pytest.raises(storage_api.AdapterError, match=error):
            runtime.apply(replace(request, expected_generation=generation), lease)
        assert runtime.generation() == 1 and runtime.checkpoint(initial.scope) == 1
        assert count(owner, "batch") == 1


def test_concurrent_writers_cannot_commit_the_same_generation(adapters, storage_api):
    owner, runtime, _ = adapters
    a = batch(storage_api)
    b = replace(a, batch="other-batch", run="other-run", scope="other-scope")
    leases = [runtime.claim(r.scope, "writer") for r in (a, b)]

    def apply(pair):
        request, lease = pair
        try:
            return runtime.apply(request, lease)
        except storage_api.AdapterError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(apply, zip((a, b), leases)))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert "stale_generation" in results
    assert count(owner, "batch") == 1


def test_runtime_cannot_bypass_capabilities_or_mutate_history(adapters):
    _, runtime, _ = adapters
    table = runtime.tables["gate"]
    for statement in (
        table.update().values(generation=123),
        table.delete(),
        text("CREATE TABLE unauthorized_fixture(id BIGINT)"),
    ):
        with pytest.raises(DBAPIError), runtime.engine.begin() as conn:
            conn.execute(statement)


def test_expired_and_reclaimed_scope_is_fenced(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    old = runtime.claim(request.scope, "first-writer")
    with pytest.raises(storage_api.AdapterError, match="scope_already_leased"):
        runtime.claim(request.scope, "second-writer")
    with owner.engine.begin() as conn:
        conn.execute(update(owner.tables["lease"]).values(expires=0))
    with pytest.raises(storage_api.AdapterError, match="stale_scope_lease"):
        runtime.apply(request, old)
    new = runtime.claim(request.scope, "second-writer")
    assert new.fence > old.fence
    with pytest.raises(storage_api.AdapterError, match="stale_scope_lease"):
        runtime.apply(request, old)
    assert runtime.apply(request, new)["generation"] == 1


def test_publication_claim_bytes_fence_and_verified_receipt(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    consumer = request.consumers[0]
    first = runtime.claim_outbox(request.batch, consumer, "publisher-one", seconds=1)
    assert first["payload"] == request.payload
    assert first["payload_hash"] == sha256(request.payload).hexdigest()
    with pytest.raises(storage_api.AdapterError, match="publication_already_leased"):
        runtime.claim_outbox(request.batch, consumer, "publisher-two")
    with pytest.raises(
        storage_api.AdapterError, match="stale_or_invalid_publication_receipt"
    ):
        runtime.ack_outbox(
            request.batch, consumer, "publisher-one", first["fence"], "0" * 64
        )
    time.sleep(1.1)
    with pytest.raises(storage_api.AdapterError, match="publication_lease_expired"):
        runtime.ack_outbox(
            request.batch,
            consumer,
            "publisher-one",
            first["fence"],
            first["payload_hash"],
        )
    second = runtime.claim_outbox(request.batch, consumer, "publisher-two")
    assert second["fence"] > first["fence"]
    with pytest.raises(
        storage_api.AdapterError, match="stale_or_invalid_publication_receipt"
    ):
        runtime.ack_outbox(
            request.batch,
            consumer,
            "publisher-one",
            first["fence"],
            first["payload_hash"],
        )
    assert (
        runtime.ack_outbox(
            request.batch,
            consumer,
            "publisher-two",
            second["fence"],
            second["payload_hash"],
        )["verified"]
        == 1
    )
    assert runtime.claim_outbox(request.batch, consumer, "publisher-two") is None


def test_populated_migration_rerun_preserves_state_and_rejects_checksum_drift(
    adapters, storage_api
):
    owner, runtime, role = adapters
    request = batch(storage_api)
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    assert not storage_api.migrate(
        owner.engine, runtime_role=role, prefix=owner.prefix
    )["initialized"]
    assert runtime.generation() == 1 and count(owner, "history") == 3
    with owner.engine.begin() as conn:
        conn.execute(update(owner.tables["migration"]).values(checksum="0" * 64))
    with pytest.raises(storage_api.AdapterError, match="differs from this build"):
        storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix)


def test_error_after_the_batch_insert_rolls_back_all_effects_then_resumes(
    adapters, storage_api
):
    owner, runtime, _ = adapters
    d = owner.engine.dialect
    quote = d.identifier_preparer.quote
    history = d.identifier_preparer.format_table(owner.tables["history"])
    trigger = f"{quote(owner.schema)}.{quote(owner.prefix + '_injected_failure')}"
    function = f"{quote(owner.schema)}.{quote(owner.prefix + '_injected_function')}"
    with owner.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if d.name == "postgresql":
            conn.execute(
                text(
                    f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture_failure'; END $$"
                )
            )
            conn.execute(
                text(
                    f"CREATE TRIGGER {quote(owner.prefix + '_injected_failure')} AFTER INSERT ON {history} FOR EACH STATEMENT EXECUTE FUNCTION {function}()"
                )
            )
        elif d.name == "mysql":
            conn.execute(
                text(
                    f"CREATE TRIGGER {trigger} BEFORE INSERT ON {history} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture_failure'"
                )
            )
        else:
            conn.execute(
                text(
                    f"CREATE TRIGGER {trigger} ON {history} AFTER INSERT AS BEGIN THROW 50002,'fixture_failure',1; END"
                )
            )
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer")
    try:
        with pytest.raises(storage_api.AdapterError, match="database_operation_failed"):
            runtime.apply(request, lease)
        assert runtime.generation() == runtime.checkpoint(request.scope) == 0
        assert all(
            count(owner, name) == 0
            for name in (
                "run",
                "batch",
                "history",
                "current",
                "evidence",
                "outbox",
                "checkpoint",
            )
        )
    finally:
        with owner.engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as conn:
            if d.name == "postgresql":
                conn.execute(
                    text(
                        f"DROP TRIGGER {quote(owner.prefix + '_injected_failure')} ON {history}"
                    )
                )
                conn.execute(text(f"DROP FUNCTION {function}()"))
            else:
                conn.execute(text(f"DROP TRIGGER {trigger}"))
    assert runtime.apply(request, lease)["generation"] == 1
    assert count(owner, "batch") == 1 and count(owner, "history") == 3


def test_a_restarted_caller_recovers_a_lost_ack_without_duplicate_writes(
    adapters, storage_api
):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    runtime.apply(request, runtime.claim(request.scope, "old-process"))
    with owner.engine.begin() as conn:
        conn.execute(update(owner.tables["lease"]).values(expires=0))
    restarted = storage_api.Adapter(runtime.engine, prefix=runtime.prefix)
    receipt = restarted.apply(
        request, restarted.claim(request.scope, "restarted-process")
    )
    assert receipt["duplicate"] and receipt["generation"] == 1
    assert count(owner, "batch") == 1 and count(owner, "history") == 3


def test_evidence_is_immutable_and_pending_initialization_cannot_write(
    adapters, storage_api
):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer")
    runtime.apply(request, lease)
    collision = replace(
        request,
        batch="next",
        expected_generation=1,
        expected_checkpoint=1,
        checkpoint=2,
        objects=(),
        evidence=(replace(request.evidence[0], body={"revision": 2}),),
    )
    with pytest.raises(storage_api.AdapterError, match="immutable_evidence_collision"):
        runtime.apply(collision, lease)
    with owner.engine.begin() as conn:
        conn.execute(update(owner.tables["migration"]).values(complete=0))
    with pytest.raises(storage_api.AdapterError, match="storage_not_initialized"):
        runtime.claim("another-scope", "writer")
    assert count(owner, "batch") == 1 and count(owner, "evidence") == 1


def test_lookup_plan_seeks_the_storage_key_on_every_engine(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    statement = owner.lookup_statement([(e.type, e.id) for e in request.objects[:2]])
    sql = str(
        statement.compile(
            dialect=owner.engine.dialect, compile_kwargs={"literal_binds": True}
        )
    )
    name = owner.tables["current"].name
    with owner.engine.connect() as conn:
        if owner.engine.dialect.name == "postgresql":
            conn.execute(text("SET LOCAL enable_seqscan=off"))
            plan = conn.execute(text("EXPLAIN (FORMAT JSON) " + sql)).scalar()[0][
                "Plan"
            ]

            def nodes(node):
                yield node
                for child in node.get("Plans", []):
                    yield from nodes(child)

            accesses = [n for n in nodes(plan) if n.get("Relation Name") == name]
            assert accesses and all(
                n["Node Type"] in {"Index Scan", "Index Only Scan"} for n in accesses
            )
        elif owner.engine.dialect.name == "mysql":
            plan = json.loads(conn.execute(text("EXPLAIN FORMAT=JSON " + sql)).scalar())

            def entries(node):
                if isinstance(node, dict):
                    yield node
                    for value in node.values():
                        yield from entries(value)
                elif isinstance(node, list):
                    for value in node:
                        yield from entries(value)

            accesses = [n for n in entries(plan) if n.get("table_name") == name]
            assert accesses and all(
                n.get("access_type") in {"ref", "eq_ref", "const"} for n in accesses
            )
        else:
            conn.exec_driver_sql("SET SHOWPLAN_XML ON")
            try:
                plan = conn.execute(text(sql)).scalar()
            finally:
                conn.exec_driver_sql("SET SHOWPLAN_XML OFF")
            tree = ElementTree.fromstring(plan)
            operations = [
                node.attrib.get("PhysicalOp", "")
                for node in tree.iter()
                if node.tag.endswith("RelOp")
            ]
            assert any("Index Seek" in operation for operation in operations)
            assert not any(
                "Index Scan" in operation or "Table Scan" in operation
                for operation in operations
            )


def test_large_payload_and_chunked_key_lists_preserve_the_complete_request(
    adapters, storage_api
):
    _, runtime, _ = adapters
    objects = tuple(
        storage_api.Effect(
            "generated-fixture-type", str(i), {"n": i, "text": "\u03a9" * 40}
        )
        for i in range(805)
    )
    payload = storage_api.canonical({"text": "\U0001f30d" * 6000})
    request = batch(storage_api, objects=objects, payload=payload)
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    assert len(runtime.read([(e.type, e.id) for e in objects])) == len(objects)
    claim = runtime.claim_outbox(request.batch, request.consumers[0], "publisher")
    assert (
        claim["payload"] == payload
        and claim["payload_hash"] == sha256(payload).hexdigest()
    )


def test_shared_identity_survivorship_and_links_prepare_the_same_storage_input(
    adapters, storage_api
):
    """The adapter consumes existing shared-engine results without domain code.

    This proves the prepared-effect seam, not a replacement of the native
    runtime's Rules/Bookkeeping registration and source-activation workflow.
    """
    from edgar_warehouse.mdm.clean.evidence import assertion
    from edgar_warehouse.mdm.clean.identity import replay
    from edgar_warehouse.mdm.clean.relationships import project, types_of
    from edgar_warehouse.mdm.clean.store import canonical, digest
    from edgar_warehouse.mdm.clean.survivorship import current_claims, select_fields
    from tests.integration.test_clean_mdm_postgres import identity_and_binding
    from tests.support.fresh_mastering import AS_OF, cohort

    _, runtime, _ = adapters
    policy, _, readings = cohort()
    pairs = [
        identity_and_binding(
            a, str(uuid5(NAMESPACE_URL, "adapter-fixture/" + a["subject"]))
        )
        for a in readings
    ]
    identities, decisions = [pair[0] for pair in pairs], [pair[1] for pair in pairs]
    state = replay(identities, decisions, AS_OF)  # Existing Rust identity engine.
    claims = current_claims(readings, AS_OF, state.retired_sources)
    projected = {}
    policy_digest = digest(policy)
    for identity in identities:
        entity = identity["entity_id"]
        members = sorted(s for s, e in state.bindings.items() if e == entity)
        fields, profiles, _ = select_fields(
            identity["kind"],
            members,
            claims,
            policy,
            state.overrides,
            as_of=AS_OF,
            policy_digest=policy_digest,
            entity_id=entity,
        )
        projected[entity] = {
            "entity_id": entity,
            "kind": identity["kind"],
            "canonical_id": entity,
            "status": "accepted",
            "subjects": members,
            "fields": fields,
            "profiles": profiles,
            "identifiers": {
                k: [v] for k, v in claims[members[0]]["identifiers"].items()
            },
        }
    person = next(a for a in readings if a["kind"] == "person")
    company = next(a for a in readings if a["kind"] == "company")
    sighting = assertion(
        source_code="fixture.links",
        record_key="one",
        publication_key="one",
        revision=1,
        effective_at=AS_OF,
        kind="person",
        fields={},
        relationships=[
            {
                "type": "EMPLOYED_BY",
                "source_subject": person["subject"],
                "target_subject": company["subject"],
                "capacity": "director",
                "on": AS_OF,
            }
        ],
    )
    edges, reviews = project(
        current_claims([*readings, sighting], AS_OF, state.retired_sources),
        state,
        projected,
        AS_OF,
        types=types_of(policy),
    )
    assert Counter(p["kind"] for p in projected.values()) == {"company": 2, "person": 2}
    assert edges and not reviews
    effects = tuple(
        storage_api.Effect("entity", k, canonical(v).encode())
        for k, v in projected.items()
    )
    effects += tuple(
        storage_api.Effect("relationship", e["relationship_id"], canonical(e).encode())
        for e in edges
    )
    request = batch(
        storage_api,
        objects=effects,
        evidence=tuple(
            storage_api.Effect(
                "source-reading", a["assertion_id"], canonical(a).encode()
            )
            for a in [*readings, sighting]
        ),
        pins={"policy": policy_digest},
        payload=canonical({"entities": projected, "relationships": edges}).encode(),
    )
    runtime.apply(request, runtime.claim(request.scope, "shared-engine-worker"))
    actual = runtime.read([(effect.type, effect.id) for effect in effects])
    assert len(actual) == len(effects)
    assert all(
        actual[(effect.type, effect.id)]["body"] == effect.body for effect in effects
    )
    publication = runtime.claim_outbox(
        request.batch, request.consumers[0], "independent-verifier"
    )
    assert publication["payload"] == request.payload


def test_a_caller_cannot_delay_an_expiry_checked_commit(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer", seconds=1)
    name = runtime.routines["apply"][0]
    wire = json.dumps(
        {
            "intent": request.intent(),
            "owner": lease.owner.encode().hex(),
            "fence": str(lease.fence),
            "expected_generation": "0",
        }
    )
    if runtime.engine.dialect.name == "postgresql":
        with pytest.raises(DBAPIError):
            with runtime.engine.begin() as conn:
                conn.execute(text(f"SELECT * FROM {name}(:wire)"), {"wire": wire}).all()
                conn.execute(text("SELECT pg_sleep(1.2)"))
    else:
        with pytest.raises(DBAPIError):
            with runtime.engine.begin() as conn:
                conn.execute(select(runtime.tables["gate"].c.generation)).all()
                statement = (
                    f"CALL {name}(:wire)"
                    if runtime.engine.dialect.name == "mysql"
                    else f"EXEC {name} @p_wire=:wire"
                )
                conn.execute(text(statement), {"wire": wire}).all()
    assert runtime.generation() == runtime.checkpoint(request.scope) == 0
    assert count(owner, "batch") == 0


def test_migration_refuses_a_changed_capability_security_boundary(
    adapters, storage_api
):
    owner, _, role = adapters
    name = owner.routines["claim"][0]
    with owner.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if owner.engine.dialect.name == "postgresql":
            conn.execute(text(f"ALTER FUNCTION {name}(text) SECURITY INVOKER"))
        elif owner.engine.dialect.name == "mysql":
            conn.execute(text(f"ALTER PROCEDURE {name} SQL SECURITY INVOKER"))
        else:
            conn.execute(
                text(
                    f"ALTER PROCEDURE {name} @p_wire VARCHAR(MAX) AS SELECT 1 AS ignored"
                )
            )
    with pytest.raises(storage_api.AdapterError, match="capability differs"):
        storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix)


def test_prepared_effects_never_silently_repin_to_a_later_generation(
    adapters, storage_api
):
    _, runtime, _ = adapters
    prepared = batch(storage_api)
    unrelated = batch(
        storage_api,
        batch="unrelated-batch",
        run="unrelated-run",
        scope="unrelated-scope",
        objects=(storage_api.Effect("unrelated-type", "unrelated-key", {}),),
        evidence=(),
    )
    runtime.apply(unrelated, runtime.claim(unrelated.scope, "other-writer"))
    lease = runtime.claim(prepared.scope, "writer")
    with pytest.raises(storage_api.AdapterError, match="stale_generation"):
        runtime.apply(prepared, lease)
    assert prepared.expected_generation == 0 and runtime.checkpoint(prepared.scope) == 0
    assert runtime.read([(e.type, e.id) for e in prepared.objects]) == {}
