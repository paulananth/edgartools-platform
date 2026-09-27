"""Required PG16 acceptance: missing prerequisites FAIL, never skip.

The source fixture tests exercise configured control, not SEC/GLEIF business
parsing or production cutover. No network source requests are made.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import subprocess
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.capabilities import receipt_for, standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, Capability, canonical, digest
from edgar_warehouse.bookkeeping.clean.database import migrate
from edgar_warehouse.bookkeeping.clean.destinations import guard, migrate_guard
from edgar_warehouse.change_journal import ChangeJournal, JournalConflict
from edgar_warehouse.change_journal.database import migrate as migrate_journal
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import Authority, run
from edgar_warehouse.rules.db import Rules, migrate as migrate_rules


@dataclass
class Databases:
    admin: object
    runtime: object
    rules: Rules
    approver: Rules
    ledger: ChangeJournal
    ledger_admin: object
    destination: object
    destination_admin: object
    mdm: object


@pytest.fixture(scope="module")
def databases():
    assert shutil.which("docker"), "PG16 acceptance requires Docker (Colima on macOS)"
    name = f"bookkeeping-acceptance-{uuid4().hex[:10]}"
    subprocess.run(["docker", "image", "inspect", "postgres:16-alpine"], capture_output=True, check=True)
    subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_PASSWORD=test", "postgres:16-alpine"], capture_output=True, check=True)
    engines = []
    try:
        for _ in range(80):
            ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL 16 failed to start")
        port = subprocess.run(["docker", "port", name, "5432/tcp"], capture_output=True, text=True, check=True).stdout.strip().rsplit(":", 1)[1]

        def engine(db, user="postgres"):
            value = create_engine(f"postgresql://{user}:test@127.0.0.1:{port}/{db}", connect_args={"connect_timeout": 5})
            engines.append(value)
            return value

        setup = engine("postgres")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with setup.connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except DBAPIError:
                time.sleep(0.1)
        else:
            pytest.fail("PostgreSQL host connection did not become ready")
        with setup.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for role in ("bk_runtime", "rules_agent", "operator", "ledger_runtime", "destination_runtime", "clean_application"):
                conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
            conn.exec_driver_sql("CREATE ROLE rules_approver NOLOGIN")
            conn.exec_driver_sql("GRANT rules_approver TO operator")
            for db in ("bookkeeping_clean", "rules", "change_journal_clean", "destination"):
                conn.exec_driver_sql(f"CREATE DATABASE {db}")
        admin = engine("bookkeeping_clean")
        runtime = engine("bookkeeping_clean", "bk_runtime")
        rules_admin = engine("rules")
        ledger_admin = engine("change_journal_clean")
        destination_admin = engine("destination")
        migrate(admin, runtime_role="bk_runtime")
        migrate_rules(rules_admin)
        migrate_journal(ledger_admin, runtime_role="ledger_runtime")
        migrate_guard(destination_admin, runtime_role="destination_runtime")
        with destination_admin.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE effects(key text PRIMARY KEY, body jsonb NOT NULL)")
            conn.exec_driver_sql("GRANT SELECT,INSERT ON effects TO destination_runtime")
        from edgar_warehouse.mdm.migrations.runtime import _apply_source_registry_migration
        _apply_source_registry_migration(destination_admin)
        migrate_guard(destination_admin, runtime_role="clean_application")
        yield Databases(admin, runtime, Rules(engine("rules", "rules_agent")), Rules(engine("rules", "operator")),
                        ChangeJournal(engine("change_journal_clean", "ledger_runtime")), ledger_admin,
                        engine("destination", "destination_runtime"), destination_admin, engine("destination", "clean_application"))
    finally:
        for value in engines:
            value.dispose()
        subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True, check=True)


def config(steps=1, *, seconds=120, zero=False, resource="output:{destination}"):
    return {"source": "fixture", "bookkeeping": {"version": 1, "targets": {"silver": {
        "lease_seconds": seconds, "heartbeat_seconds": 1 if seconds<30 else 30,
        "retry": {"attempts": 2, "base_ms": 1, "cap_ms": 2}, "allow_zero_work": zero,
        "steps": [{"name": f"s{i}", "operation": "artifact.copy", "requires": [] if i==0 else [f"s{i-1}"],
                   "key": "{id}", "leases": [resource], "checks": ["input.hash", "output.receipt"]} for i in range(steps)],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}


def submit(databases, tmp_path, count=3, *, body=None, book=None, output_root=None):
    book = book or Bookkeeping(databases.runtime, standard_registry())
    body = body or config()
    name = f"fixture-{uuid4().hex}"
    saved = databases.rules.save("source", name, "1", body)
    artifacts = book.artifacts
    units = []
    for n in range(count):
        source = artifacts.put(tmp_path.as_uri() + "/inputs", {"row": n})
        output = (output_root or tmp_path) / f"output-{n}"
        units.append({"keys": {"id": str(n), "destination": output.as_uri()}, "input": source, "output": output.as_uri(), "cursor": {"offset": n}})
    inputs = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": units})
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    if body.get("mdm"):
        databases.approver.approve("source", name, "1", saved["digest"])
    databases.rules.activate("source", name, "1")
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"test": name})
    return book, rid, inputs, name


def complete(book, rid, key="0", step="s0"):
    claim = book.claim(rid, step, key, sleep=lambda _: None)
    assert claim
    cap = book.registry.operations["artifact.copy"]
    receipt = cap.execute(book, book.item(claim), Authority(claim))
    book.record_verified_completion(claim, receipt)
    return claim, receipt


def expire(databases, claim):
    with databases.admin.begin() as conn:
        conn.execute(text("UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' WHERE attempt=CAST(:a AS uuid)"), {"a": claim.attempt})


def test_exact_five_tables_restricted_runtime_and_migrations(databases):
    with databases.runtime.connect() as conn:
        tables = set(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='bookkeeping'")))
        assert tables == {"pipeline_run", "work_item", "lease", "checkpoint", "journal_outbox"}
        assert str(conn.scalar(text("SHOW server_version"))).startswith("16.")
    migrate(databases.admin, runtime_role="bk_runtime")
    for sql in ("UPDATE bookkeeping.lease SET token=0", "DELETE FROM bookkeeping.pipeline_run",
                "CREATE TABLE bookkeeping.bad(x text)", "SELECT bookkeeping.compact(30)"):
        with pytest.raises(DBAPIError), databases.runtime.begin() as conn:
            conn.execute(text(sql))


def test_pipeline_rules_and_approval_authority(databases, tmp_path):
    body = config()
    body["mdm"] = {"fixture": {"contract": {}}}
    name = "approval-" + uuid4().hex
    saved = databases.rules.save("pipeline", name, "1", body)
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET approved_by='operator',approved_at=clock_timestamp() WHERE name=:n"), {"n": name})
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET body='{}' WHERE name=:n"), {"n": name})
    databases.rules.prove("pipeline", name, "1", {"digest": saved["digest"], "batch_hash": "a"*64, "passed": True})
    with pytest.raises(DBAPIError):
        databases.rules.activate("pipeline", name, "1")
    databases.approver.approve("pipeline", name, "1", saved["digest"])
    databases.rules.activate("pipeline", name, "1")
    ref = databases.rules.resolve("pipeline", name, root=tmp_path.as_uri())
    export = Artifacts().json(ref)
    assert export["approval"]["by"] == "operator"
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET status='draft' WHERE name=:n"), {"n": name})
    with pytest.raises(Blocked):
        databases.rules.save("pipeline", name, "1", {**body, "change": True})
    target = tmp_path / "pipeline.yaml"
    databases.rules.to_file("pipeline", name, "1", target)
    from edgar_warehouse.rules.files import load
    assert digest(load(target)) == saved["digest"]


@pytest.mark.parametrize("damage", ["failed", "truthy", "digest", "batch_hash", "unapproved_operation"])
def test_submission_rejects_invalid_proof_or_unapproved_mastering(databases, tmp_path, damage):
    from copy import deepcopy
    book, rid, inputs, _ = submit(databases, tmp_path)
    rules = book.artifacts.json(book._run(rid)["submission"]["rules"])
    invalid = deepcopy(rules)
    if damage == "failed":
        invalid["proof"]["passed"] = False
    elif damage == "truthy":
        invalid["proof"]["passed"] = "true"
    elif damage == "digest":
        invalid["proof"]["digest"] = "0" * 64
    elif damage == "batch_hash":
        invalid["proof"]["batch_hash"] = "missing"
    else:
        # A mastering operation still requires approval when the document
        # kind is pipeline and its target has a different name.
        invalid["kind"] = "pipeline"
        invalid["body"]["bookkeeping"]["targets"]["silver"]["steps"][0]["operation"] = "mdm.merge"
        invalid["digest"] = digest(invalid["body"])
        invalid["proof"]["digest"] = invalid["digest"]
        book.registry.operation("mdm.merge", book.registry.operations["artifact.copy"])
    ref = book.artifacts.put(tmp_path.as_uri() + "/invalid", invalid)
    proposed = str(uuid4())
    with pytest.raises(Blocked):
        book.start(rules_ref=ref, inputs_ref=inputs, target="silver", scope={}, run_id=proposed)
    with databases.runtime.connect() as conn:
        assert not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM bookkeeping.pipeline_run WHERE run_id=CAST(:r AS uuid))"), {"r": proposed})


def test_two_way_rules_migration_preserves_all_document_digests(databases, tmp_path):
    from edgar_warehouse.rules import files
    version = "roundtrip-" + uuid4().hex
    rows = databases.rules.from_files(files.ROOT, version)
    assert {r["kind"] for r in rows} == {"source", "merge", "pipeline"}
    assert all(r["status"] == "draft" and r["approved_by"] is None for r in rows)
    exported = databases.rules.to_files(tmp_path, version)
    assert {r["digest"] for r in rows} == {r["digest"] for r in exported}
    assert digest(files.policy(tmp_path)) == digest(files.policy())
    for name in ("gleif", "sec.submissions.company"):
        assert digest(files.source(name, tmp_path)) == digest(files.source(name))
    assert digest(files.pipeline("graph-publication", tmp_path)) == digest(files.pipeline("graph-publication"))


def test_invalid_proof_and_unsafe_document_names_refused(databases):
    name = "invalid-proof-" + uuid4().hex
    saved = databases.rules.save("pipeline", name, "1", config())
    for proof in ({"digest": saved["digest"], "batch_hash": None, "passed": True},
                  {"digest": saved["digest"], "batch_hash": "a"*64, "passed": "true"}):
        with pytest.raises(DBAPIError):
            databases.rules.prove("pipeline", name, "1", proof)
    with pytest.raises(Blocked):
        databases.rules.save("pipeline", "../escape", "1", config())
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(text("INSERT INTO rules.rule_version(kind,name,version,body,digest) VALUES('pipeline','../escape','1','{}',:d)"), {"d": digest({})})


def test_full_completion_and_duplicate_delivery(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path)
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"
    assert state["counts"] == {"verified": 3}
    with databases.admin.connect() as conn:
        events = conn.execute(text("SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid)"), {"r": rid}).mappings().all()
    for event in events:
        databases.ledger.append(book.journal_event(event))
        with pytest.raises(JournalConflict):
            databases.ledger.append(book.journal_event({**event, "payload": {**event["payload"], "checks": {"changed": True}}}))
    with databases.ledger_admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM journal.event WHERE run_id=CAST(:r AS uuid)"), {"r": rid}) == 3
    book.resume(rid)
    assert run(book, rid, databases.ledger)["counts"] == {"verified": 3}


def test_out_of_order_and_stage_prerequisites(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, body=config(2))
    assert book.claim(rid, "s1", "0", sleep=lambda _: None) is None
    complete(book, rid, "2")
    assert book.status(rid)["checkpoints"][0]["ordinal"] == -1
    complete(book, rid, "0")
    assert next(c for c in book.status(rid)["checkpoints"] if c["scope"] == "s0")["ordinal"] == 0
    assert book.claim(rid, "s1", "0", sleep=lambda _: None) is None
    complete(book, rid, "1")
    assert next(c for c in book.status(rid)["checkpoints"] if c["scope"] == "s0")["ordinal"] == 2
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"


def staged_submission(databases, tmp_path):
    """Different stage cardinalities and transformed output; no source callback."""
    executions = []
    registry = standard_registry()

    def expected(book, item):
        return book.artifacts.verified(item["unit"]["input"]).upper() + b"|transformed"

    def transform(book, item, authority):
        executions.append(item["unit_key"])
        output = book.artifacts.put_bytes(item["unit"]["output"], expected(book, item))
        return receipt_for(book, item, output)

    def reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        if data != expected(book, item):
            raise Blocked("Transformed output differs from verified input")
        return receipt_for(book, item, book.artifacts.put_bytes(item["unit"]["output"], data))

    def verify(book, item, receipt):
        evidence = book.artifacts.json(receipt["evidence"])
        return (book.artifacts.verified({"uri": receipt["uri"], "sha256": receipt["sha256"]}) == expected(book, item)
                and evidence["input"] == item["unit"]["input"]
                and evidence["output"] == {"uri": receipt["uri"], "sha256": receipt["sha256"]})

    registry.operation("fixture.transform", Capability("1", transform, reconcile, verify))
    book = Bookkeeping(databases.runtime, registry)
    body = config(3)
    steps = body["bookkeeping"]["targets"]["silver"]["steps"]
    for step, name, requires in zip(steps, ("z_capture", "a_transform", "b_finish"),
                                    ([], ["z_capture"], ["a_transform"])):
        step.update(name=name, requires=requires)
    steps[1]["operation"] = "fixture.transform"

    def unit(stage, key, source):
        output = (tmp_path / stage / key).as_uri()
        return {"keys": {"id": key, "destination": output}, "input": source,
                "output": output, "cursor": {"key": key}}

    capture = [unit("capture", f"raw{n}", book.artifacts.put_bytes((tmp_path / f"input{n}").as_uri(),
                f"input-{n}".encode())) for n in range(2)]
    transform_units = [unit("transform", f"parsed{n}", {"from": {"step": "z_capture", "key": f"raw{n % 2}"}})
                       for n in range(3)]
    finish = [unit("finish", "final", {"from": {"step": "a_transform", "key": "parsed2"}})]
    manifest = {"version": 2, "steps": {"z_capture": capture, "a_transform": transform_units, "b_finish": finish}}
    inputs = book.artifacts.put(tmp_path.as_uri() + "/manifests", manifest)
    name = "stages-" + uuid4().hex
    saved = databases.rules.save("pipeline", name, "1", body)
    databases.rules.prove("pipeline", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.rules.activate("pipeline", name, "1")
    rules = databases.rules.resolve("pipeline", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"test": name})
    return book, rid, manifest, executions


def test_stage_inputs_follow_verified_outputs_with_distinct_work_accounting(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    assert book.claim(rid, "a_transform", "parsed0", sleep=lambda _: None) is None
    state = run(book, rid, databases.ledger, limit=3)
    assert state["run"]["expected_count"] == 6
    assert state["counts"]["verified"] == 3
    assert state["run"]["state"] == "waiting"
    assert executions == ["parsed0"]
    assert book.claim(rid, "b_finish", "final", sleep=lambda _: None) is None
    book.resume(rid)
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 6}
    assert executions == ["parsed0", "parsed1", "parsed2"]
    assert book.artifacts.read(manifest["steps"]["b_finish"][0]["output"]) == b"INPUT-0|transformed"
    assert {c["scope"]: c["ordinal"] for c in state["checkpoints"]} == {"z_capture": 1, "a_transform": 2, "b_finish": 0}
    receipt = next(i["receipt"] for i in state["items"] if i["step"] == "b_finish")
    assert book.artifacts.json(receipt["evidence"])["input"]["uri"] == manifest["steps"]["a_transform"][2]["output"]
    with databases.runtime.connect() as conn:
        frozen = conn.scalar(text("SELECT unit->'input' FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step='b_finish'"), {"r": rid})
        assert frozen == {"from": {"step": "a_transform", "key": "parsed2"}}
    book.resume(rid)
    run(book, rid, databases.ledger)
    assert executions == ["parsed0", "parsed1", "parsed2"]


def test_chained_transform_reconciles_lost_ack_before_reexecution(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    run(book, rid, databases.ledger, limit=2)
    claim = book.claim(rid, "a_transform", "parsed0")
    capability = book.registry.operations["fixture.transform"]
    retained = capability.execute(book, book.item(claim), Authority(claim))
    expire(databases, claim)
    book.resume(rid)
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"
    assert executions == ["parsed0", "parsed1", "parsed2"]
    assert next(i["receipt"] for i in state["items"] if i["unit_key"] == "parsed0") == retained


@pytest.mark.parametrize("corruption", ["output", "evidence", "missing_receipt"])
def test_dependency_corruption_blocks_downstream_without_execution(databases, tmp_path, corruption):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    state = run(book, rid, databases.ledger, limit=2)
    upstream = next(i for i in state["items"] if i["step"] == "z_capture" and i["unit_key"] == "raw0")
    if corruption == "missing_receipt":
        with databases.admin.begin() as conn:
            conn.execute(text("UPDATE bookkeeping.work_item SET receipt=NULL WHERE run_id=CAST(:r AS uuid) AND step='z_capture' AND unit_key='raw0'"), {"r": rid})
    else:
        uri = upstream["receipt"]["uri"] if corruption == "output" else upstream["receipt"]["evidence"]["uri"]
        Path(uri.removeprefix("file://")).write_bytes(b"corrupt")
    with pytest.raises(Blocked):
        run(book, rid, databases.ledger)
    assert book.status(rid)["run"]["state"] == "blocked" and executions == []


def test_resume_rechecks_full_dependency_chain_and_blocks_corrupt_intermediate(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    state = run(book, rid, databases.ledger)
    Path(manifest["steps"]["a_transform"][2]["output"].removeprefix("file://")).unlink()
    with pytest.raises(Blocked):
        book.resume(rid)
    assert book.status(rid)["run"]["state"] == "blocked"
    assert executions == ["parsed0", "parsed1", "parsed2"]


def test_independent_concurrency_and_shared_contention(databases, tmp_path):
    first, r1, _, _ = submit(databases, tmp_path / "a", count=1, body=config(resource="shared:resource"))
    second, r2, _, _ = submit(databases, tmp_path / "b", count=1, body=config(resource="shared:resource"))
    independent, r3, _, _ = submit(databases, tmp_path / "c", count=1, body=config(resource="independent:resource"))
    c1 = first.claim(r1, "s0", "0")
    with ThreadPoolExecutor(max_workers=2) as pool:
        blocked = pool.submit(second.claim, r2, "s0", "0", sleep=lambda _: None)
        allowed = pool.submit(independent.claim, r3, "s0", "0")
        assert blocked.result() is None
        c3 = allowed.result()
        assert c3
    assert second.status(r2)["items"][0]["state"] == "waiting"
    first.wait(c1, "yield")
    c2 = second.claim(r2, "s0", "0")
    assert c2.proof[0]["token"] > c1.proof[0]["token"]
    with pytest.raises(DBAPIError):
        first.heartbeat(c1)
    independent.wait(c3, "yield")
    second.wait(c2, "yield")


def test_multiple_resource_contention_rolls_back_acquired_prefix(databases, tmp_path):
    holder, held_run, _, _ = submit(databases, tmp_path / "holder", count=1, body=config(resource="multi:z"))
    held = holder.claim(held_run, "s0", "0")
    body = config()
    body["bookkeeping"]["targets"]["silver"]["steps"][0]["leases"] = ["multi:z", "multi:a"]
    candidate, candidate_run, _, _ = submit(databases, tmp_path / "candidate", count=1, body=body)
    assert candidate.claim(candidate_run, "s0", "0", sleep=lambda _: None) is None
    with databases.runtime.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM bookkeeping.lease WHERE resource='multi:a'")) == 0
    holder.wait(held, "release")
    claim = candidate.claim(candidate_run, "s0", "0")
    assert [p["resource"] for p in claim.proof] == ["multi:a", "multi:z"]
    candidate.wait(claim, "release")


def test_control_commit_expiry_rolls_back_progress_and_outbox(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=config(seconds=2, resource="control:expiry"))
    claim = book.claim(rid, "s0", "0")
    cap = book.registry.operations["artifact.copy"]
    receipt = cap.execute(book, book.item(claim), Authority(claim))
    checks = book.check(rid, claim=claim, receipt=receipt)
    with pytest.raises(DBAPIError), databases.runtime.begin() as conn:
        conn.execute(text("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))"),
                     {"r": rid, "s": claim.step, "k": claim.key, "a": claim.attempt, "p": canonical(claim.proof),
                      "v": canonical(receipt), "c": canonical(checks), "e": str(uuid4())})
        time.sleep(2.1)
    state = book.status(rid)
    assert state["counts"] == {"running": 1} and state["pending_deliveries"] == 0
    book.resume(rid)
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"


def test_renewal_takeover_and_stale_completion(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    old = book.claim(rid, "s0", "0")
    renewed = book.heartbeat(old)
    assert renewed.proof[0]["token"] == old.proof[0]["token"]
    assert renewed.proof[0]["expires_at"] >= old.proof[0]["expires_at"]
    receipt = book.registry.operations["artifact.copy"].execute(book, book.item(old), Authority(old))
    expire(databases, old)
    new = book.claim(rid, "s0", "0")
    assert new.attempt != old.attempt
    with pytest.raises(DBAPIError):
        book.record_verified_completion(old, receipt)
    with pytest.raises(DBAPIError):
        book.wait(old, "stale")
    book.record_verified_completion(new, receipt)
    book.record_verified_completion(new, receipt)  # lost acknowledgement
    assert book.status(rid)["counts"] == {"verified": 1}


def test_worker_automatically_renews_during_execution(databases, tmp_path):
    registry = standard_registry()
    original = registry.operations["artifact.copy"]
    observed = []

    def slow_execute(book, item, authority):
        initial = authority.current().proof[0]["expires_at"]
        time.sleep(3.2)
        observed.append(authority.current().proof[0]["expires_at"] > initial)
        return original.execute(book, item, authority)

    registry.operations["artifact.copy"] = Capability(original.version, slow_execute, original.reconcile, original.verify)
    book = Bookkeeping(databases.runtime, registry)
    book, rid, _, _ = submit(databases, tmp_path, count=1, book=book, body=config(seconds=2, resource="automatic:renewal"))
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    assert observed == [True]


def test_crash_after_destination_before_control_and_reconcile(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    old = book.claim(rid, "s0", "0")
    cap = book.registry.operations["artifact.copy"]
    receipt = cap.execute(book, book.item(old), Authority(old))
    expire(databases, old)
    book.resume(rid)
    original = book.registry.operations["artifact.copy"]
    def must_not_execute(*args):
        raise AssertionError("Committed output must reconcile, not execute twice")
    book.registry.operations["artifact.copy"] = Capability(original.version, must_not_execute, original.reconcile, original.verify)
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"
    assert state["items"][0]["receipt"] == receipt


def test_outbox_atomic_with_progress_and_lost_delivery_ack(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    complete(book, rid)
    with databases.admin.connect() as conn:
        event = conn.execute(text("SELECT * FROM bookkeeping.journal_outbox WHERE run_id=CAST(:r AS uuid)"), {"r": rid}).mappings().one()
    databases.ledger.append(book.journal_event(event))
    assert book.finalize(rid)["run"]["state"] == "waiting"
    assert book.deliver(databases.ledger, rid) == 1
    assert book.finalize(rid)["run"]["state"] == "complete"


def test_journal_failure_and_recovery(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    complete(book, rid)
    class FailingLedger:
        def append(self, *args):
            raise ConnectionError("injected journal outage")
    with pytest.raises(ConnectionError):
        book.deliver(FailingLedger(), rid)
    state = book.finalize(rid)
    assert state["run"]["state"] == "waiting" and state["pending_deliveries"] == 1
    book.deliver(databases.ledger, rid)
    assert book.finalize(rid)["run"]["state"] == "complete"


@pytest.mark.parametrize("damage", ["missing", "corrupt", "version", "receipt"])
def test_resume_blocks_drift_and_bad_evidence(databases, tmp_path, damage):
    book, rid, inputs, _ = submit(databases, tmp_path, count=1)
    if damage == "version":
        cap = book.registry.operations["artifact.copy"]
        book.registry.operations["artifact.copy"] = Capability("2", cap.execute, cap.reconcile, cap.verify)
    elif damage == "receipt":
        _, receipt = complete(book, rid)
        Path(receipt["evidence"]["uri"].removeprefix("file://")).write_text("{}")
    else:
        path = Path(inputs["uri"].removeprefix("file://"))
        if damage == "missing":
            path.unlink()
        else:
            path.write_text("not a manifest")
    with pytest.raises(Blocked):
        book.resume(rid)
    assert book.status(rid)["run"]["state"] == "blocked"


def test_zero_work_explicit_configuration_and_manifest_evidence(databases, tmp_path):
    with pytest.raises(Blocked):
        submit(databases, tmp_path / "no", count=0)
    book, rid, _, _ = submit(databases, tmp_path / "yes", count=0, body=config(zero=True))
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"


def test_destination_transaction_fence_and_expiry_at_commit(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=config(seconds=2, resource="destination:guard"))
    claim = book.claim(rid, "s0", "0")
    key = uuid4().hex
    with pytest.raises(DBAPIError), databases.destination.begin() as conn:
        guard(conn, claim)
        conn.execute(text("INSERT INTO effects VALUES(:k,'{}')"), {"k": key})
        time.sleep(2.1)
    with databases.destination.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM effects WHERE key=:k"), {"k": key}) == 0
    new = book.claim(rid, "s0", "0")
    with databases.destination.begin() as conn:
        guard(conn, new)
        conn.execute(text("INSERT INTO effects VALUES(:k,'{}')"), {"k": key})
    # Same old token, with a fabricated later deadline, still cannot defeat
    # the higher token stored by the destination.
    old_proof = [{**p, "expires_at": new.proof[0]["expires_at"]} for p in claim.proof]
    from dataclasses import replace
    with pytest.raises(DBAPIError), databases.destination.begin() as conn:
        guard(conn, replace(claim, proof=old_proof))
    with pytest.raises(DBAPIError), databases.destination.begin() as conn:
        conn.execute(text("UPDATE bookkeeping_guard.resource SET token=1"))


def test_compaction_retains_receipts_checkpoints_and_tokens(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=config(resource="retention:resource"))
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    with databases.admin.begin() as conn:
        conn.execute(text("UPDATE bookkeeping.pipeline_run SET completed_at=clock_timestamp()-interval '31 days' WHERE run_id=CAST(:r AS uuid)"), {"r": rid})
        assert conn.scalar(text("SELECT bookkeeping.compact(30)")) == 1
    state = book.status(rid)
    assert state["items"] == []
    assert state["run"]["summary"]["receipts"][0]["receipt"]
    assert state["checkpoints"][0]["ordinal"] == 0
    assert state["leases"][0]["token"] >= 1
    with pytest.raises(Blocked):
        book.resume(rid)


def mdm_submission(databases, tmp_path):
    from tests.integration.test_clean_mdm_postgres import initialize_database, source, identity_and_binding, AS_OF
    from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
    from edgar_warehouse.mdm.clean.publication import LocalContractSink

    db = initialize_database(databases.destination_admin, databases.mdm)
    assertion = source("configured-control")
    identity, decision = identity_and_binding(assertion)
    registry = standard_registry()
    register_mdm(registry, databases.mdm, publisher_factory=lambda spec: LocalContractSink(spec["destination"]))
    book = Bookkeeping(databases.runtime, registry)
    body = config(resource="mdm:consumer:{consumer}")
    target = body["bookkeeping"]["targets"].pop("silver")
    body["bookkeeping"]["targets"]["mdm"] = target
    target["steps"][0]["operation"] = "mdm.merge"
    target["checks"].append("mdm.publication")
    with databases.mdm.connect() as conn:
        contract = conn.scalar(text("SELECT body FROM mdm_v2.dataset_mapping WHERE source_code='fixture.primary' ORDER BY mapping_version DESC LIMIT 1"))
    body["mdm"] = {"fixture.primary": {"contract": {k: v for k, v in contract.items() if k != "registry_evidence"}}}
    name = "mdm-" + uuid4().hex
    saved = databases.rules.save("source", name, "1", body)
    payload = {"version": 1, "command": {"batch_id": "mdm-" + uuid4().hex,
        "consumer": "fixture", "expected_checkpoint": 0, "checkpoint": 1,
        "policy_digest": db.policy, "as_of": AS_OF,
        "assertions": [assertion], "identities": [identity], "decisions": [decision]}}
    unit = {"keys": {"id": "0", "consumer": "fixture"},
            "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", payload),
            "output": (tmp_path / "mdm-receipt.json").as_uri(), "cursor": {"offset": 0}}
    inputs = book.artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": [unit]})
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.approver.approve("source", name, "1", saved["digest"])
    databases.rules.activate("source", name, "1", mdm_engine=databases.destination_admin, registry_engine=databases.destination_admin)
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="mdm", scope={"prepared_batch": payload["command"]["batch_id"]})
    return book, rid, payload


def test_actual_mdm_commit_keeps_hash_and_reconciles_lost_ack(databases, tmp_path):
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.mdm.clean.store import Store
    book, rid, payload = mdm_submission(databases, tmp_path)
    claim = book.claim(rid, "s0", "0")
    capability = book.registry.operations["mdm.merge"]
    receipt = capability.execute(book, book.item(claim), Authority(claim))
    with databases.mdm.connect() as conn:
        retained = conn.execute(text("SELECT request_hash,effects FROM mdm_v2.batch WHERE batch_id=:b"), {"b": payload["command"]["batch_id"]}).one()
        assert "lease_proof" not in canonical(retained.effects)
        assert str(conn.scalar(text("SELECT run_id FROM mdm_v2.observation WHERE batch_id=:b"), {"b": payload["command"]["batch_id"]})) == rid
    expire(databases, claim)
    book.resume(rid)
    state = run(book, rid, databases.ledger)
    assert state["counts"] == {"verified": 1} and state["run"]["state"] == "waiting"
    assert state["items"][0]["receipt"] == receipt
    # Existing consumer fences can deliver the exact committed intent. Root
    # completion stays incomplete until both consumers verify their outputs.
    store = Store(databases.mdm)
    for consumer in ("export", "graph"):
        assert store.deliver_one(consumer, "offline-acceptance", LocalContractSink(tmp_path / consumer),
                                 batch_id=payload["command"]["batch_id"])
    assert book.finalize(rid)["run"]["state"] == "complete"
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT request_hash FROM mdm_v2.batch WHERE batch_id=:b"), {"b": payload["command"]["batch_id"]}) == retained.request_hash
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 1


def test_stage_manifest_chains_prepared_mdm_and_separate_publication_intents(databases, tmp_path):
    book, original, payload = mdm_submission(databases, tmp_path)
    body = book.artifacts.json(book._run(original)["submission"]["rules"])["body"]
    target = body["bookkeeping"]["targets"]["mdm"]
    merge = target["steps"][0]
    target["steps"] = [
        {**merge, "name": "archive", "operation": "artifact.copy", "requires": [],
         "leases": ["artifact:{destination}"]},
        {**merge, "name": "merge", "requires": ["archive"]},
        {**merge, "name": "publish", "operation": "mdm.publish", "requires": ["merge"],
         "leases": ["mdm:publication:{consumer}"]},
    ]
    archived = (tmp_path / "archived-command.json").as_uri()
    inputs = book.artifacts.put(tmp_path.as_uri() + "/stage-manifests", {"version": 2, "steps": {
        "archive": [{"keys": {"id": "prepared", "destination": archived},
            "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", payload), "output": archived, "cursor": 0}],
        "merge": [{"keys": {"id": "company", "consumer": "fixture"},
            "input": {"from": {"step": "archive", "key": "prepared"}},
            "output": (tmp_path / "merged.json").as_uri(), "cursor": 0}],
        "publish": [{"keys": {"id": consumer, "consumer": consumer}, "cursor": n,
            "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", {"version": 1,
                "batch_id": payload["command"]["batch_id"], "consumer": consumer, "destination": str(tmp_path / consumer)}),
            "output": (tmp_path / f"{consumer}-receipt.json").as_uri()}
            for n, consumer in enumerate(("export", "graph"))],
    }})
    name = "staged-mdm-" + uuid4().hex
    # The source document owns dataset registration; this is a source pipeline
    # with multiple stages, not a platform job without a dataset contract.
    saved = databases.rules.save("source", name, "1", body)
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.approver.approve("source", name, "1", saved["digest"])
    databases.rules.activate("source", name, "1", mdm_engine=databases.destination_admin, registry_engine=databases.destination_admin)
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="mdm", scope={})
    state = run(book, rid, databases.ledger, limit=2)
    assert state["counts"]["verified"] == 2 and state["run"]["state"] == "waiting"
    assert not state["run"]["checks"]["mdm.publication"]
    book.resume(rid)
    state = run(book, rid, databases.ledger)
    assert state["counts"] == {"verified": 4} and state["run"]["state"] == "complete"
    assert state["run"]["checks"]["mdm.publication"]
    book.resume(rid)
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"


def test_retired_rules_resume_original_export_and_reading(databases, tmp_path):
    book, rid, _ = mdm_submission(databases, tmp_path)
    assert run(book, rid, databases.ledger)["counts"] == {"verified": 1}
    original = book._run(rid)["submission"]
    row = databases.rules.version("source", original["name"], "1")
    body = json.loads(row["body"])
    body["bookkeeping"]["targets"]["mdm"]["lease_seconds"] = 180
    saved = databases.rules.save("source", original["name"], "2", body)
    databases.rules.prove("source", original["name"], "2", {"digest": saved["digest"], "batch_hash": original["inputs"]["sha256"], "passed": True})
    databases.approver.approve("source", original["name"], "2", saved["digest"])
    databases.rules.activate("source", original["name"], "2", mdm_engine=databases.destination_admin, registry_engine=databases.destination_admin)
    assert databases.rules.version("source", original["name"], "1")["status"] == "retired"
    assert book._frozen(rid)[1]["lease_seconds"] == 120
    book.resume(rid)
    assert book._run(rid)["submission"] == original
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT max(mapping_version) FROM mdm_v2.dataset_mapping WHERE source_code='fixture.primary'")) == 1


def test_assessment_writes_reject_expired_authority(databases, tmp_path):
    from edgar_warehouse.mdm.clean import assessment
    from edgar_warehouse.mdm.clean.store import Store
    book, rid, _ = mdm_submission(databases, tmp_path)
    claim = book.claim(rid, "s0", "0")
    store = Store(databases.mdm, lease_authority=Authority(claim))
    expire(databases, claim)
    # Expire destination proof too: a control-only forced expiry cannot be
    # read atomically from an independent business database.
    claim.proof[0]["expires_at"] = "2000-01-01T00:00:00+00:00"
    with pytest.raises(DBAPIError, match="Expired destination authority"):
        assessment.record(store, {"version": 1}, rid)
    with pytest.raises(DBAPIError, match="Expired destination authority"):
        assessment.supersede(store, "missing-assessment", rid)
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.assessment")) == 0


def test_configured_source_ingest_pins_mapping_and_reconciles_lost_ack(databases, tmp_path):
    from copy import deepcopy
    from tests.integration.test_clean_mdm_postgres import initialize_database, identity_and_binding, AS_OF
    from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
    from edgar_warehouse.mdm.clean.adapters import normalize
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.mdm.clean.store import register_dataset, register_policy, Store
    db = initialize_database(databases.destination_admin, databases.mdm)
    code = "unseen.company.v1"
    contract = {"provider": "fixture", "family": "fixture", "schema_version": "1",
                "record_key": "key", "publication_key": "release", "effective_time": "unknown",
                "semantics": "patch", "adapter": {"version": "unseen-1", "kind": "company",
                "record_key": ["key"], "retain_deferred": True, "fields": {"name": "name"}}}
    with databases.destination_admin.begin() as conn:
        policy = register_policy(conn, {"version": 1, "required_consumers": ["export", "graph"],
                                       "automatic_rules": [], "fields": {"company": {"name": {
                                           "sources": [code], "allow_unknown_effective": True}}}})
    registry = standard_registry()
    register_mdm(registry, databases.mdm, publisher_factory=lambda spec: LocalContractSink(spec["destination"]))
    before = set(registry.operations)
    book = Bookkeeping(databases.runtime, registry)
    body = config(resource="mdm:consumer:{consumer}")
    target = body["bookkeeping"]["targets"].pop("silver")
    body["bookkeeping"]["targets"]["mdm"] = target
    target["steps"][0]["operation"] = "mdm.ingest"
    target["checks"].append("mdm.publication")
    body["mdm"] = {code: {"contract": contract}}
    publication = {"publication_key": "release-1", "revision": 1}
    record = {"key": "one", "name": "Configured Company"}
    source = book.artifacts.put_bytes((tmp_path / "source.ndjson").as_uri(), canonical(record).encode() + b"\n")
    prepared = normalize(record, source_code=code, contract=contract, publication={**publication,
        "artifact_sha256": source["sha256"], "member": source["uri"], "record_locator": f"{source['sha256']}:line:1"})
    identity, decision = identity_and_binding(prepared)
    payload = {"version": 1, "source_input": {"source_code": code, "artifact": source,
        "publication": publication, "record_count": 1}, "command": {"batch_id": "ingest-" + uuid4().hex,
        "consumer": "unseen-company", "expected_checkpoint": 0, "checkpoint": 1,
        "policy_digest": policy, "as_of": AS_OF, "identities": [identity], "decisions": [decision]}}
    unit = {"keys": {"id": "0", "consumer": "unseen-company"}, "input": book.artifacts.put(tmp_path.as_uri(), payload),
            "output": (tmp_path / "receipt.json").as_uri(), "cursor": 0}
    inputs = book.artifacts.put(tmp_path.as_uri(), {"version": 1, "units": [unit]})
    name = "unseen-" + uuid4().hex
    saved = databases.rules.save("source", name, "1", body)
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.approver.approve("source", name, "1", saved["digest"])
    databases.rules.activate("source", name, "1", mdm_engine=databases.destination_admin, registry_engine=databases.destination_admin)
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri())
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="mdm", scope={})
    claim = book.claim(rid, "s0", "0")
    capability = registry.operations["mdm.ingest"]
    receipt = capability.execute(book, book.item(claim), Authority(claim))
    # A later correction cannot change the mapping used to reconcile this run.
    corrected = deepcopy(contract)
    corrected["adapter"]["version"] = "unseen-2"
    corrected["adapter"]["fields"]["name"] = "different_name"
    with databases.destination_admin.begin() as conn:
        register_dataset(conn, code, db.registry, corrected)
    expire(databases, claim)
    book.resume(rid)
    state = run(book, rid, databases.ledger)
    assert state["counts"] == {"verified": 1} and state["items"][0]["receipt"] == receipt
    assert set(registry.operations) == before
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 1
        assert conn.scalar(text("SELECT mapping_version FROM mdm_v2.assertion WHERE source_code=:c"), {"c": code}) == 1
        assert conn.scalar(text("SELECT body->'fields'->'name'->>'value' FROM mdm_v2.projection WHERE object_type='entity'")) == record["name"]
    for consumer in ("export", "graph"):
        assert Store(databases.mdm).deliver_one(consumer, "offline", LocalContractSink(tmp_path / consumer))
    assert book.finalize(rid)["run"]["state"] == "complete"
    # Nested source bytes and accounting remain authoritative on fresh runs,
    # even though the enclosing input command has a valid content hash.
    for problem in ("count", "hash", "missing", "consumer"):
        bad = deepcopy(payload)
        bad["command"]["batch_id"] += "-" + problem
        if problem == "count":
            bad["source_input"]["record_count"] = 2
        elif problem == "hash":
            bad["source_input"]["artifact"]["sha256"] = "0" * 64
        elif problem == "missing":
            bad["source_input"]["artifact"]["uri"] = (tmp_path / "missing.ndjson").as_uri()
        else:
            bad["command"]["consumer"] = "unowned-consumer"
        bad_unit = {**unit, "input": book.artifacts.put(tmp_path.as_uri(), bad),
                    "output": (tmp_path / f"{problem}-receipt.json").as_uri()}
        bad_inputs = book.artifacts.put(tmp_path.as_uri(), {"version": 1, "units": [bad_unit]})
        bad_run = book.start(rules_ref=rules, inputs_ref=bad_inputs, target="mdm", scope={})
        with pytest.raises(Blocked):
            run(book, bad_run, databases.ledger)
        assert book.status(bad_run)["run"]["state"] == "blocked"
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.batch")) == 1


def test_configured_platform_publication_failure_and_recovery(databases, tmp_path):
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.bookkeeping.clean.mdm_capabilities import register_mdm
    book, source_run, payload = mdm_submission(databases, tmp_path / "source")
    state = run(book, source_run, databases.ledger)
    assert state["run"]["state"] == "waiting"
    failing = [True]

    class Sink(LocalContractSink):
        def verify(self, *args):
            if failing[0]:
                raise ConnectionError("publication verification outage")
            return super().verify(*args)

    registry = standard_registry()
    register_mdm(registry, databases.mdm, publisher_factory=lambda spec: Sink(spec["destination"]))
    publisher = Bookkeeping(databases.runtime, registry)
    from edgar_warehouse.rules.files import pipeline
    body = pipeline("graph-publication")
    name = "graph-" + uuid4().hex
    saved = databases.rules.save("pipeline", name, "1", body)
    publication = {"version": 1, "batch_id": payload["command"]["batch_id"], "consumer": "graph", "destination": str(tmp_path / "graph")}
    unit = {"keys": {"batch_id": publication["batch_id"], "consumer": "graph"},
            "input": publisher.artifacts.put(tmp_path.as_uri() + "/inputs", publication),
            "output": (tmp_path / "graph-receipt.json").as_uri(), "cursor": 0}
    inputs = publisher.artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": [unit]})
    databases.rules.prove("pipeline", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.rules.activate("pipeline", name, "1")
    rules = databases.rules.resolve("pipeline", name, root=tmp_path.as_uri() + "/rules")
    rid = publisher.start(rules_ref=rules, inputs_ref=inputs, target="publish", scope={})
    with pytest.raises(ConnectionError):
        run(publisher, rid, databases.ledger)
    assert publisher.status(rid)["counts"] == {"waiting": 1}
    failing[0] = False
    publisher.resume(rid)
    assert run(publisher, rid, databases.ledger)["run"]["state"] == "complete"
    with databases.mdm.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm_v2.publication_event WHERE batch_id=:b AND consumer='graph' AND event='verified'"), {"b": publication["batch_id"]}) == 1
    assert book.finalize(source_run)["run"]["state"] == "waiting"  # export still absent


def test_unseen_source_configuration_only(databases, tmp_path):
    from edgar_warehouse.rules.files import loads
    body = loads('''source: unseen.calendar\nbookkeeping:\n  version: 1\n  targets:\n    silver:\n      steps:\n        - name: archive\n          operation: artifact.copy\n          requires: []\n          key: "{id}"\n          leases: ["calendar:{destination}"]\n          checks: [input.hash, output.receipt]\n      checks: [manifest.hash, work.accounting, journal.delivered]\n''')
    book, rid, _, _ = submit(databases, tmp_path, body=body)
    before = set(book.registry.operations)
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    assert before == set(book.registry.operations)


def test_operator_cli_submits_and_resumes_frozen_work(databases, tmp_path, monkeypatch, capsys):
    from edgar_warehouse.cli import main
    _, _, inputs, name = submit(databases, tmp_path)
    monkeypatch.setenv("BOOKKEEPING_CLEAN_DATABASE_URL", databases.runtime.url.render_as_string(hide_password=False))
    monkeypatch.setenv("RULES_DATABASE_URL", databases.rules.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CHANGE_JOURNAL_DATABASE_URL", databases.ledger.engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("BOOKKEEPING_MANIFEST_ROOT", (tmp_path / "cli-manifests").as_uri())
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    assert main(["rules", "run", "--source", name, "--target", "silver",
                 "--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"], "--limit", "1"]) == 3
    first = json.loads(capsys.readouterr().out)
    rid = first["run"]["run_id"]
    frozen = first["run"]["submission"]
    assert first["counts"] == {"pending": 2, "verified": 1}
    assert main(["rules", "run", "--source", name, "--target", "silver", "--resume-run-id", rid, "--limit", "100"]) == 0
    completed = json.loads(capsys.readouterr().out)
    assert completed["run"]["submission"] == frozen and completed["counts"] == {"verified": 3}
    assert main(["bookkeeping", "status", rid]) == 0
    assert json.loads(capsys.readouterr().out)["pending_deliveries"] == 0
    assert main(["bookkeeping", "checks", rid]) == 0
    assert all(json.loads(capsys.readouterr().out).values())
    assert main(["bookkeeping", "runs", "--state", "complete", "--limit", "100"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert any(row["run_id"] == rid for row in listed)
    assert len(listed) <= 100 and all(row["state"] == "complete" for row in listed)


def test_source_configs_use_same_control_contract():
    from edgar_warehouse.rules.files import source
    from edgar_warehouse.bookkeeping.clean.config import validate
    registry = standard_registry()
    from edgar_warehouse.change_journal.capture import register_capture
    register_capture(registry, None)
    for name in ("gleif", "sec.submissions.company"):
        selected = validate(source(name), "capture", registry)
        assert selected["lease_seconds"] == 120 and selected["heartbeat_seconds"] == 30


def test_provisioning_uses_nologin_owners_and_empty_stores(monkeypatch):
    import runpy
    name = f"bookkeeping-provision-{uuid4().hex[:10]}"
    subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_PASSWORD=test", "postgres:16-alpine"], capture_output=True, check=True)
    engines = []
    try:
        port = subprocess.run(["docker", "port", name, "5432/tcp"], capture_output=True, text=True, check=True).stdout.strip().rsplit(":", 1)[1]
        url = f"postgresql://postgres:test@127.0.0.1:{port}/postgres"
        admin = create_engine(url, connect_args={"connect_timeout": 3})
        engines.append(admin)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with admin.connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except DBAPIError:
                time.sleep(0.1)
        else:
            pytest.fail("Provisioning acceptance PostgreSQL unavailable")
        monkeypatch.setenv("BOOKKEEPING_CLEAN_RUNTIME_PASSWORD", "test")
        monkeypatch.setenv("RULES_AGENT_PASSWORD", "test")
        script = Path(__file__).parents[2] / "infra/scripts/provision-clean-bookkeeping.py"
        provision = runpy.run_path(str(script))["provision"]
        monkeypatch.setenv("CHANGE_JOURNAL_RUNTIME_PASSWORD", "test")
        result = provision(url, rules=True, journal=True)
        assert set(result) == {"bookkeeping_clean", "rules", "change_journal_clean"}
        assert provision(url, rules=True, journal=True) == result
        for database, role, table in (("bookkeeping_clean", "bookkeeping_clean_runtime", "bookkeeping.pipeline_run"),
                                      ("rules", "rules_agent", "rules.rule_version")):
            runtime = create_engine(f"postgresql://{role}:test@127.0.0.1:{port}/{database}")
            engines.append(runtime)
            with runtime.connect() as conn:
                assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(f"DELETE FROM {table}"))
        journal_admin = create_engine(f"postgresql://postgres:test@127.0.0.1:{port}/change_journal_clean")
        engines.append(journal_admin)
        with journal_admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM journal.event")) == 0
            assert conn.scalars(text("SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")).all() == ["journal.event"]
        with admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname IN ('rules_owner','bookkeeping_clean_owner','change_journal_owner') AND NOT rolcanlogin AND NOT rolsuper")) == 3
    finally:
        for engine in engines:
            engine.dispose()
        subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True, check=True)
