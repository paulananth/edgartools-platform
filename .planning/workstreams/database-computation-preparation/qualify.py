"""Bounded offline SQL/native publication qualification on a disposable PG16.

LC_ALL=C PG16_SERVER=pgserver uv run --no-sync python <this-file> --limit 600 --output /tmp/publication-600.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import types
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, event, text
import psutil

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from edgar_warehouse.mdm.clean import payloads
from edgar_warehouse.mdm.clean.journal_delivery import JournalPublisher
from edgar_warehouse.mdm.clean.publication import LocalContractSink
from edgar_warehouse.mdm.clean.store import Store, canonical
from edgar_warehouse.rules import source_engine
from edgar_warehouse.workers import mdm_publish
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_clean_outbox_names_batch import journal_policy
from tests.support import pg16
from edgar_warehouse.change_journal.database import migrate as migrate_journal
from edgar_warehouse.change_journal.store import ChangeJournal

BASELINE = "7f1e8856952d574da6a9b13aa6a40bee83139989"
RUN_ID = "00000000-0000-0000-0000-000000000001"


def baseline_journal():
    code = subprocess.run(["git", "show", f"{BASELINE}:edgar_warehouse/mdm/clean/journal_delivery.py"],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout
    module = types.ModuleType("publication_baseline")
    exec(compile(code, "pinned-baseline-journal_delivery.py", "exec"), module.__dict__)
    return module.JournalPublisher


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
    expected = json.loads(mdm_publish.receipt(Store(engine), "batch-1", consumer))
    with engine.connect() as conn:
        payload = conn.scalar(text("SELECT payload FROM mdm.outbox_delivery WHERE batch_id=:b AND consumer=:c"),
                              {"b": "batch-1", "c": consumer})
    sink.verify(f"{consumer}/batch-1", payload, expected["payload_hash"])


def native_verify(engine, consumer, sink):
    expected = json.loads(mdm_publish.receipt(Store(engine), "batch-1", consumer))
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM mdm.outbox_input WHERE batch_id=:b AND consumer=:c"),
                           {"b": "batch-1", "c": consumer}).mappings().one()
    assert row["payload_hash"] == expected["payload_hash"]
    sink.verify(f"{consumer}/{row['batch_id']}", payloads.prepare(row), row["payload_hash"])


def measure(engines, server_process, action):
    calls = {name: 0 for name in engines}
    hooks = {}
    for name, engine in engines.items():
        def count(*_, name=name):
            calls[name] += 1
        event.listen(engine, "before_cursor_execute", count)
        hooks[name] = count
    client = psutil.Process()
    memory = {"client_peak_rss_bytes": 0, "postgres_peak_sum_rss_bytes": 0, "samples": 0}
    def sample():
        memory["client_peak_rss_bytes"] = max(memory["client_peak_rss_bytes"], client.memory_info().rss)
        processes = [server_process, *server_process.children(recursive=True)]
        rss = 0
        for process in processes:
            try:
                rss += process.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        memory["postgres_peak_sum_rss_bytes"] = max(memory["postgres_peak_sum_rss_bytes"], rss)
        memory["samples"] += 1
    stopped = threading.Event()
    failures = []
    def watch():
        try:
            while not stopped.wait(0.01):
                sample()
        except Exception as error:
            failures.append(error)
    sample()
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    started = time.perf_counter()
    try:
        action()
    finally:
        elapsed = time.perf_counter() - started
        stopped.set()
        watcher.join()
        sample()
        for name, engine in engines.items():
            event.remove(engine, "before_cursor_execute", hooks[name])
    if failures:
        raise failures[0]
    return {"seconds": elapsed, "sql_calls": calls, **memory}


def qualify(limit, repeats, mode):
    started = time.perf_counter()
    with pg16.server() as server, tempfile.TemporaryDirectory(prefix="publication-proof-") as folder:
        admin = create_engine(server.url(driver="postgresql"))
        if server.socket is None:
            raise ValueError("Memory qualification requires PG16_SERVER=pgserver")
        server_process = psutil.Process(int((Path(server.socket) / "postmaster.pid").read_text().splitlines()[0]))
        with admin.begin() as conn:
            conn.exec_driver_sql("CREATE ROLE clean_application LOGIN PASSWORD 'test'")
            conn.exec_driver_sql("CREATE ROLE journal_application LOGIN PASSWORD 'test'")
        with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("CREATE DATABASE change_journal_clean")
        app = create_engine(server.url(user="clean_application", driver="postgresql"))
        journal_admin = create_engine(server.url(database="change_journal_clean", driver="postgresql"))
        journal_app = create_engine(server.url(database="change_journal_clean", user="journal_application", driver="postgresql"))
        try:
            migrate_journal(journal_admin, runtime_role="journal_application")
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
                Store(app).commit(conn, request, RUN_ID)
            full = {consumer: [] for consumer in ("export", "journal")}
            journal_type = baseline_journal() if mode == "sql" else JournalPublisher
            sinks = {"export": LocalContractSink(folder),
                     "journal": journal_type(ChangeJournal(journal_app), app,
                         {"run_id": RUN_ID, "source": "fixture", "feed": "fixture"})}
            for n in range(repeats):
                for consumer in (("export", "journal") if n % 2 == 0 else ("journal", "export")):
                    with admin.begin() as conn:
                        conn.execute(text("UPDATE mdm.outbox SET verified_at=NULL,lease_until=NULL,worker=NULL WHERE consumer=:c"), {"c": consumer})
                    sink = sinks[consumer]
                    def action():
                        if mode == "sql":
                            assert old_deliver(app, consumer, sink)
                            old_verify(app, consumer, sink)
                            assert not old_deliver(app, consumer, sink)
                        else:
                            assert Store(app).deliver_one(consumer, "native", sink)
                            native_verify(app, consumer, sink)
                            assert not Store(app).deliver_one(consumer, "native", sink)
                    full[consumer].append(measure({"mdm": app, "journal": journal_app}, server_process, action))
            prepared = {}
            with app.connect() as conn:
                for consumer in ("export", "journal"):
                    row = dict(conn.execute(text("SELECT * FROM mdm.outbox_input WHERE consumer=:c"), {"c": consumer}).mappings().one())
                    expected = conn.scalar(text("SELECT payload::text FROM mdm.outbox_delivery WHERE consumer=:c"), {"c": consumer})
                    expected_bytes = expected.encode()
                    assert payloads.payload_bytes(row) == expected_bytes
                    claim_wire_old = conn.scalar(text("SELECT octet_length((to_jsonb(o)||jsonb_build_object('payload',d.payload))::text) "
                                                    "FROM mdm.outbox o JOIN mdm.outbox_delivery d USING(batch_id,consumer) WHERE consumer=:c"), {"c": consumer})
                    claim_wire_native = conn.scalar(text("SELECT octet_length(((to_jsonb(o)-'payload')||to_jsonb(i))::text) "
                                                       "FROM mdm.outbox o JOIN mdm.outbox_input i USING(batch_id,consumer) WHERE consumer=:c"), {"c": consumer})
                    timings = []
                    for _ in range(repeats):
                        t = time.perf_counter()
                        actual = payloads.payload_bytes(row)
                        timings.append(time.perf_counter() - t)
                        assert actual == expected_bytes
                    prepared[consumer] = {"payload_bytes": len(expected.encode()), "expected_hash": row["payload_hash"],
                                          "native_prepare_seconds": timings, "median_native_prepare_seconds": statistics.median(timings),
                                          "claim_wire_old_bytes": claim_wire_old, "claim_wire_native_bytes": claim_wire_native}
            for consumer in full:
                prepared[consumer][f"median_{mode}_full_seconds"] = statistics.median(r["seconds"] for r in full[consumer])
                prepared[consumer]["client_peak_rss_bytes"] = max(r["client_peak_rss_bytes"] for r in full[consumer])
                prepared[consumer]["postgres_peak_sum_rss_bytes"] = max(r["postgres_peak_sum_rss_bytes"] for r in full[consumer])
            files = [Path(__file__), ROOT / "crates/source-contract/src/postgres_jsonb.rs",
                     ROOT / "edgar_warehouse/mdm/migrations/016_publication_inputs.sql",
                     *mdm_publish.runtime_files()]
            return {"baseline": BASELINE, "limit": limit, "repeats": repeats, "mode": mode,
                    "request_bytes": len(canonical(request).encode()), "preparation": prepared, "full": full,
                    "elapsed_seconds": time.perf_counter() - started,
                    "client_process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
                    "runtime_hashes": {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else p.name:
                                       hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                    "limits": "Each mode uses a separate Python process and disposable PostgreSQL server. Synthetic bounded serial proof. Sampled 10ms RSS; PostgreSQL sum RSS double-counts shared mappings and is not physical unique memory. No production performance/RSS-cap claim."}
        finally:
            journal_app.dispose()
            journal_admin.dispose()
            app.dispose()
            admin.dispose()


def compare(limit, repeats):
    modes = {}
    with tempfile.TemporaryDirectory(prefix="publication-modes-") as directory:
        for mode in ("sql", "native"):
            output = Path(directory) / f"{mode}.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--mode", mode,
                            "--limit", str(limit), "--repeats", str(repeats), "--output", str(output)],
                           check=True, capture_output=True, text=True)
            modes[mode] = json.loads(output.read_text())
    summary = {}
    for consumer in ("export", "journal"):
        old, new = [modes[m]["preparation"][consumer] for m in ("sql", "native")]
        assert old["expected_hash"] == new["expected_hash"]
        checks = {"wall_ratio": new["median_native_full_seconds"] / old["median_sql_full_seconds"],
                  "wire_ratio": new["claim_wire_native_bytes"] / old["claim_wire_old_bytes"],
                  "client_rss_ratio": new["client_peak_rss_bytes"] / old["client_peak_rss_bytes"],
                  "postgres_sum_rss_ratio": new["postgres_peak_sum_rss_bytes"] / old["postgres_peak_sum_rss_bytes"]}
        old_calls = {json.dumps(r["sql_calls"], sort_keys=True) for r in modes["sql"]["full"][consumer]}
        new_calls = {json.dumps(r["sql_calls"], sort_keys=True) for r in modes["native"]["full"][consumer]}
        checks["sql_calls_equal"] = old_calls == new_calls and len(old_calls) == 1
        checks["accepted"] = (checks["wall_ratio"] <= 1.5 and checks["wire_ratio"] <= 1.1
                              and checks["client_rss_ratio"] <= 1.5 and checks["postgres_sum_rss_ratio"] <= 1.5
                              and checks["sql_calls_equal"])
        summary[consumer] = checks
    return {"limit": limit, "repeats": repeats, "baseline": BASELINE, "modes": modes, "acceptance": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--mode", choices=("all", "sql", "native"), default="all")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000 or not 1 <= args.repeats <= 10:
        parser.error("limit must be 1..1000 and repeats 1..10")
    result = compare(args.limit, args.repeats) if args.mode == "all" else qualify(args.limit, args.repeats, args.mode)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"limit": args.limit, "mode": args.mode, "acceptance": result.get("acceptance")}, indent=2))
    if args.mode == "all" and not all(r["accepted"] for r in result["acceptance"].values()):
        raise SystemExit("Publication placement acceptance failed; inspect the preserved evidence")
