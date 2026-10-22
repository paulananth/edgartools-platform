"""The same prepared-effect storage contract against every real engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
import os
import subprocess
import sys
import time
from threading import Barrier, Event
from xml.etree import ElementTree
from collections import Counter
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import event, func, select, text, update
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


def test_native_connection_uses_configured_driver_and_restricted_principal(adapters, storage_api, monkeypatch):
    from edgar_warehouse.mdm.clean.connections import engine_from_env
    from edgar_warehouse.mdm.clean.store import storage_adapter as native_storage_adapter

    owner, runtime, role = adapters
    selected = runtime.engine.dialect.name
    monkeypatch.setenv("MDM_APPLICATION_ROLE", role)
    # The connection's scheme selects its engine. A URL without a driver must
    # resolve to the same supported driver as the skill's standalone command.
    monkeypatch.setenv("NATIVE_CONNECTION_PROOF", runtime.engine.url.set(drivername=selected).render_as_string(hide_password=False))
    engine = engine_from_env("NATIVE_CONNECTION_PROOF")
    try:
        assert engine.dialect.driver == runtime.engine.dialect.driver
        adapter = storage_api.Adapter(engine, prefix=runtime.prefix)
        assert adapter.generation() == 0
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(update(adapter.tables["gate"]).values(generation=99))
    finally:
        engine.dispose()
    monkeypatch.setenv("NATIVE_CONNECTION_PROOF", owner.engine.url.set(drivername=selected).render_as_string(hide_password=False))
    engine = engine_from_env("NATIVE_CONNECTION_PROOF", restricted=False)
    try:
        with engine.begin() as conn:
            conn.execute(update(owner.tables["gate"]).values(generation=0))
    finally:
        engine.dispose()
    if selected != "postgresql":
        engine = engine_from_env("NATIVE_CONNECTION_PROOF")
        try:
            with pytest.raises(native_storage_adapter().AdapterError, match="Authenticate as the configured runtime principal"):
                engine.connect()
        finally:
            engine.dispose()


def test_native_policy_registration_uses_the_selected_engine_and_transaction(database, storage_api):
    """Exercise the actual native registration caller, not an opaque effect."""
    from edgar_warehouse.mdm.clean.store import current_reading, reading_at, register_policy
    from edgar_warehouse.mdm.clean.merge import MergeStage
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
        assert MergeStage._check_rule_proposals(conn, first, None, []) == policy
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
        expected_contracts = {"fixture.records": initial[1]}
        for n, code in enumerate(("fixture.Café.資料.🧪." + "x" * 300,
                                  "fixture.café.資料.🧪." + "x" * 300,
                                  "fixture.Cafe.資料.🧪." + "x" * 300)):
            distinct = {**contract, "schema_version": str(n + 10)}
            register_dataset(conn, code, str(uuid4()), distinct)
            assert current_reading(conn, code)[1]["schema_version"] == str(n + 10)
            expected_contracts[code] = current_reading(conn, code)[1]
        # Database case/accent folding must not have conflated earlier names.
        assert current_reading(conn, "fixture.Café.資料.🧪." + "x" * 300)[1]["schema_version"] == "10"
        assert storage_api.dataset_contracts(conn, [*expected_contracts, "fixture.absent", "fixture.records"]) == expected_contracts
        assert storage_api.dataset_contracts(conn, []) == {}
        assert storage_api.registered_policy(conn, "0" * 64) is None
    with runtime.connect() as conn:
        assert storage_api.registered_policies(conn) == [policy]
    with pytest.raises(DBAPIError), runtime.begin() as conn:
        register_policy(conn, {**policy, "version": "forbidden-runtime-registration"})
    concurrent = {**policy, "version": "concurrent-registration"}
    insert_barrier = Barrier(4, timeout=15)

    def overlap_inserts(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT INTO") and "policy" in statement:
            insert_barrier.wait()

    def register(_):
        with admin.begin() as conn:
            return register_policy(conn, concurrent)

    event.listen(admin, "before_cursor_execute", overlap_inserts)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            digests = list(pool.map(register, range(4)))
    finally:
        event.remove(admin, "before_cursor_execute", overlap_inserts)
    assert len(set(digests)) == 1
    with admin.connect() as conn:
        assert len(storage_api.registered_policies(conn)) == 2
    for version in (None, 1):
        assert_index_lookup(admin, storage_api.dataset_reading_statement(admin.dialect.name, "fixture.records", version), "dataset_mapping")


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


def test_keyed_native_scope_reads_paginate_and_retain_the_callers_transaction(adapters, storage_api):
    owner, runtime, _ = adapters
    lookup = "fixture.lookup/Café/資料"
    records = tuple(storage_api.Effect(lookup, f"record-{n}", {"position": n}) for n in range(405))
    request = batch(storage_api, objects=records + (storage_api.Effect(lookup.lower(), "unrelated", {"position": -1}),))
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    opened = []

    def note_connection(connection):
        opened.append(True)

    with runtime.engine.connect() as conn:
        event.listen(runtime.engine, "engine_connect", note_connection)
        try:
            assert runtime.generation(connection=conn) == 1
            assert runtime.checkpoint(request.scope, connection=conn) == 1
            found = dict(runtime.iter_type(lookup, connection=conn))
            assert len(found) == 405
            assert {json.loads(row["body"])["position"] for row in found.values()} == set(range(405))
            assert all(key[0] == lookup and row["version"] == 1 for key, row in found.items())
            assert runtime.read([(lookup, "record-404")], connection=conn)[(lookup, "record-404")] == found[(lookup, "record-404")]
            evidence = runtime.read([("fixture-evidence", "one")], immutable=True, connection=conn)
            assert evidence[("fixture-evidence", "one")]["body"] == b'{"revision":1}'
            assert not conn.closed
        finally:
            event.remove(runtime.engine, "engine_connect", note_connection)
    assert len(opened) == 0
    assert_index_lookup(owner.engine, owner.type_statement(lookup), owner.tables["current"].name)


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


def test_populated_protocol_upgrade_preserves_replay_and_consumer_payload_bytes(adapters, storage_api):
    owner, runtime, role = adapters
    original = batch(storage_api)
    lease = runtime.claim(original.scope, "writer")
    runtime.apply(original, lease)
    ledger = owner.tables["migration"]
    if owner.engine.dialect.name == "mysql":
        compiled = "\n".join(storage_api._migration_statements(owner))
        historical = compiled.replace(")ENGINE=InnoDB CHARSET=ascii COLLATE ascii_bin\n",
                                      ")CHARSET=ascii ENGINE=InnoDB COLLATE ascii_bin\n")
        assert historical != compiled
        with owner.engine.begin() as conn:
            conn.execute(update(ledger).where(ledger.c.version == 1).values(checksum=sha256(historical.encode()).hexdigest()))
    with owner.engine.connect() as conn:
        baseline = dict(conn.execute(select(ledger).where(ledger.c.version == 1)).mappings().one())
    before = {name: count(owner, name) for name in ("batch", "current", "history", "evidence", "outbox")}
    result = storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)
    assert result["migration"] == 2 and result["initialized"]
    assert not storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)["initialized"]
    upgraded = storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=2)
    assert upgraded.apply(original, lease)["duplicate"]
    assert upgraded.generation() == 1
    assert {name: count(owner, name) for name in before} == before
    with owner.engine.connect() as conn:
        assert dict(conn.execute(select(ledger).where(ledger.c.version == 1)).mappings().one()) == baseline
    for consumer in original.consumers:
        claim = upgraded.claim_outbox(original.batch, consumer, "publisher")
        assert claim["payload"] == original.payload
        upgraded.ack_outbox(original.batch, consumer, "publisher", claim["fence"], claim["payload_hash"])
    payloads = {original.consumers[0]: ('{"precise":100000000000000000001.00000,"text":"東","long":"' + "🧪" * 3000 + '"}').encode(),
                original.consumers[1]: b'{"different":[true,null,""]}'}
    changed = replace(original, batch="consumer-payloads", expected_generation=1, expected_checkpoint=1, checkpoint=2,
                      objects=(replace(original.objects[0], body={"changed": True}, expected_version=1),),
                      payload=b"null", payloads=payloads)
    assert upgraded.apply(changed, lease)["generation"] == 2
    for consumer, payload in payloads.items():
        claim = upgraded.claim_outbox(changed.batch, consumer, "publisher")
        assert claim["payload"] == payload and claim["payload_hash"] == sha256(payload).hexdigest()
        with pytest.raises(storage_api.AdapterError, match="stale_or_invalid_publication_receipt"):
            upgraded.ack_outbox(changed.batch, consumer, "publisher", claim["fence"], "0" * 64)
        upgraded.ack_outbox(changed.batch, consumer, "publisher", claim["fence"], claim["payload_hash"])
    with pytest.raises(storage_api.AdapterError, match="migration differs"):
        storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix)


def test_migration_fingerprint_survives_python_hash_seed_changes(storage_api):
    # No server or credentials enter the child processes: compile the logical
    # model with the same driver dialect and a fixed invented schema.
    code = '''
from importlib import import_module
from types import SimpleNamespace
from hashlib import sha256
from sqlalchemy.dialects import mysql
a = import_module("skills.mdm-engineering.scripts.database_adapter")
metadata, tables = a.model("fixture", "fixture")
dialect = mysql.dialect()
build = SimpleNamespace(engine=SimpleNamespace(dialect=dialect), metadata=metadata,
                        routines=a.capabilities(dialect, tables, "fixture"),
                        commit_guards=a.commit_guards(dialect, tables, "fixture"))
print(sha256("\\n".join(a._migration_statements(build)).encode()).hexdigest())
'''
    fingerprints = [subprocess.check_output([sys.executable, "-c", code],
                    env={**os.environ, "PYTHONHASHSEED": seed}, text=True, timeout=15).strip()
                    for seed in ("1", "2", "3")]
    assert len(set(fingerprints)) == 1


@pytest.mark.parametrize("interrupt_after_replacement", [False, True])
def test_interrupted_upgrade_refuses_old_and_new_writes_then_resumes(adapters, storage_api, interrupt_after_replacement):
    owner, runtime, role = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer")
    runtime.apply(request, lease)
    before = {name: count(owner, name) for name in ("batch", "current", "history", "evidence", "outbox")}
    upgraded = storage_api.Adapter(owner.engine, prefix=owner.prefix, protocol=2)
    routine = list(upgraded.routines.values())[int(interrupt_after_replacement)][1]

    def interrupt(conn, clause, *args):
        if str(clause) == routine:
            raise RuntimeError("interrupt storage upgrade")

    phase = "after_execute" if interrupt_after_replacement else "before_execute"
    event.listen(owner.engine, phase, interrupt)
    try:
        with pytest.raises(RuntimeError, match="interrupt storage upgrade"):
            storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)
    finally:
        event.remove(owner.engine, phase, interrupt)
    with owner.engine.connect() as conn:
        rows = list(conn.execute(select(owner.tables["migration"])).mappings())
        assert {row["version"] for row in rows} == {1, 2}
        assert all(not row["complete"] for row in rows)
    pending = replace(request, batch="pending-upgrade", expected_generation=1,
                      expected_checkpoint=1, checkpoint=2, objects=())
    # MySQL drops/recreates procedures, so EXECUTE is also absent until the
    # final grant step. Either refusal protects this partially replaced path;
    # before replacement, require the unchanged v1 routine's migration guard.
    refusal = ("storage_not_initialized|database_operation_failed"
               if interrupt_after_replacement and owner.engine.dialect.name == "mysql"
               else "storage_not_initialized")
    for api in (runtime, storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=2)):
        with pytest.raises(storage_api.AdapterError, match=refusal):
            api.apply(pending, lease)
    assert {name: count(owner, name) for name in before} == before
    assert storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)["initialized"]
    assert runtime.apply(request, lease)["duplicate"]
    assert runtime.generation() == 1
    assert {name: count(owner, name) for name in before} == before


def test_upgrade_fences_an_old_call_already_waiting_at_the_gate(adapters, storage_api):
    owner, runtime, role = adapters
    request = batch(storage_api)
    lease = runtime.claim(request.scope, "writer")
    upgraded = storage_api.Adapter(owner.engine, prefix=owner.prefix, protocol=2)
    # This is the upgrade's actual first stage, before publishing pending.
    with owner.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        storage_api._verify_migration_guards(conn, upgraded, install=True)
    selected = owner.engine.dialect.name
    pids = {}
    pending = Event()
    entered = {name: Event() for name in ("migration", "writer")}
    pid_sql = {"postgresql": "SELECT pg_backend_pid()", "mysql": "SELECT CONNECTION_ID()", "mssql": "SELECT @@SPID"}[selected]
    wait_sql = {
        "postgresql": "SELECT count(*) FROM pg_locks WHERE pid=:pid AND NOT granted",
        "mysql": "SELECT count(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.threads t ON t.THREAD_ID=w.REQUESTING_THREAD_ID WHERE t.PROCESSLIST_ID=:pid",
        "mssql": "SELECT count(*) FROM sys.dm_exec_requests WHERE session_id=:pid AND blocking_session_id>0",
    }[selected]

    def capture(name):
        def before(conn, cursor, statement, params, context, many):
            wanted = (statement.startswith("UPDATE ") and owner.tables["migration"].name in statement) if name == "migration" else runtime.prefix + "_apply" in statement
            if wanted and not entered[name].is_set():
                cursor.execute(pid_sql)
                pids[name] = cursor.fetchone()[0]
                entered[name].set()
        return before

    def wait_for_lock(name, *, allow_pending=False):
        assert entered[name].wait(10), name + " did not enter its database call"
        deadline = time.monotonic() + 10
        with owner.engine.connect() as conn:
            while not (allow_pending and pending.is_set()) and not conn.scalar(text(wait_sql), {"pid": pids[name]}):
                assert time.monotonic() < deadline, name + " did not wait for the gate"
                time.sleep(0.02)

    first = next(iter(upgraded.routines.values()))[1]

    def interrupt(conn, clause, *args):
        if str(clause) == first:
            pending.set()
            raise RuntimeError("interrupt overlapping upgrade")

    migration_capture, writer_capture = capture("migration"), capture("writer")
    gate = owner.tables["gate"]
    lock = select(gate.c.id).where(gate.c.id == 1).with_for_update()
    if selected == "mssql":
        lock = lock.with_hint(gate, "WITH (UPDLOCK,HOLDLOCK)", dialect_name="mssql")
    with ThreadPoolExecutor(max_workers=2) as pool:
        with owner.engine.begin() as conn:
            conn.execute(lock).one()
            event.listen(owner.engine, "before_cursor_execute", migration_capture)
            event.listen(runtime.engine, "before_cursor_execute", writer_capture)
            event.listen(owner.engine, "before_execute", interrupt)
            try:
                writer = pool.submit(runtime.apply, request, lease)
                wait_for_lock("writer")
                migration = pool.submit(storage_api.migrate, owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)
                # Either the barrier becomes pending while the writer waits,
                # or a trigger's current ledger lock makes it drain that writer.
                wait_for_lock("migration", allow_pending=True)
                pending_before_release = pending.is_set()
            finally:
                event.remove(owner.engine, "before_cursor_execute", migration_capture)
                event.remove(runtime.engine, "before_cursor_execute", writer_capture)
        try:
            with pytest.raises(RuntimeError, match="interrupt overlapping"):
                migration.result(timeout=15)
            if pending_before_release:
                with pytest.raises(storage_api.AdapterError, match="storage_not_initialized"):
                    writer.result(timeout=15)
            else:
                assert writer.result(timeout=15)["generation"] == 1
        finally:
            event.remove(owner.engine, "before_execute", interrupt)
    assert runtime.generation() == (0 if pending_before_release else 1)
    if pending_before_release:
        assert count(owner, "batch") == count(owner, "current") == count(owner, "outbox") == 0
    storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)
    assert runtime.apply(request, lease)["generation"] == 1
    assert runtime.apply(request, lease)["duplicate"]


def test_populated_upgrade_rerun_refuses_a_missing_migration_write_guard(adapters, storage_api):
    owner, runtime, role = adapters
    storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)
    upgraded = storage_api.Adapter(owner.engine, prefix=owner.prefix, protocol=2)
    name, _, _, table, _ = upgraded.migration_guards[0]
    quote = owner.engine.dialect.identifier_preparer.quote
    target = (quote(name) + " ON " + owner.engine.dialect.identifier_preparer.format_table(owner.tables[table])
              if owner.engine.dialect.name == "postgresql"
              else quote(upgraded.schema) + "." + quote(name))
    with owner.engine.begin() as conn:
        conn.execute(text("DROP TRIGGER " + target))
        if owner.engine.dialect.name == "postgresql":
            conn.execute(CreateSchema("guard_drift"))
            function = "guard_drift." + quote(name + "_check")
            conn.execute(text(f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'"))
            table_sql = owner.engine.dialect.identifier_preparer.format_table(owner.tables[table])
            conn.execute(text(f"CREATE TRIGGER {quote(name)} BEFORE INSERT OR UPDATE ON {table_sql} FOR EACH ROW EXECUTE FUNCTION {function}()"))
    with pytest.raises(storage_api.AdapterError, match="migration guard differs"):
        storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=2)


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


def assert_index_lookup(engine, statement, name):
    """Require an actual key seek, never a table or full-index scan."""
    sql = str(
        statement.compile(
            dialect=engine.dialect, compile_kwargs={"literal_binds": True}
        )
    )
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
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
        elif engine.dialect.name == "mysql":
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


def test_lookup_plan_seeks_the_storage_key_on_every_engine(adapters, storage_api):
    owner, runtime, _ = adapters
    request = batch(storage_api)
    runtime.apply(request, runtime.claim(request.scope, "writer"))
    statement = owner.lookup_statement([(e.type, e.id) for e in request.objects[:2]])
    assert_index_lookup(owner.engine, statement, owner.tables["current"].name)


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
    from edgar_warehouse.mdm.clean.evidence import PROFILE_KINDS, assertion
    from edgar_warehouse.mdm.clean.identity import replay
    from edgar_warehouse.mdm.clean.relationships import project, types_of
    from edgar_warehouse.mdm.clean.store import canonical, digest
    from edgar_warehouse.mdm.clean.survivorship import current_claims
    from edgar_warehouse.rules.source_engine import prepare_master_records
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
    policy_digest = digest(policy)
    projected, record_reviews, _ = prepare_master_records({
        "identities": {identity["entity_id"]: identity for identity in identities},
        "canonical": state.canonical, "bindings": state.bindings,
        "quarantined": state.quarantined, "claims": claims, "policy": policy,
        "overrides": state.overrides, "decisions": decisions, "as_of": AS_OF,
        "policy_digest": policy_digest,
        "profile_kinds": {role: sorted(kinds) for role, kinds in PROFILE_KINDS.items()},
    })
    assert not record_reviews
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
