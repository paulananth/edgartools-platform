"""Real PostgreSQL 16 protocol parity and fenced publication from raw inputs."""

import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import payloads
from edgar_warehouse.mdm.clean.store import Conflict, Store, canonical, migrate
from edgar_warehouse.rules import source_engine
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_outbox_names_batch import Destination, journal_policy

postgres = core.postgres
database = core.database


def test_exact_sql_jsonb_bytes_and_hashes_on_numeric_unicode_and_nested_inputs(database):
    rng = random.Random(922016)
    bodies = ['-0', '-0.000', '0e100', '0e-100', '1e131071', '1e-16383',
              '{"x":1,"x":2}', '{"é":1,"bb":2,"𝄞":3,"a":4}',
              json.dumps(['"', '\\', '\b', '\f', '\n', '\t', '\r', '\x01', 'é', '𝄞'], ensure_ascii=False),
              '[' * 512 + '1.2300' + ']' * 512]
    for _ in range(1000):
        number = f"{rng.choice(['', '-'])}{rng.randrange(1, 10**25)}.{rng.randrange(10**12):012}e{rng.randrange(-50, 50):+}"
        bodies.append('{"bbb":[' + number + ',null,true],"a":{"é":"𝄞","x":-0.00}}')
    with database.admin.connect() as conn:
        for body in bodies:
            expected = conn.scalar(text("SELECT CAST(:b AS jsonb)::text"), {"b": body})
            actual = source_engine.postgres_jsonb_text(body)
            assert actual == expected
            assert hashlib.sha256(actual.encode()).hexdigest() == conn.scalar(
                text("SELECT encode(sha256(convert_to(CAST(:b AS jsonb)::text,'UTF8')),'hex')"), {"b": body})


@pytest.mark.parametrize("body", ['"\\u0000"', '"\\ud800"', '[NaN]', '[1,]', '1e131072', '1e-16384',
                                   '0e1073741824', '0e2147483647',
                                   '{"x":"\\u0000","x":1}', '{"x":1e-16384,"x":1}'])
def test_program_and_sql_refuse_invalid_jsonb(database, body):
    with database.admin.begin() as conn, pytest.raises(DBAPIError):
        conn.scalar(text("SELECT CAST(:b AS jsonb)"), {"b": body})
    with pytest.raises(ValueError):
        source_engine.postgres_jsonb_text(body)


def save(database, **changes):
    with database.application.begin() as conn:
        return Store(database.application).commit(conn, core.request(database, **changes), str(uuid4()))


def input_row(database, consumer="export"):
    with database.application.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM mdm.outbox_input WHERE consumer=:c"), {"c": consumer}).mappings().one())


def test_new_inputs_match_old_view_without_numeric_roundtrip(database):
    policy = journal_policy(database)
    # JSON numbers stored by PostgreSQL keep scale even though a normal DBAPI
    # JSON result would convert the value to a binary float and lose that scale.
    request = core.request(database, policy_digest=policy, projections=[{"object_type": "review", "object_id": "numeric",
         "body": {"decimal": 1.23, "tiny": 1e-20, "huge": 10**80, "text": "é𝄞"}}])
    raw = canonical(request).replace('"decimal":1.23', '"decimal":1.2300')
    with database.application.begin() as conn:
        conn.scalar(text("SELECT mdm.save_batch(:r,CAST(:run AS uuid))"), {"r": raw, "run": str(uuid4())})
    with database.admin.connect() as conn:
        for row in conn.execute(text("SELECT * FROM mdm.outbox_input")).mappings():
            expected = conn.scalar(text("SELECT payload::text FROM mdm.outbox_delivery WHERE batch_id=:b AND consumer=:c"),
                                   {"b": row["batch_id"], "c": row["consumer"]})
            assert payloads.payload_text(row) == expected
            assert '1.2300' in payloads.payload_text(row)
            assert payloads.prepare(row) == json.loads(expected)
            assert (row["effects_text"] is not None) == (row["consumer"] == "journal")
    sent = Destination()
    assert Store(database.application).deliver_one("export", "native", sent)


@pytest.mark.parametrize("consumer,corrupt", [
    ("journal", "postgres_jsonb_object_bytes"),  # contract 2: rebuilt by the program
    ("export", "payload_bytes"),                 # contract 3 (018): the database's text, still hashed
])
def test_reconstructed_hash_mismatch_is_refused_before_any_send_and_releases_claim(database, monkeypatch, consumer, corrupt):
    save(database, policy_digest=journal_policy(database))
    sent = Destination()
    monkeypatch.setattr(payloads, corrupt, lambda *_, **__: b'{"corrupt": true}')
    with pytest.raises(Conflict, match="committed payload hash"):
        Store(database.application).deliver_one(consumer, "native", sent)
    assert not sent.sent
    with database.admin.connect() as conn:
        assert conn.scalar(text("SELECT lease_until FROM mdm.outbox WHERE consumer=:c"), {"c": consumer}) is None
        assert conn.scalar(text("SELECT detail->>'error' FROM mdm.outbox_event WHERE event='failed'")) == "Conflict"


def test_generation_order_scope_and_concurrent_claim_share_the_original_fence(database):
    save(database)
    save(database, batch_id="batch-2", expected_generation=1, expected_checkpoint=1, checkpoint=2)
    with database.application.begin() as conn:
        assert conn.scalar(text("SELECT mdm.claim_outbox_input('export','early',300,'batch-2')")) is None
    def claim(owner):
        with database.application.begin() as conn:
            return conn.scalar(text("SELECT mdm.claim_outbox_input('export',:w,300,NULL)"), {"w": owner})
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, ["one", "two"]))
    first, = [c for c in claims if c is not None]
    assert first["batch_id"] == "batch-1"
    with database.admin.begin() as conn:
        conn.execute(text("UPDATE mdm.outbox SET lease_until=clock_timestamp()-interval '1 second' WHERE consumer='export' AND batch_id='batch-1'"))
    # A frozen runtime's old claim API competes against the same row/fence.
    with database.application.begin() as conn:
        later = conn.scalar(text("SELECT mdm.claim_outbox('export','old-runtime',300)"))
    assert later["fence"] == first["fence"] + 1
    assert later["payload"] == payloads.prepare(first)
    with database.application.begin() as conn, pytest.raises(DBAPIError, match="Stale publication fence"):
        conn.execute(text("SELECT mdm.finish_outbox(:b,'export',:f,:h,NULL)"),
                     {"b": first["batch_id"], "f": first["fence"], "h": first["payload_hash"]})


def test_repeated_migration_and_restricted_authority(database):
    assert not migrate(database.admin, application_role="clean_application")["installed"]
    with database.application.begin() as conn, pytest.raises(DBAPIError):
        conn.execute(text("UPDATE mdm.outbox SET payload_hash=repeat('0',64)"))
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT has_function_privilege('public','mdm.claim_outbox_input(text,text,integer,text)','EXECUTE')")) is False


def test_publish_runtime_pins_payload_adapter_facade_and_native_binary():
    from pathlib import Path
    from edgar_warehouse.workers import mdm_publish

    files = set(mdm_publish.runtime_files())
    assert Path(payloads.__file__) in files
    assert set(source_engine.runtime_files()) <= files


def test_journal_still_reports_the_original_conflict_type_before_append(database, monkeypatch):
    from edgar_warehouse.change_journal.store import JournalConflict
    from edgar_warehouse.mdm.clean.journal_delivery import JournalPublisher

    save(database, policy_digest=journal_policy(database))
    row = input_row(database, "journal")
    payload = payloads.prepare(row)
    class NeverAppend:
        def append(self, _):
            raise AssertionError("Invalid preparation must never reach the Journal")
    publisher = JournalPublisher(NeverAppend(), database.application, {"run_id": str(uuid4()), "source": "fixture", "feed": "fixture"})
    monkeypatch.setattr(payloads, "postgres_jsonb_object_bytes", lambda *_, **__: b'{"corrupt": true}')
    with pytest.raises(JournalConflict, match="committed local evidence"):
        publisher.publish("journal/batch-1", payload, row["payload_hash"])


def test_a_populated_015_store_upgrades_without_changing_intent_or_request_hash(postgres, monkeypatch):
    from edgar_warehouse.mdm.clean import store as module

    admin, app = postgres
    with monkeypatch.context() as patch:
        patch.setattr(module, "MIGRATIONS", module.MIGRATIONS[:module.MIGRATIONS.index("016_publication_inputs.sql")])
        patch.setattr(module, "RUNTIME_FUNCTIONS", tuple(f for f in module.RUNTIME_FUNCTIONS
                                                       if f not in ("claim_outbox_input(text,text,integer,text)",
                                                                    "force_publish(text,uuid,bigint,text,text,integer)")))
        database = core.initialize_database(admin, app)
    save(database)
    with database.admin.begin() as conn:
        conn.exec_driver_sql("CREATE ROLE publication_reader LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO publication_reader")
        conn.exec_driver_sql("GRANT SELECT ON mdm.outbox_delivery TO publication_reader")
        # Retain one payload, alongside a hash-only row, as an older store may.
        conn.execute(text("UPDATE mdm.outbox o SET payload=d.payload FROM mdm.outbox_delivery d "
                          "WHERE o.batch_id=d.batch_id AND o.consumer=d.consumer AND o.consumer='export'"))
        before = conn.execute(text("SELECT o.consumer,o.payload::text,o.payload_hash,b.request_hash,b.effects::text "
                                   "FROM mdm.outbox o JOIN mdm.batch b USING(batch_id) ORDER BY consumer")).all()
    assert not migrate(database.admin, application_role="clean_application")["installed"]
    with database.admin.connect() as conn:
        after = conn.execute(text("SELECT o.consumer,o.payload::text,o.payload_hash,b.request_hash,b.effects::text "
                                  "FROM mdm.outbox o JOIN mdm.batch b USING(batch_id) ORDER BY consumer")).all()
        assert conn.scalar(text("SELECT count(*) FROM mdm.migration WHERE name='016_publication_inputs.sql'")) == 1
    assert before == after
    reader = create_engine(admin.url.set(username="publication_reader", password="test"))
    try:
        with reader.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM mdm.outbox_input")) == 2
            assert not conn.scalar(text("SELECT has_function_privilege(current_user,'mdm.claim_outbox_input(text,text,integer,text)','EXECUTE')"))
        with reader.begin() as conn, pytest.raises(DBAPIError):
            conn.execute(text("UPDATE mdm.outbox SET verified_at=now()"))
    finally:
        reader.dispose()
    sink = Destination()
    assert Store(database.application).deliver_one("export", "upgraded", sink)
    assert not Store(database.application).deliver_one("export", "lost-ack-retry", sink)


def test_input_retrieval_uses_the_existing_batch_and_outbox_indexes(database):
    save(database)
    with database.application.begin() as conn:
        conn.execute(text("SET LOCAL enable_seqscan=off"))
        root = conn.scalar(text("EXPLAIN (FORMAT JSON) SELECT * FROM mdm.outbox_input "
                                "WHERE batch_id='batch-1' AND consumer='export'"))[0]["Plan"]
    pending, relations = [root], set()
    while pending:
        node = pending.pop()
        assert node["Node Type"] != "Seq Scan"
        if "Relation Name" in node:
            relations.add(node["Relation Name"])
        pending.extend(node.get("Plans", []))
    assert relations == {"batch", "outbox", "batch_change"}  # 018: the changed records, by key


def test_public_worker_recovers_a_lost_reply_after_durable_publication_without_resending(database, tmp_path, monkeypatch):
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.workers import mdm_publish

    save(database)
    class CountingSink(LocalContractSink):
        sent = 0
        def publish(self, *args):
            self.sent += 1
            return super().publish(*args)
    sink = CountingSink(tmp_path / "consumer")
    store = Store(database.application)
    monkeypatch.setattr(mdm_publish, "_store", lambda **_: store)
    monkeypatch.setattr(mdm_publish, "_publisher", lambda *_: sink)
    deliver = store.deliver_one
    lost = False
    def lose_reply(*args, **kwargs):
        nonlocal lost
        result = deliver(*args, **kwargs)
        if result and not lost:
            lost = True
            raise RuntimeError("Lost publication acknowledgement after commit")
        return result
    monkeypatch.setattr(store, "deliver_one", lose_reply)
    task = {"checks": [mdm_publish.CHECK], "keys": {"batch_id": "batch-1", "consumer": "export"},
            "claim": {"attempt": str(uuid4())}, "output": (tmp_path / "receipt.json").as_uri()}
    artifacts = Artifacts()
    with pytest.raises(RuntimeError, match="after commit"):
        mdm_publish.execute(task, artifacts)
    assert not (tmp_path / "receipt.json").exists()
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT verified_at IS NOT NULL FROM mdm.outbox WHERE consumer='export'"))
    receipt = mdm_publish.execute(task, artifacts)
    assert sink.sent == 1
    assert mdm_publish.verify({**task, "candidate": receipt}, artifacts) == ({mdm_publish.CHECK: True}, [])
    assert mdm_publish.execute(task, artifacts) == receipt
    assert sink.sent == 1
