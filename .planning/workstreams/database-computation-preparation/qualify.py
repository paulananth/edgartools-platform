"""Bounded offline SQL/native publication qualification on a disposable PG16.

LC_ALL=C PG16_SERVER=pgserver uv run --no-sync python <this-file> --limit 600 --output /tmp/publication-600.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from edgar_warehouse.mdm.clean import payloads
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import Store, canonical
from edgar_warehouse.rules import source_engine
from edgar_warehouse.workers import mdm_publish
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_outbox_names_batch import journal_policy
from tests.support import pg16


def old_deliver(engine, consumer, sink):
    with engine.begin() as conn:
        claim = conn.scalar(text("SELECT mdm.claim_outbox(:c,'baseline',300)"), {"c": consumer})
    if claim is None:
        return False
    key = f"{consumer}/{claim['batch_id']}"
    sink.publish(key, claim["payload"], claim["payload_hash"])
    verified = sink.verify(key, claim["payload"], claim["payload_hash"])
    with engine.begin() as conn:
        conn.execute(text("SELECT mdm.finish_outbox(:b,:c,:f,:h,NULL)"),
                     {"b": claim["batch_id"], "c": consumer, "f": claim["fence"], "h": verified})
    return True


def old_verify(engine, consumer, sink):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT d.*,o.payload_hash,encode(sha256(convert_to(d.payload::text,'UTF8')),'hex') AS actual_hash "
                                "FROM mdm.outbox_delivery d JOIN mdm.outbox o USING(batch_id,consumer) WHERE consumer=:c"),
                           {"c": consumer}).mappings().one()
    assert row["actual_hash"] == row["payload_hash"]
    sink.verify(f"{consumer}/{row['batch_id']}", row["payload"], row["payload_hash"])


def native_verify(engine, consumer, sink):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM mdm.outbox_input WHERE consumer=:c"), {"c": consumer}).mappings().one()
    sink.verify(f"{consumer}/{row['batch_id']}", payloads.prepare(row), row["payload_hash"])


def measure(engine, action):
    calls = 0
    def count(*_):
        nonlocal calls
        calls += 1
    event.listen(engine, "before_cursor_execute", count)
    started = time.perf_counter()
    try:
        action()
    finally:
        elapsed = time.perf_counter() - started
        event.remove(engine, "before_cursor_execute", count)
    return {"seconds": elapsed, "sql_calls": calls}


def qualify(limit, repeats):
    started = time.perf_counter()
    with pg16.server() as server, tempfile.TemporaryDirectory(prefix="publication-proof-") as folder:
        admin = create_engine(server.url(driver="postgresql"))
        with admin.begin() as conn:
            conn.exec_driver_sql("CREATE ROLE clean_application LOGIN PASSWORD 'test'")
        app = create_engine(server.url(user="clean_application", driver="postgresql"))
        try:
            db = core.initialize_database(admin, app)
            policy = journal_policy(db)
            projections = [{"object_type": "review", "object_id": str(n), "body": {
                "name": f"Company {n} é𝄞", "fields": {
                    f"field_{i}": {"value": ("qualified raw payload " * 12) + str(n),
                                   "winner": {"source_code": "fixture.primary", "record_key": str(n)},
                                   "conflicts": [], "numeric": 1e-20}
                    for i in range(12)}}} for n in range(limit)]
            request = core.request(db, policy_digest=policy, projections=projections)
            with app.begin() as conn:
                Store(app).commit(conn, request, str(uuid4()))
            prepared = {}
            with app.connect() as conn:
                for consumer in ("export", "journal"):
                    row = dict(conn.execute(text("SELECT * FROM mdm.outbox_input WHERE consumer=:c"), {"c": consumer}).mappings().one())
                    expected = conn.scalar(text("SELECT payload::text FROM mdm.outbox_delivery WHERE consumer=:c"), {"c": consumer})
                    assert payloads.payload_text(row) == expected
                    claim_wire_old = conn.scalar(text("SELECT octet_length((to_jsonb(o)||jsonb_build_object('payload',d.payload))::text) "
                                                    "FROM mdm.outbox o JOIN mdm.outbox_delivery d USING(batch_id,consumer) WHERE consumer=:c"), {"c": consumer})
                    claim_wire_native = conn.scalar(text("SELECT octet_length(((to_jsonb(o)-'payload')||to_jsonb(i))::text) "
                                                       "FROM mdm.outbox o JOIN mdm.outbox_input i USING(batch_id,consumer) WHERE consumer=:c"), {"c": consumer})
                    timings = []
                    for _ in range(repeats):
                        t = time.perf_counter()
                        assert payloads.payload_text(row) == expected
                        timings.append(time.perf_counter() - t)
                    prepared[consumer] = {"payload_bytes": len(expected.encode()), "expected_hash": row["payload_hash"],
                                          "native_prepare_seconds": timings, "median_native_prepare_seconds": statistics.median(timings),
                                          "claim_wire_old_bytes": claim_wire_old, "claim_wire_native_bytes": claim_wire_native}
            full = {consumer: {"sql": [], "native": []} for consumer in ("export", "journal")}
            sink = LocalContractSink(folder)
            for n in range(repeats):
                for consumer in full:
                    for mode in (("sql", "native") if n % 2 == 0 else ("native", "sql")):
                        with admin.begin() as conn:
                            conn.execute(text("UPDATE mdm.outbox SET verified_at=NULL,lease_until=NULL,worker=NULL WHERE consumer=:c"), {"c": consumer})
                        def action():
                            if mode == "sql":
                                assert old_deliver(app, consumer, sink)
                                old_verify(app, consumer, sink)
                                assert not old_deliver(app, consumer, sink)
                            else:
                                assert Store(app).deliver_one(consumer, "native", sink)
                                native_verify(app, consumer, sink)
                                assert not Store(app).deliver_one(consumer, "native", sink)
                        full[consumer][mode].append(measure(app, action))
            for consumer in full:
                for mode in full[consumer]:
                    prepared[consumer][f"median_{mode}_full_seconds"] = statistics.median(r["seconds"] for r in full[consumer][mode])
            files = [Path(__file__), ROOT / "crates/source-contract/src/postgres_jsonb.rs",
                     ROOT / "edgar_warehouse/mdm/migrations/016_publication_inputs.sql",
                     *mdm_publish.runtime_files()]
            return {"baseline": "7f1e8856952d574da6a9b13aa6a40bee83139989", "limit": limit, "repeats": repeats,
                    "request_bytes": len(canonical(request).encode()), "preparation": prepared, "full": full,
                    "elapsed_seconds": time.perf_counter() - started,
                    "combined_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
                    "runtime_hashes": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
                                       hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                    "limits": "Synthetic bounded local serial proof; combined-process RSS, not per-engine memory or production performance."}
        finally:
            app.dispose()
            admin.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 1 <= args.repeats <= 10:
        parser.error("limit must be 1..1000 and repeats 1..10")
    result = qualify(args.limit, args.repeats)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"limit": args.limit, "elapsed_seconds": result["elapsed_seconds"], "preparation": result["preparation"]}, indent=2))
