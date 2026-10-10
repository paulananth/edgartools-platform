"""Required PG16 acceptance: missing prerequisites FAIL, never skip.

The source fixture tests exercise configured control, not SEC/GLEIF business
parsing or production cutover. No network source requests are made.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from edgar_warehouse.bookkeeping.clean.database import grant_profile, migrate
from edgar_warehouse.bookkeeping.clean.destinations import guard, migrate_guard
from edgar_warehouse.change_journal import ChangeJournal, JournalConflict
from edgar_warehouse.change_journal.database import migrate as migrate_journal
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.rules.db import Rules, migrate as migrate_rules
from edgar_warehouse.workers import copy
from tests.support import pg16
from tests.support.bookkeeping_protocol import RUNTIME, complete, drive, verification_for, verification_report
from tests.support.rules_approval import approve


PROFILES = ("artifact.copy", "jsonl.count", "fixture.transform")


@dataclass
class Databases:
    admin: object
    runtime: object
    verifier: object
    rules: Rules
    approver: Rules
    ledger: ChangeJournal
    ledger_admin: object
    destination: object
    destination_admin: object
    mdm: object


@pytest.fixture(scope="module")
def databases():
    # Docker in CI; PG16_SERVER=pgserver runs on a local PostgreSQL 16 (tests/support/pg16.py).
    with pg16.server() as server:
        engines = []
        try:
            def engine(db, user="postgres"):
                value = create_engine(server.url(db, user, driver="postgresql"), connect_args={"connect_timeout": 5})
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
                for role in ("bk_runtime", "bk_verifier", "rules_agent", "operator", "ledger_runtime", "destination_runtime", "clean_application"):
                    conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
                # Control's grants go to one group; the worker (bk_runtime) and the
                # verifier (bk_verifier) log in separately (mastering to-do 20b).
                conn.exec_driver_sql("CREATE ROLE bk_control NOLOGIN")
                conn.exec_driver_sql("GRANT bk_control TO bk_runtime, bk_verifier")
                conn.exec_driver_sql("CREATE ROLE rules_approver NOLOGIN")
                conn.exec_driver_sql("GRANT rules_approver TO operator")
                for db in ("bookkeeping_clean", "rules", "change_journal_clean", "destination"):
                    conn.exec_driver_sql(f"CREATE DATABASE {db}")
            admin = engine("bookkeeping_clean")
            runtime = engine("bookkeeping_clean", "bk_runtime")
            rules_admin = engine("rules")
            ledger_admin = engine("change_journal_clean")
            destination_admin = engine("destination")
            with pytest.raises(Blocked, match="not initialized"):
                migrate(admin, runtime_role="bk_control", existing_only=True)
            with pytest.raises(Blocked, match="not initialized"):
                migrate_journal(ledger_admin, runtime_role="ledger_runtime", existing_only=True)
            migrate(admin, runtime_role="bk_control")
            for profile in PROFILES:
                grant_profile(admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
            migrate_rules(rules_admin)
            migrate_journal(ledger_admin, runtime_role="ledger_runtime")
            migrate_guard(destination_admin, runtime_role="destination_runtime")
            with destination_admin.begin() as conn:
                conn.exec_driver_sql("CREATE TABLE effects(key text PRIMARY KEY, body jsonb NOT NULL)")
                conn.exec_driver_sql("GRANT SELECT,INSERT ON effects TO destination_runtime")
            migrate_guard(destination_admin, runtime_role="clean_application")
            yield Databases(admin, runtime, engine("bookkeeping_clean", "bk_verifier"), Rules(engine("rules", "rules_agent")), Rules(engine("rules", "operator")),
                            ChangeJournal(engine("change_journal_clean", "ledger_runtime")), ledger_admin,
                            engine("destination", "destination_runtime"), destination_admin, engine("destination", "clean_application"))
        finally:
            for value in engines:
                value.dispose()


def config(steps=1, *, seconds=120, zero=False, resource="output:{destination}"):
    return {"source": "fixture", "bookkeeping": {"version": 1, "targets": {"silver": {
        "lease_seconds": seconds, "heartbeat_seconds": 1 if seconds<30 else 30,
        "retry": {"attempts": 2, "base_ms": 1, "cap_ms": 2}, "allow_zero_work": zero,
        "steps": [{"name": f"s{i}", "operation": "artifact.copy", "requires": [] if i==0 else [f"s{i-1}"],
                   "key": "{id}", "leases": [resource], "checks": ["input.hash", "output.receipt"]} for i in range(steps)],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}


def approved_acquisition(body, name, contracts, manifest):
    """Attach a bounded fixture feed to an MDM Rules source document."""
    body["source"] = name
    body["acquisition"] = {"version": 1, "feeds": {"fixture": {
        "family": "fixture", "datasets": list(contracts), "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
        "required_producers": ["fixture"], "url_prefixes": ["https://fixture.invalid/"],
    }}}
    return {"fixture": {"manifest": manifest, "counts": {"fixture": {"expected": 0, "verified": 0}},
                        "checks": {"fixture": True}}}


def submit(databases, tmp_path, count=3, *, body=None, book=None, output_root=None, cursor=None):
    book = book or Bookkeeping(databases.runtime)
    if not hasattr(book, "verifier"):
        book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    body = body or config()
    name = f"fixture-{uuid4().hex}"
    saved = databases.rules.save("source", name, "1", body)
    artifacts = book.artifacts
    units = []
    for n in range(count):
        source = artifacts.put(tmp_path.as_uri() + "/inputs", {"row": n})
        output = (output_root or tmp_path) / f"output-{n}"
        units.append({"keys": {"id": str(n), "destination": output.as_uri()}, "input": source, "output": output.as_uri(),
                      "cursor": cursor(n) if cursor else {"offset": n}})
    inputs = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": units})
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    if body.get("mdm"):
        approve(databases.approver, "source", name, "1")
    databases.rules.activate("source", name, "1")
    rules = databases.rules.resolve("source", name, root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"test": name})
    return book, rid, inputs, name


def expire(databases, claim):
    with databases.admin.begin() as conn:
        conn.execute(text("UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' WHERE attempt=CAST(:a AS uuid)"), {"a": claim.attempt})


def test_exact_five_tables_restricted_runtime_and_migrations(databases):
    with databases.runtime.connect() as conn:
        tables = set(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='bookkeeping'")))
        assert tables == {"pipeline_run", "work_item", "lease", "checkpoint", "journal_outbox"}
        assert str(conn.scalar(text("SHOW server_version"))).startswith("16.")
    migrate(databases.admin, runtime_role="bk_control")
    for sql in ("UPDATE bookkeeping.lease SET token=0", "DELETE FROM bookkeeping.pipeline_run",
                "CREATE TABLE bookkeeping.bad(x text)", "SELECT bookkeeping.compact(30)"):
        with pytest.raises(DBAPIError), databases.runtime.begin() as conn:
            conn.execute(text(sql))


def test_bookkeeping_cli_init_and_migrate_use_owner_and_preserve_empty_control(databases, monkeypatch, capsys):
    from edgar_warehouse.cli import main

    monkeypatch.setenv(
        "BOOKKEEPING_CLEAN_MIGRATION_DATABASE_URL",
        databases.admin.url.render_as_string(hide_password=False),
    )
    assert main(["bookkeeping", "init", "--runtime-role", "bk_control"]) == 0
    assert "001_control.sql" in capsys.readouterr().out
    assert main(["bookkeeping", "migrate", "--runtime-role", "bk_control"]) == 0
    assert "001_control.sql" in capsys.readouterr().out
    with databases.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run")) == 0
        assert conn.scalar(text("SELECT count(*) FROM bookkeeping.work_item")) == 0


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
    approve(databases.approver, "pipeline", name, "1")
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
        invalid["body"]["mdm"] = {"fixture": {"contract": {}}}
        invalid["digest"] = digest(invalid["body"])
        invalid["proof"]["digest"] = invalid["digest"]
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
    with pytest.raises(DBAPIError):  # the database refuses an unpinned batch
        databases.rules.prove("pipeline", name, "1", {"digest": saved["digest"], "batch_hash": None, "passed": True})
    with pytest.raises(Blocked, match="whether it passed"):
        databases.rules.prove("pipeline", name, "1", {"digest": saved["digest"], "batch_hash": "a"*64, "passed": "true"})
    with pytest.raises(Blocked):
        databases.rules.save("pipeline", "../escape", "1", config())
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(text("INSERT INTO rules.rule_version(kind,name,version,body,digest) VALUES('pipeline','../escape','1','{}',:d)"), {"d": digest({})})


def test_full_completion_and_duplicate_delivery(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path)
    state = drive(book, rid, databases.ledger)
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
    assert drive(book, rid, databases.ledger)["counts"] == {"verified": 3}


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
    state = drive(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"


def staged_submission(databases, tmp_path):
    """Different stage cardinalities and transformed output; no source callback."""
    executions = []

    class Transform:
        """A worker the control code has never seen; adding it changes
        nothing in Bookkeeping."""
        @staticmethod
        def expected(envelope, artifacts):
            return artifacts.verified(envelope["input"]).upper() + b"|transformed"

        @classmethod
        def execute(cls, envelope, artifacts):
            data = cls.expected(envelope, artifacts)
            try:  # reconcile an earlier attempt's effect before writing again
                if artifacts.read(envelope["output"]) == data:
                    return artifacts.put_bytes(envelope["output"], data)
            except Blocked:
                pass
            executions.append(envelope["claim"]["key"])
            return artifacts.put_bytes(envelope["output"], data)

        @classmethod
        def verify(cls, envelope, artifacts):
            if artifacts.verified(envelope["candidate"]) != cls.expected(envelope, artifacts):
                raise ValueError("Transformed output differs from verified input")
            return {name: True for name in envelope["checks"]}, []

    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
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
    book.workers = {"artifact.copy": copy, "fixture.transform": Transform}
    return book, rid, manifest, executions


def test_stage_inputs_follow_verified_outputs_with_distinct_work_accounting(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    assert book.claim(rid, "a_transform", "parsed0", sleep=lambda _: None) is None
    state = drive(book, rid, databases.ledger, workers=book.workers, limit=3)
    assert state["run"]["expected_count"] == 6
    assert state["counts"]["verified"] == 3
    assert state["run"]["state"] == "waiting"
    assert executions == ["parsed0"]
    assert book.claim(rid, "b_finish", "final", sleep=lambda _: None) is None
    book.resume(rid)
    state = drive(book, rid, databases.ledger, workers=book.workers)
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 6}
    assert executions == ["parsed0", "parsed1", "parsed2"]
    assert book.artifacts.read(manifest["steps"]["b_finish"][0]["output"]) == b"INPUT-0|transformed"
    assert {c["scope"]: c["ordinal"] for c in state["checkpoints"]} == {"z_capture": 1, "a_transform": 2, "b_finish": 0}
    receipt = next(i["receipt"] for i in state["items"] if i["step"] == "b_finish")
    assert book.artifacts.verified({"uri": receipt["uri"], "sha256": receipt["sha256"]}) == b"INPUT-0|transformed"
    assert book.artifacts.json(receipt["evidence"])["binding"]["step"] == "b_finish"
    with databases.runtime.connect() as conn:
        frozen = conn.scalar(text("SELECT unit->'input' FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step='b_finish'"), {"r": rid})
        assert frozen == {"from": {"step": "a_transform", "key": "parsed2"}}
    book.resume(rid)
    drive(book, rid, databases.ledger, workers=book.workers)
    assert executions == ["parsed0", "parsed1", "parsed2"]


def test_chained_transform_reconciles_lost_ack_before_reexecution(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    drive(book, rid, databases.ledger, workers=book.workers, limit=2)
    claim = book.claim(rid, "a_transform", "parsed0")
    retained = book.workers["fixture.transform"].execute(book.envelope(claim), book.artifacts)
    expire(databases, claim)
    book.resume(rid)
    state = drive(book, rid, databases.ledger, workers=book.workers)
    assert state["run"]["state"] == "complete"
    assert executions == ["parsed0", "parsed1", "parsed2"]
    receipt = next(i["receipt"] for i in state["items"] if i["unit_key"] == "parsed0")
    assert {"uri": receipt["uri"], "sha256": receipt["sha256"]} == retained


@pytest.mark.parametrize("corruption", ["output", "evidence", "missing_receipt"])
def test_dependency_corruption_blocks_downstream_without_execution(databases, tmp_path, corruption):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    state = drive(book, rid, databases.ledger, workers=book.workers, limit=2)
    upstream = next(i for i in state["items"] if i["step"] == "z_capture" and i["unit_key"] == "raw0")
    if corruption == "missing_receipt":
        with databases.admin.begin() as conn:
            conn.execute(text("UPDATE bookkeeping.work_item SET receipt=NULL WHERE run_id=CAST(:r AS uuid) AND step='z_capture' AND unit_key='raw0'"), {"r": rid})
    else:
        uri = upstream["receipt"]["uri"] if corruption == "output" else upstream["receipt"]["evidence"]["uri"]
        Path(uri.removeprefix("file://")).write_bytes(b"corrupt")
    with pytest.raises(Blocked):
        drive(book, rid, databases.ledger, workers=book.workers)
    assert book.status(rid)["run"]["state"] == "blocked" and executions == []


def test_resume_rechecks_full_dependency_chain_and_blocks_corrupt_intermediate(databases, tmp_path):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    state = drive(book, rid, databases.ledger, workers=book.workers)
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
    envelope = book.envelope(claim)
    candidate = copy.execute(envelope, book.artifacts)
    book.report(envelope, candidate, RUNTIME)
    report = verification_report(book, verification_for(book, rid, "s0", "0"), copy)
    receipt = {**candidate, "evidence": report}
    checks = {"input.hash": True, "output.receipt": True}
    with pytest.raises(DBAPIError), databases.runtime.begin() as conn:
        conn.execute(text("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))"),
                     {"r": rid, "s": claim.step, "k": claim.key, "a": claim.attempt, "p": canonical(claim.proof),
                      "v": canonical(receipt), "c": canonical(checks), "e": str(uuid4())})
        time.sleep(2.1)
    state = book.status(rid)
    assert state["counts"] == {"reported": 1} and state["pending_deliveries"] == 0
    book.resume(rid)
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"


def test_renewal_takeover_and_stale_completion(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    old = book.claim(rid, "s0", "0")
    renewed = book.heartbeat(old)
    assert renewed.proof[0]["token"] == old.proof[0]["token"]
    assert renewed.proof[0]["expires_at"] >= old.proof[0]["expires_at"]
    stale = book.envelope(old)
    candidate = copy.execute(stale, book.artifacts)
    expire(databases, old)
    new = book.claim(rid, "s0", "0")
    assert new.attempt != old.attempt
    with pytest.raises(DBAPIError):
        book.report(stale, candidate, RUNTIME)
    with pytest.raises(DBAPIError):
        book.wait(old, "stale")
    envelope = book.envelope(new)
    book.report(envelope, candidate, RUNTIME)
    book.report(envelope, candidate, RUNTIME)  # lost acknowledgement
    verification = verification_for(book, rid, "s0", "0")
    report = verification_report(book, verification, copy)
    book.verifier.admit(verification, report)
    book.verifier.admit(verification, report)  # lost acknowledgement
    assert book.status(rid)["counts"] == {"verified": 1}
    other = book.artifacts.put(tmp_path.as_uri() + "/other-reports", {"other": True})
    with pytest.raises(Blocked, match="changed"):
        book.verifier.admit(verification, other)


def test_worker_renews_during_execution(databases, tmp_path, monkeypatch):
    """The worker runner keeps its lease alive while slow work runs."""
    from edgar_warehouse.workers import __main__ as runner, control
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=config(seconds=2, resource="automatic:renewal"))
    monkeypatch.setattr(control, "renew", book.renew)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    initial = envelope["claim"]["proof"][0]["expires_at"]
    with runner.Renewal(envelope) as renewal:
        time.sleep(3.2)
    assert renewal.error is None and renewal.envelope["claim"]["proof"][0]["expires_at"] > initial
    book.report(renewal.envelope, copy.execute(renewal.envelope, book.artifacts), RUNTIME)
    verification = verification_for(book, rid, "s0", "0")
    book.verifier.admit(verification, verification_report(book, verification, copy))
    assert book.status(rid)["counts"] == {"verified": 1}


def test_crash_after_destination_before_control_and_reconcile(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    old = book.claim(rid, "s0", "0")
    written = copy.execute(book.envelope(old), book.artifacts)
    output = Path(written["uri"].removeprefix("file://"))
    before = output.stat().st_mtime_ns
    expire(databases, old)
    book.resume(rid)
    state = drive(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete"
    receipt = state["items"][0]["receipt"]
    assert {"uri": receipt["uri"], "sha256": receipt["sha256"]} == written
    assert output.stat().st_mtime_ns == before  # reconciled, not written twice


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


@pytest.mark.parametrize("damage", ["missing", "corrupt", "receipt"])
def test_resume_blocks_drift_and_bad_evidence(databases, tmp_path, damage):
    book, rid, inputs, _ = submit(databases, tmp_path, count=1)
    if damage == "receipt":
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


def test_a_worker_runtime_is_pinned_for_the_run(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    complete(book, rid, "0")
    envelope = book.envelope(book.claim(rid, "s0", "1"))
    with pytest.raises(DBAPIError, match="Pinned worker runtime changed"):
        book.report(envelope, copy.execute(envelope, book.artifacts), "b" * 64)
    book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)


def test_admission_refuses_reports_that_name_other_work_or_skip_checks(databases, tmp_path):
    body = config(2)
    body["bookkeeping"]["targets"]["silver"]["steps"][1]["checks"].append("fixture.readback")
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=body)
    complete(book, rid, "0")
    envelope = book.envelope(book.claim(rid, "s1", "0"))
    book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)
    verification = verification_for(book, rid, "s1", "0")
    assert verification["checks"] == ["fixture.readback"]
    binding = {"run_id": rid, "step": "s1", "key": "0", "attempt": envelope["claim"]["attempt"],
               "effect_key": verification["effect_key"], "candidate": verification["candidate"]}

    def admit(**changes):
        report = {"protocol": 1, "binding": binding, "checks": {"fixture.readback": True}, "proofs": [],
                  "runtime": RUNTIME}
        report.update(changes)
        return book.verifier.admit(verification, book.artifacts.put(tmp_path.as_uri() + "/forged", report))

    for forged in ({"binding": {**binding, "key": "1"}}, {"binding": {**binding, "attempt": str(uuid4())}},
                   {"binding": {**binding, "candidate": {"uri": "file:///other", "sha256": "0" * 64}}},
                   {"checks": {}}, {"checks": {"fixture.readback": False}},
                   {"checks": {"fixture.readback": True, "extra": True}}):
        with pytest.raises(Blocked):
            admit(**forged)
    with pytest.raises(Blocked, match="frozen work"):
        book.verifier.admit({**verification, "input": {"uri": "file:///elsewhere", "sha256": "0" * 64}},
                   book.artifacts.put(tmp_path.as_uri() + "/forged", {"protocol": 1}))
    assert book.status(rid)["counts"] == {"verified": 1, "reported": 1}
    admit()
    assert book.status(rid)["counts"] == {"verified": 2}


def test_completion_must_be_the_reported_candidate(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    claim = book.claim(rid, "s0", "0")
    candidate = copy.execute(book.envelope(claim), book.artifacts)
    evidence = book.artifacts.put(tmp_path.as_uri() + "/evidence", {"unreported": True})
    with pytest.raises(DBAPIError, match="reported candidate"):
        book._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
                   r=rid, s="s0", k="0", a=claim.attempt, p=canonical(claim.proof),
                   v=canonical({**candidate, "evidence": evidence}), c=canonical({"input.hash": True}), e=str(uuid4()))


def test_a_lapsed_report_is_verified_not_worked_again(databases, tmp_path):
    """A reported unit belongs to verifiers: once its lease lapses, the
    verifier re-takes it for the same attempt; no worker claims it again."""
    book, rid, _, _ = submit(databases, tmp_path, count=12)
    for key in map(str, range(12)):
        envelope = book.envelope(book.claim(rid, "s0", key))
        book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)
        expire(databases, book._claim_of(envelope))
    assert book.tasks(rid, "artifact.copy", limit=20) == []
    found = book.verifier.verifications(rid, "artifact.copy", limit=12)
    assert len(found) == 12 and all(v["claim"]["proof"][0]["token"] >= 2 for v in found)
    for verification in found:
        book.verifier.admit(verification, verification_report(book, verification, copy))
    assert book.status(rid)["counts"] == {"verified": 12}


def test_a_candidate_must_be_the_intended_output(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    elsewhere = book.artifacts.put_bytes((tmp_path / "elsewhere").as_uri(), b"x")
    with pytest.raises(Blocked, match="intended output"):
        book.report(envelope, elsewhere, RUNTIME)


def test_resource_checkpoints_span_runs_and_refuse_a_stale_comparison(databases, tmp_path):
    shared = tmp_path / "checkpointed"

    def run_at(folder, revision, position):
        return submit(databases, tmp_path / folder, count=1, output_root=shared / folder,
                      body=config(resource="feed:checkpointed"),
                      cursor=lambda n: {"resource_checkpoint": {"resource": "feed:checkpointed",
                                                                "revision": revision, "position": position}})

    first, r1, _, _ = run_at("a", 0, -1)
    complete(first, r1)
    assert first.resource_checkpoint("feed:checkpointed")["revision"] == 1
    stale, r2, _, _ = run_at("b", 0, -1)
    with pytest.raises(DBAPIError, match="comparison failed"):
        complete(stale, r2)
    with databases.admin.begin() as conn:  # the refused run gives its lease up
        conn.execute(text("UPDATE bookkeeping.lease SET expires_at=clock_timestamp() WHERE run_id=CAST(:r AS uuid)"), {"r": r2})
    current, r3, _, _ = run_at("c", 1, 0)
    complete(current, r3)
    assert current.resource_checkpoint("feed:checkpointed")["revision"] == 2


def test_restricted_functions_refuse_missing_fencing_or_unreported_completion(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    claim = book.claim(rid, "s0", "0")
    candidate = copy.execute(book.envelope(claim), book.artifacts)
    for proof in ([], [{**claim.proof[0], "token": claim.proof[0]["token"] + 1}], None):
        with pytest.raises(DBAPIError):
            book._call("SELECT bookkeeping.report(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:c AS jsonb),:f,:t)",
                       r=rid, s="s0", k="0", a=claim.attempt, p=None if proof is None else canonical(proof),
                       c=canonical(candidate), f="artifact.copy", t=RUNTIME)
    evidence = book.artifacts.put(tmp_path.as_uri() + "/evidence", {"unreported": True})
    with pytest.raises(DBAPIError, match="reported candidate"):
        book._call("SELECT bookkeeping.finish_resource(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),:x,0,-1)",
                   r=rid, s="s0", k="0", a=claim.attempt, p=canonical(claim.proof),
                   v=canonical({**candidate, "evidence": evidence}), c=canonical({"input.hash": True}),
                   e=str(uuid4()), x=claim.proof[0]["resource"])
    with databases.runtime.connect() as conn:
        assert not conn.scalar(text("SELECT has_function_privilege('bk_runtime','bookkeeping.verify_claim(uuid,text,text,uuid,integer)','EXECUTE') IS FALSE"))
        assert not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_proc WHERE proname='authorize_request')"))


def test_only_a_profiles_roles_report_and_verify_and_never_the_same_login(databases, tmp_path):
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("CREATE ROLE bk_stranger LOGIN PASSWORD 'test'")
        conn.exec_driver_sql("GRANT bk_control TO bk_stranger")
    with pytest.raises(Blocked, match="two different logins"):
        grant_profile(databases.admin, profile="self.check", worker="bk_runtime", verifier="bk_runtime")
    stranger = Bookkeeping(create_engine(databases.runtime.url.set(username="bk_stranger")))
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    for wrong in (stranger, book.verifier):  # only the worker role claims
        with pytest.raises(DBAPIError, match="no worker role"):
            wrong.claim(rid, "s0", "1", sleep=lambda _: None)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    candidate = copy.execute(envelope, book.artifacts)
    for wrong in (stranger, book.verifier):
        with pytest.raises(DBAPIError, match="no worker role"):
            wrong.report(envelope, candidate, RUNTIME)
    with pytest.raises(DBAPIError, match="profile the run froze"):  # a worker of another profile's name
        book._call("SELECT bookkeeping.report(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:c AS jsonb),:f,:t)",
                   r=rid, s="s0", k="0", a=envelope["claim"]["attempt"], p=canonical(envelope["claim"]["proof"]),
                   c=canonical(candidate), f="jsonl.count", t=RUNTIME)
    book.report(envelope, candidate, RUNTIME)
    for wrong in (stranger, book):
        with pytest.raises(DBAPIError, match="no verifier role"):
            wrong.verifications(rid, "artifact.copy")
    # A login granted both duties still cannot verify, or complete, what it reported.
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        role = conn.scalar(text("SELECT bookkeeping.profile_role('artifact.copy','verifier')"))
        conn.exec_driver_sql(f'GRANT "{role}" TO bk_runtime')
    try:
        with pytest.raises(DBAPIError, match="its own report"):
            book.verifications(rid, "artifact.copy")
        evidence = book.artifacts.put(tmp_path.as_uri() + "/evidence", {"self": True})
        with pytest.raises(DBAPIError, match="other than its reporter"):
            book._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
                       r=rid, s="s0", k="0", a=envelope["claim"]["attempt"], p=canonical(envelope["claim"]["proof"]),
                       v=canonical({**candidate, "evidence": evidence}), c=canonical({"input.hash": True}), e=str(uuid4()))
    finally:
        with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'REVOKE "{role}" FROM bk_runtime')
    verification = verification_for(book, rid, "s0", "0")
    book.verifier.admit(verification, verification_report(book, verification, copy))
    assert book.status(rid)["counts"] == {"verified": 1, "pending": 1}
    stranger.close()


def test_a_lease_lapsing_while_the_verifier_runs_refuses_the_late_admission(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)
    late = verification_for(book, rid, "s0", "0")
    report = verification_report(book, late, copy)
    expire(databases, book._claim_of(late))
    with pytest.raises(DBAPIError, match="Stale lease"):
        book.verifier.admit(late, report)
    fresh = verification_for(book, rid, "s0", "0")
    assert fresh["claim"]["proof"][0]["token"] > late["claim"]["proof"][0]["token"]
    with pytest.raises(DBAPIError, match="Stale lease"):  # the old lease's token stays dead
        book.verifier.admit(late, report)
    book.verifier.admit(fresh, verification_report(book, fresh, copy))
    assert book.status(rid)["counts"] == {"verified": 1}


def test_a_verifier_runtime_is_pinned_for_the_run(databases, tmp_path):
    from edgar_warehouse.workers.control import report_document
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    complete(book, rid, "0")
    envelope = book.envelope(book.claim(rid, "s0", "1"))
    book.report(envelope, copy.execute(envelope, book.artifacts), RUNTIME)
    verification = verification_for(book, rid, "s0", "1")
    checks, proofs = copy.verify(verification, book.artifacts)
    other = book.artifacts.put(tmp_path.as_uri() + "/reports", report_document(verification, checks, proofs, "c" * 64))
    with pytest.raises(DBAPIError, match="Pinned verifier runtime changed"):
        book.verifier.admit(verification, other)
    malformed = book.artifacts.put(tmp_path.as_uri() + "/reports", report_document(verification, checks, proofs, "unnamed"))
    with pytest.raises(DBAPIError, match="names its runtime"):
        book.verifier.admit(verification, malformed)
    assert book.status(rid)["run"]["runtimes"]["verify:artifact.copy"] == RUNTIME
    assert book.status(rid)["counts"] == {"verified": 1, "reported": 1}  # a refused admission pins nothing new


def test_zero_work_explicit_configuration_and_manifest_evidence(databases, tmp_path):
    with pytest.raises(Blocked):
        submit(databases, tmp_path / "no", count=0)
    book, rid, _, _ = submit(databases, tmp_path / "yes", count=0, body=config(zero=True))
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"


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
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"
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


def test_unseen_source_configuration_only(databases, tmp_path):
    from edgar_warehouse.rules.files import loads
    body = loads('''source: unseen.calendar\nbookkeeping:\n  version: 1\n  targets:\n    silver:\n      steps:\n        - name: archive\n          operation: artifact.copy\n          requires: []\n          key: "{id}"\n          leases: ["calendar:{destination}"]\n          checks: [input.hash, output.receipt]\n      checks: [manifest.hash, work.accounting, journal.delivered]\n''')
    book, rid, _, _ = submit(databases, tmp_path, body=body)
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"


GUARD = """
import importlib.abc, sys
BLOCKED = ("edgar", "pyarrow", "lxml", "bs4", "source_contract", "edgar_warehouse.mdm", "edgar_warehouse.loaders",
           "edgar_warehouse.parsers", "edgar_warehouse.serving", "edgar_warehouse.application",
           "edgar_warehouse.acquisition", "edgar_warehouse.workers")

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        control = bool(sys.argv) and sys.argv[0].endswith("edgar_warehouse/bookkeeping/__main__.py")
        if control and any(name == b or name.startswith(b + ".") for b in BLOCKED):
            raise ImportError("Bookkeeping control loaded a domain package: " + name)
        return None

sys.meta_path.insert(0, Guard())
"""


def test_two_workers_in_their_own_processes_complete_a_cli_submitted_run(databases, tmp_path, monkeypatch, capsys):
    """Gates 1 and 2: control runs with every domain package blocked, and two
    different workers finish the run through the commands alone."""
    import os
    import sys
    from edgar_warehouse.cli import main
    body = config(2)
    second = body["bookkeeping"]["targets"]["silver"]["steps"][1]
    second.update(operation="jsonl.count", checks=["input.hash", "output.receipt", "count.readback"])
    book = Bookkeeping(databases.runtime)
    name = f"workers-{uuid4().hex}"
    saved = databases.rules.save("source", name, "1", body)
    copies = []
    for n in range(2):
        source = book.artifacts.put(tmp_path.as_uri() + "/inputs", {"row": n})
        copies.append({"keys": {"id": str(n), "destination": (tmp_path / f"copy-{n}").as_uri()}, "input": source,
                       "output": (tmp_path / f"copy-{n}").as_uri(), "cursor": {"offset": n}})
    counts = [{"keys": {"id": f"count-{n}", "destination": (tmp_path / f"count-{n}").as_uri()},
               "input": {"from": {"step": "s0", "key": str(n)}}, "output": (tmp_path / f"count-{n}").as_uri(),
               "cursor": {"offset": n}} for n in range(2)]
    inputs = book.artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 2, "steps": {"s0": copies, "s1": counts}})
    databases.rules.prove("source", name, "1", {"digest": saved["digest"], "batch_hash": inputs["sha256"], "passed": True})
    databases.rules.activate("source", name, "1")
    environment = {"BOOKKEEPING_CLEAN_DATABASE_URL": databases.runtime.url.render_as_string(hide_password=False),
                   "RULES_DATABASE_URL": databases.rules.engine.url.render_as_string(hide_password=False),
                   "CHANGE_JOURNAL_DATABASE_URL": databases.ledger.engine.url.render_as_string(hide_password=False),
                   "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "cli-manifests").as_uri()}
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MDM_DATABASE_URL", raising=False)
    assert main(["rules", "run", "--source", name, "--target", "silver",
                 "--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"]]) == 0
    submitted = json.loads(capsys.readouterr().out)
    rid = submitted["run"]["run_id"]
    assert submitted["counts"] == {"pending": 4}

    site = tmp_path / "site"
    site.mkdir()
    (site / "sitecustomize.py").write_text(GUARD)
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, **environment, "PYTHONPATH": os.pathsep.join([str(site), str(root)])}

    def process(*arguments):
        done = subprocess.run([sys.executable, *arguments], env=env, cwd=root, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    reports = (tmp_path / "reports").as_uri()
    verifier_url = databases.verifier.url.render_as_string(hide_password=False)
    for profile in ("artifact.copy", "jsonl.count"):
        process("-m", "edgar_warehouse.workers", "work", profile, rid)
        env["BOOKKEEPING_CLEAN_DATABASE_URL"], worker_url = verifier_url, env["BOOKKEEPING_CLEAN_DATABASE_URL"]
        process("-m", "edgar_warehouse.workers", "verify", profile, rid, "--reports", reports)
        env["BOOKKEEPING_CLEAN_DATABASE_URL"] = worker_url
    finished = json.loads(process("-m", "edgar_warehouse.bookkeeping", "finalize", rid))
    assert finished["run"]["state"] == "complete" and finished["counts"] == {"verified": 4}
    assert json.loads(Path(tmp_path / "count-1").read_text()) == {"lines": 1}
    runtimes = {p: json.loads(process("-m", "edgar_warehouse.workers", "describe", p))["runtime"]
                for p in ("artifact.copy", "jsonl.count")}
    assert book.status(rid)["run"]["runtimes"] == {**runtimes, **{f"verify:{p}": d for p, d in runtimes.items()}}

    # The guard is live: control refuses to start once a domain import creeps in.
    refused = subprocess.run([sys.executable, "-c", GUARD + "\nsys.argv=['edgar_warehouse/bookkeeping/__main__.py']\nimport edgar_warehouse.mdm"],
                             env=env, cwd=root, capture_output=True, text=True)
    assert "Bookkeeping control loaded a domain package" in refused.stderr

    assert main(["rules", "run", "--source", name, "--target", "silver", "--resume-run-id", rid]) == 0
    assert json.loads(capsys.readouterr().out)["counts"] == {"verified": 4}
    assert main(["bookkeeping", "finalize", rid]) == 0  # resume reopens; nothing is left to work
    capsys.readouterr()
    assert main(["bookkeeping", "runs", "--state", "complete", "--limit", "100"]) == 0
    assert any(row["run_id"] == rid for row in json.loads(capsys.readouterr().out))


def test_source_configs_use_same_control_contract():
    from edgar_warehouse.rules.files import source
    from edgar_warehouse.bookkeeping.clean.config import validate
    for name in ("sec.submissions.company",):
        selected = validate(source(name), "capture")
        assert selected["lease_seconds"] == 120 and selected["heartbeat_seconds"] == 30


def test_provisioning_uses_nologin_owners_and_empty_stores(monkeypatch):
    import runpy
    with pg16.server() as server:
        _provision(server, monkeypatch, runpy)


def _provision(server, monkeypatch, runpy):
    engines = []
    try:
        url = server.url(driver="postgresql")
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
            runtime = create_engine(server.url(database, role, driver="postgresql"))
            engines.append(runtime)
            with runtime.connect() as conn:
                assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(f"DELETE FROM {table}"))
        journal_admin = create_engine(server.url("change_journal_clean", driver="postgresql"))
        engines.append(journal_admin)
        with journal_admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM journal.event")) == 0
            assert conn.scalars(text("SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")).all() == ["journal.event"]
        with admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname IN ('rules_owner','bookkeeping_clean_owner','change_journal_owner') AND NOT rolcanlogin AND NOT rolsuper")) == 3
    finally:
        for engine in engines:
            engine.dispose()
