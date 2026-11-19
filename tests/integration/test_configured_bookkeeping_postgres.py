"""Required PG16 acceptance: missing prerequisites FAIL, never skip.

The source fixture tests exercise configured control, not SEC/GLEIF business
parsing or production cutover. No network source requests are made.
"""
from __future__ import annotations
from edgar_warehouse.rules import frozen

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import json
import subprocess
from threading import Event
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from edgar_warehouse.bookkeeping.clean.database import grant_profile, migrate
from edgar_warehouse.change_journal import ChangeJournal, JournalConflict
from edgar_warehouse.change_journal.database import migrate as migrate_journal
from edgar_warehouse.bookkeeping.clean.engine import CONTENTION, Bookkeeping
from edgar_warehouse.rules.db import Rules, migrate as migrate_rules
from edgar_warehouse.workers import copy
from tests.support import pg16
from tests.support.bookkeeping_protocol import RUNTIME, check_report, complete, drive, finish


PROFILES = ("artifact.copy", "jsonl.count", "fixture.transform", "fixture.gather")


@dataclass
class Databases:
    admin: object
    runtime: object
    rules: Rules
    ledger: ChangeJournal
    ledger_admin: object
    loader: str  # the DB_URL of one login that holds every store's runtime privileges, with no database


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
            with setup.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                for role in ("bk_runtime", "mdm_reader", "rules_agent", "operator", "ledger_runtime", "clean_application", "loader"):
                    conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
                # Control's grants go to one group; the worker (bk_runtime) is its member.
                conn.exec_driver_sql("CREATE ROLE bk_control NOLOGIN")
                conn.exec_driver_sql("GRANT bk_control TO bk_runtime")
                conn.exec_driver_sql("GRANT bk_runtime, rules_agent, ledger_runtime, clean_application TO loader")
                for db in ("bookkeeping", "rules", "change_journal"):
                    conn.exec_driver_sql(f"CREATE DATABASE {db}")
            admin = engine("bookkeeping")
            runtime = engine("bookkeeping", "bk_runtime")
            rules_admin = engine("rules")
            ledger_admin = engine("change_journal")
            with pytest.raises(Blocked, match="not initialized"):
                migrate(admin, runtime_role="bk_control", existing_only=True)
            with pytest.raises(Blocked, match="not initialized"):
                migrate_journal(ledger_admin, runtime_role="ledger_runtime", existing_only=True)
            migrate(admin, runtime_role="bk_control")
            for profile in PROFILES:
                grant_profile(admin, profile=profile, worker="bk_runtime")
            migrate_rules(rules_admin, agent_role="rules_agent")
            migrate_journal(ledger_admin, runtime_role="ledger_runtime")
            from sqlalchemy.engine import make_url

            loader = make_url(server.url("postgres", "loader", driver="postgresql"))._replace(database=None).render_as_string(hide_password=False)
            yield Databases(admin, runtime, Rules(engine("rules", "rules_agent")),
                            ChangeJournal(engine("change_journal", "ledger_runtime")), ledger_admin, loader)
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


def fixture_feed(body, name, contracts):
    """Attach a bounded fixture feed to a source document."""
    body["source"] = name
    body["acquisition"] = {"version": 1, "feeds": {"fixture": {
        "family": "fixture", "datasets": list(contracts), "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
        "required_producers": ["fixture"], "url_prefixes": ["https://fixture.invalid/"],
    }}}


def submit(databases, tmp_path, count=3, *, body=None, book=None, output_root=None, cursor=None):
    book = book or Bookkeeping(databases.runtime)
    body = body or config()
    name = f"fixture-{uuid4().hex}"
    saved = frozen.of("source", name, body)
    artifacts = book.artifacts
    units = []
    for n in range(count):
        source = artifacts.put(tmp_path.as_uri() + "/inputs", {"row": n})
        output = (output_root or tmp_path) / f"output-{n}"
        units.append({"keys": {"id": str(n), "destination": output.as_uri()}, "input": source, "output": output.as_uri(),
                      "cursor": cursor(n) if cursor else {"offset": n}})
    inputs = artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 1, "units": units})
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
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


def test_bookkeeping_cli_init_and_migrate_use_owner_and_preserve_empty_control(monkeypatch, capsys):
    from edgar_warehouse.cli import main

    # This test asserts emptiness, so it owns an empty store. Selective runs
    # may schedule it after tests that populate the module-scoped store.
    with pg16.server() as server:
        setup = create_engine(server.url(driver="postgresql"))
        owner = None
        try:
            with setup.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("CREATE DATABASE bookkeeping")
                conn.exec_driver_sql("CREATE ROLE bk_control NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
            owner = create_engine(server.url("bookkeeping", driver="postgresql"))
            monkeypatch.setenv("DB_URL", owner.url.render_as_string(hide_password=False))
            assert main(["bookkeeping", "init", "--runtime-role", "bk_control"]) == 0
            assert "schema.sql" in capsys.readouterr().out
            assert main(["bookkeeping", "init", "--runtime-role", "bk_control"]) == 0
            assert "schema.sql" in capsys.readouterr().out
            with owner.connect() as conn:
                assert conn.scalar(text("SELECT count(*) FROM bookkeeping.pipeline_run")) == 0
                assert conn.scalar(text("SELECT count(*) FROM bookkeeping.work_item")) == 0
        finally:
            if owner is not None:
                owner.dispose()
            setup.dispose()


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


def test_every_event_is_delivered_however_small_the_batch(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path)
    for key in ("0", "1", "2"):
        complete(book, rid, key)

    assert book.deliver_all(databases.ledger, rid, limit=1) == 3
    assert book.status(rid)["pending_deliveries"] == 0
    assert book.finalize(rid)["run"]["state"] == "complete"


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


def test_one_steps_status_counts_only_its_units_and_a_busy_unit_is_claimed_again(databases, tmp_path):
    """`bookkeeping status --step` (ticket 136): the run driver judges a step by its own counts."""
    book, rid, _, _ = submit(databases, tmp_path, body=config(2))
    assert book.claim(rid, "s1", "0", sleep=lambda _: None) is None  # s0 unfinished: the unit waits
    waiting = book.status(rid, step="s1")
    assert waiting["counts"] == {"pending": 2, "waiting": 1}
    assert [(i["unit_key"], i["error"]) for i in waiting["items"] if i["state"] == "waiting"] == [("0", CONTENTION)]
    assert waiting["failed_steps"] == []
    for key in "012":
        complete(book, rid, key)
    assert book.status(rid, step="s0")["counts"] == {"verified": 3}
    assert {i["step"] for i in book.status(rid, step="s0")["items"]} == {"s0"}
    complete(book, rid, "0", step="s1")  # the waiting unit is claimed again once s0 is verified
    assert book.status(rid, step="s1")["counts"] == {"pending": 2, "verified": 1}
    assert book.status(rid)["counts"] == {"pending": 2, "verified": 4}


def test_status_exposes_failed_attempt_steps_without_error_text(databases, tmp_path):
    book, run_id, _, _ = submit(databases, tmp_path, count=1)
    claim = book.claim(run_id, "s0", "0", sleep=lambda _: None)
    assert claim

    book.fail(book.envelope(claim), "private failure detail")
    status = book.status(run_id)

    assert status["failed_steps"] == ["s0"]
    assert "private failure detail" not in json.dumps(status["failed_steps"])
    retry = book.claim(run_id, "s0", "0", sleep=lambda _: None)
    assert retry
    retried = book.status(run_id)
    assert retried["failed_steps"] == []
    assert retried["items"][0]["attempts"] == 2
    assert retried["items"][0]["error"] is None
    book.close()


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
        def check(cls, envelope, artifacts):
            if artifacts.verified(envelope["candidate"]) != cls.expected(envelope, artifacts):
                raise ValueError("Transformed output differs from verified input")
            return {name: True for name in envelope["checks"]}, []

    book = Bookkeeping(databases.runtime)
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
    saved = frozen.of("pipeline", name, body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
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


@pytest.mark.parametrize("corruption", ["output", "missing_receipt"])
def test_dependency_corruption_blocks_downstream_without_execution(databases, tmp_path, corruption):
    book, rid, manifest, executions = staged_submission(databases, tmp_path)
    state = drive(book, rid, databases.ledger, workers=book.workers, limit=2)
    upstream = next(i for i in state["items"] if i["step"] == "z_capture" and i["unit_key"] == "raw0")
    if corruption == "missing_receipt":
        with databases.admin.begin() as conn:
            conn.execute(text("UPDATE bookkeeping.work_item SET receipt=NULL WHERE run_id=CAST(:r AS uuid) AND step='z_capture' AND unit_key='raw0'"), {"r": rid})
    else:
        Path(upstream["receipt"]["uri"].removeprefix("file://")).write_bytes(b"corrupt")
    with pytest.raises(Blocked):
        drive(book, rid, databases.ledger, workers=book.workers)
    assert book.status(rid)["run"]["state"] == "blocked" and executions == []


def fan_in_submission(databases, tmp_path, capture=None):
    """A gathering step whose one input is a document composed from many verified outputs (to-do 20c).
    `capture`: the capture the manifest was written from."""
    book, _, manifest, executions = staged_submission(databases, tmp_path)
    gathered = []

    class Gather:
        """Reads every receipt its composed document names; Bookkeeping filled them."""
        @staticmethod
        def expected(envelope, artifacts):
            document = artifacts.json(envelope["input"])
            inner = artifacts.json(document["inner"])
            parts = [artifacts.verified(ref) for ref in [document["one"], *document["all"], inner["raw"]]]
            return b"+".join(parts)

        @classmethod
        def execute(cls, envelope, artifacts):
            gathered.append(envelope["input"])
            return artifacts.put_bytes(envelope["output"], cls.expected(envelope, artifacts))

        @classmethod
        def check(cls, envelope, artifacts):
            if artifacts.verified(envelope["candidate"]) != cls.expected(envelope, artifacts):
                raise ValueError("Gathered output differs from its composed inputs")
            return {name: True for name in envelope["checks"]}, []

    body = config(3)
    steps = body["bookkeeping"]["targets"]["silver"]["steps"]
    for step, name, requires in zip(steps, ("z_capture", "a_transform", "b_gather"),
                                    ([], ["z_capture"], ["z_capture", "a_transform"])):
        step.update(name=name, requires=requires)
    steps[1]["operation"] = "fixture.transform"
    steps[2]["operation"] = "fixture.gather"
    output = (tmp_path / "gather" / "all").as_uri()
    compose = {"document": {"version": 1, "one": {"slot": "first"}, "all": {"slot": "parts"}, "inner": {"slot": "nested"}},
               "slots": {"first": {"step": "a_transform", "key": "parsed1"},
                         "parts": [{"step": "a_transform", "key": f"parsed{n}"} for n in (2, 0)],
                         "nested": {"compose": {"document": {"raw": {"slot": "raw"}},
                                                "slots": {"raw": {"step": "z_capture", "key": "raw1"}}}}}}
    manifest["steps"]["b_gather"] = [{"keys": {"id": "all", "destination": output}, "input": {"compose": compose},
                                      "output": output, "cursor": {"key": "all"}}]
    del manifest["steps"]["b_finish"]
    if capture:
        manifest["capture"] = capture
    inputs = book.artifacts.put(tmp_path.as_uri() + "/manifests", manifest)
    name = "fan-in-" + uuid4().hex
    saved = frozen.of("pipeline", name, body)
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    rid = book.start(rules_ref=rules, inputs_ref=inputs, target="silver", scope={"test": name})
    book.workers = {**book.workers, "fixture.gather": Gather}
    return book, rid, output, executions, gathered


def test_a_composed_input_gathers_many_verified_outputs(databases, tmp_path):
    book, rid, output, executions, gathered = fan_in_submission(databases, tmp_path)
    assert book.claim(rid, "b_gather", "all", sleep=lambda _: None) is None  # waits for every prerequisite unit
    state = drive(book, rid, databases.ledger, workers=book.workers)
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 6}
    assert book.artifacts.read(output) == b"+".join(
        [b"INPUT-1|transformed", b"INPUT-0|transformed", b"INPUT-0|transformed", b"input-1"])
    (document,) = gathered
    assert document["uri"].startswith((tmp_path / "gather" / "inputs").as_uri())  # beside the output, by content
    assert book.artifacts.json(document)["all"] == [
        {k: i["receipt"][k] for k in ("uri", "sha256")} for key in ("parsed2", "parsed0")
        for i in state["items"] if i["unit_key"] == key]
    with databases.runtime.connect() as conn:
        frozen = conn.scalar(text("SELECT unit->'input' FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) AND step='b_gather'"), {"r": rid})
    assert set(frozen) == {"compose"}  # the frozen work keeps its slots, never a filled document
    book.resume(rid)
    drive(book, rid, databases.ledger, workers=book.workers)
    assert len(gathered) == 1 and executions == ["parsed0", "parsed1", "parsed2"]


def test_a_composed_input_with_a_corrupt_slot_blocks_without_execution(databases, tmp_path):
    book, rid, output, executions, gathered = fan_in_submission(databases, tmp_path)
    state = drive(book, rid, databases.ledger, workers=book.workers, limit=5)
    upstream = next(i for i in state["items"] if i["unit_key"] == "parsed0")
    Path(upstream["receipt"]["uri"].removeprefix("file://")).write_bytes(b"corrupt")
    with pytest.raises(Blocked):
        drive(book, rid, databases.ledger, workers=book.workers)
    assert book.status(rid)["run"]["state"] == "blocked" and gathered == []


def test_a_manifest_names_its_capture_as_text_only(databases, tmp_path):
    with pytest.raises(Blocked, match="capture"):
        fan_in_submission(databases, tmp_path, capture={"run": "capture-1"})


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
    receipt = {**candidate, "evidence": check_report(book, envelope, candidate, copy)}
    checks = {"input.hash": True, "output.receipt": True}
    with pytest.raises(DBAPIError), databases.runtime.begin() as conn:
        conn.execute(text("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))"),
                     {"r": rid, "s": claim.step, "k": claim.key, "a": claim.attempt, "p": canonical(claim.proof),
                      "v": canonical(receipt), "c": canonical(checks), "e": str(uuid4())})
        time.sleep(2.1)
    state = book.status(rid)
    assert state["counts"] == {"running": 1} and state["pending_deliveries"] == 0
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
    stale_report = check_report(book, stale, candidate, copy)
    expire(databases, old)
    new = book.claim(rid, "s0", "0")
    assert new.attempt != old.attempt
    with pytest.raises(Blocked, match="live attempt"):
        book.report(stale, candidate, stale_report)
    with pytest.raises(DBAPIError):
        book.wait(old, "stale")
    envelope = book.envelope(new)
    report = check_report(book, envelope, candidate, copy)
    book.report(envelope, candidate, report)
    book.report(envelope, candidate, report)  # lost acknowledgement
    assert book.status(rid)["counts"] == {"verified": 1}
    other = book.artifacts.put(tmp_path.as_uri() + "/other-reports", {"other": True})
    with pytest.raises(Blocked, match="changed"):
        book.report(envelope, candidate, other)


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
    finish(book, renewal.envelope, copy)
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


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_no_work_starts_on_a_changed_manifest(databases, tmp_path, damage):
    book, rid, inputs, _ = submit(databases, tmp_path, count=1)
    path = Path(inputs["uri"].removeprefix("file://"))
    if damage == "missing":
        path.unlink()
    else:
        path.write_text("not a manifest")
    with pytest.raises(Blocked):
        Bookkeeping(databases.runtime).tasks(rid, "artifact.copy")


def test_a_worker_runtime_is_pinned_for_the_run(databases, tmp_path):
    from edgar_warehouse.workers.control import report_document
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    complete(book, rid, "0")
    envelope = book.envelope(book.claim(rid, "s0", "1"))
    candidate = copy.execute(envelope, book.artifacts)
    checks, proofs = copy.check({**envelope, "candidate": candidate}, book.artifacts)

    def report(runtime):
        return book.artifacts.put(tmp_path.as_uri() + "/reports", report_document(envelope, candidate, checks, proofs, runtime))

    with pytest.raises(DBAPIError, match="Pinned worker runtime changed"):
        book.report(envelope, candidate, report("c" * 64))
    with pytest.raises(DBAPIError, match="names its runtime"):
        book.report(envelope, candidate, report("unnamed"))
    assert book.status(rid)["run"]["runtimes"] == {"artifact.copy": RUNTIME}
    assert book.status(rid)["counts"] == {"verified": 1, "running": 1}  # a refused report pins nothing new
    book.report(envelope, candidate, report(RUNTIME))


def test_a_report_that_names_other_work_or_skips_a_check_is_refused(databases, tmp_path):
    body = config(2)
    body["bookkeeping"]["targets"]["silver"]["steps"][1]["checks"].append("fixture.readback")
    book, rid, _, _ = submit(databases, tmp_path, count=1, body=body)
    complete(book, rid, "0")
    envelope = book.envelope(book.claim(rid, "s1", "0"))
    assert envelope["checks"] == ["fixture.readback"]
    candidate = copy.execute(envelope, book.artifacts)
    binding = {"run_id": rid, "step": "s1", "key": "0", "attempt": envelope["claim"]["attempt"],
               "effect_key": envelope["effect_key"], "candidate": candidate}

    def report(**changes):
        document = {"protocol": 1, "binding": binding, "checks": {"fixture.readback": True}, "proofs": [],
                    "runtime": RUNTIME}
        document.update(changes)
        return book.report(envelope, candidate, book.artifacts.put(tmp_path.as_uri() + "/forged", document))

    for forged in ({"binding": {**binding, "key": "1"}}, {"binding": {**binding, "attempt": str(uuid4())}},
                   {"binding": {**binding, "candidate": {"uri": "file:///other", "sha256": "0" * 64}}},
                   {"checks": {}}, {"checks": {"fixture.readback": False}},
                   {"checks": {"fixture.readback": True, "extra": True}}):
        with pytest.raises(Blocked):
            report(**forged)
    with pytest.raises(Blocked, match="frozen work"):
        book.report({**envelope, "input": {"uri": "file:///elsewhere", "sha256": "0" * 64}}, candidate,
                    book.artifacts.put(tmp_path.as_uri() + "/forged", {"protocol": 1}))
    assert book.status(rid)["counts"] == {"verified": 1, "running": 1}
    report()
    assert book.status(rid)["counts"] == {"verified": 2}


def test_a_candidate_must_be_the_intended_output(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    elsewhere = book.artifacts.put_bytes((tmp_path / "elsewhere").as_uri(), b"x")
    with pytest.raises(Blocked, match="intended output"):
        book.report(envelope, elsewhere, book.artifacts.put(tmp_path.as_uri() + "/reports", {"protocol": 1}))


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


def test_restricted_functions_refuse_missing_fencing(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    claim = book.claim(rid, "s0", "0")
    envelope = book.envelope(claim)
    candidate = copy.execute(envelope, book.artifacts)
    receipt = {**candidate, "evidence": check_report(book, envelope, candidate, copy)}
    for proof in ([], [{**claim.proof[0], "token": claim.proof[0]["token"] + 1}], None):
        with pytest.raises(DBAPIError):
            book._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
                       r=rid, s="s0", k="0", a=claim.attempt, p=None if proof is None else canonical(proof),
                       v=canonical(receipt), c=canonical({"input.hash": True}), e=str(uuid4()))
    with databases.runtime.connect() as conn:
        assert not conn.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_proc WHERE proname IN ('authorize_request','report','verify_claim','pin_verifier'))"))


def test_only_a_profiles_worker_claims_and_completes_its_units(databases, tmp_path):
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("CREATE ROLE bk_stranger LOGIN PASSWORD 'test'")
        conn.exec_driver_sql("GRANT bk_control TO bk_stranger")
    stranger = Bookkeeping(create_engine(databases.runtime.url.set(username="bk_stranger")), artifacts=None)
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    stranger.artifacts = book.artifacts
    with pytest.raises(DBAPIError, match="no worker role"):
        stranger.claim(rid, "s0", "1", sleep=lambda _: None)
    envelope = book.envelope(book.claim(rid, "s0", "0"))
    candidate = copy.execute(envelope, book.artifacts)
    report = check_report(book, envelope, candidate, copy)
    with pytest.raises(DBAPIError, match="no worker role"):
        stranger.report(envelope, candidate, report)
    with pytest.raises(DBAPIError, match="worker of this profile"):  # the finish function alone, by another login
        stranger._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
                       r=rid, s="s0", k="0", a=envelope["claim"]["attempt"], p=canonical(envelope["claim"]["proof"]),
                       v=canonical({**candidate, "evidence": report}), c=canonical({"input.hash": True}), e=str(uuid4()))
    book.report(envelope, candidate, report)
    assert book.status(rid)["counts"] == {"verified": 1, "pending": 1}
    stranger.close()


def test_a_lease_lapsing_before_the_report_refuses_it(databases, tmp_path):
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    late = book.envelope(book.claim(rid, "s0", "0"))
    candidate = copy.execute(late, book.artifacts)
    report = check_report(book, late, candidate, copy)
    expire(databases, book._claim_of(late))
    with pytest.raises(DBAPIError, match="Stale lease"):
        book.report(late, candidate, report)
    fresh = book.envelope(book.claim(rid, "s0", "0"))
    assert fresh["claim"]["proof"][0]["token"] > late["claim"]["proof"][0]["token"]
    with pytest.raises(Blocked, match="live attempt"):  # the old attempt stays dead
        book.report(late, candidate, report)
    finish(book, fresh, copy)
    assert book.status(rid)["counts"] == {"verified": 1}


@pytest.mark.parametrize("complete_replacement", [False, True], ids=["running", "verified"])
def test_attempt_superseded_after_the_report_precheck_is_refused_atomically(
    databases, tmp_path, complete_replacement
):
    """A replacement cannot be completed or have its evidence replaced by a stale report."""
    book, rid, _, _ = submit(databases, tmp_path, count=1)
    stale = book.envelope(book.claim(rid, "s0", "0"))
    candidate = copy.execute(stale, book.artifacts)
    report = check_report(book, stale, candidate, copy)
    precheck_passed = Event()
    resume_old_report = Event()
    original_artifacts = book.artifacts
    late = Bookkeeping(databases.runtime, artifacts=None)

    class PausingArtifacts:
        def __getattr__(self, name):
            return getattr(original_artifacts, name)

        def json(self, ref):
            # The report has checked the attempt before it reads this document.
            if ref == report:
                precheck_passed.set()
                if not resume_old_report.wait(timeout=10):
                    raise TimeoutError("The report did not resume after the replacement claim")
            return original_artifacts.json(ref)

    late.artifacts = PausingArtifacts()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(late.report, stale, candidate, report)
        try:
            assert precheck_passed.wait(timeout=10), "The report did not reach its document read"
            expire(databases, book._claim_of(stale))
            replacement = book.claim(rid, "s0", "0")
            if complete_replacement:
                replacement_receipt = finish(book, book.envelope(replacement), copy)
        finally:
            resume_old_report.set()
        error = "Completion evidence changed" if complete_replacement else "Stale attempt"
        with pytest.raises(DBAPIError, match=error):
            pending.result(timeout=10)

    state = book.status(rid)
    assert state["items"][0]["attempt"] == replacement.attempt
    if complete_replacement:
        assert state["counts"] == {"verified": 1}
        assert state["items"][0]["receipt"] == replacement_receipt
        assert state["items"][0]["receipt"]["evidence"] != report
    else:
        assert state["counts"] == {"running": 1}
        assert state["items"][0]["state"] == "running"


def test_zero_work_explicit_configuration_and_manifest_evidence(databases, tmp_path):
    with pytest.raises(Blocked):
        submit(databases, tmp_path / "no", count=0)
    book, rid, _, _ = submit(databases, tmp_path / "yes", count=0, body=config(zero=True))
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"


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
    saved = frozen.of("source", name, body)
    copies = []
    for n in range(2):
        source = book.artifacts.put(tmp_path.as_uri() + "/inputs", {"row": n})
        copies.append({"keys": {"id": str(n), "destination": (tmp_path / f"copy-{n}").as_uri()}, "input": source,
                       "output": (tmp_path / f"copy-{n}").as_uri(), "cursor": {"offset": n}})
    counts = [{"keys": {"id": f"count-{n}", "destination": (tmp_path / f"count-{n}").as_uri()},
               "input": {"from": {"step": "s0", "key": str(n)}}, "output": (tmp_path / f"count-{n}").as_uri(),
               "cursor": {"offset": n}} for n in range(2)]
    inputs = book.artifacts.put(tmp_path.as_uri() + "/manifests", {"version": 2, "steps": {"s0": copies, "s1": counts}})
    environment = {"DB_URL": databases.loader,
                   "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "cli-manifests").as_uri()}
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    from edgar_warehouse.rules import files
    files.write_source(body, tmp_path / "rules-root" / "sources" / name)
    assert main(["rules", "run", "--source", name, "--target", "silver", "--root", str(tmp_path / "rules-root"),
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
    for profile in ("artifact.copy", "jsonl.count"):
        process("-m", "edgar_warehouse.workers", "work", profile, rid, "--reports", reports)
    finished = json.loads(process("-m", "edgar_warehouse.bookkeeping", "finalize", rid))
    assert finished["run"]["state"] == "complete" and finished["counts"] == {"verified": 4}
    assert json.loads(Path(tmp_path / "count-1").read_text()) == {"lines": 1}
    runtimes = {p: json.loads(process("-m", "edgar_warehouse.workers", "describe", p))["runtime"]
                for p in ("artifact.copy", "jsonl.count")}
    assert book.status(rid)["run"]["runtimes"] == runtimes

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
    for name in ("sec.company",):
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
        monkeypatch.setenv("BOOKKEEPING_RUNTIME_PASSWORD", "test")
        monkeypatch.setenv("RULES_AGENT_PASSWORD", "test")
        script = Path(__file__).parents[2] / "infra/scripts/provision-clean-bookkeeping.py"
        provision = runpy.run_path(str(script))["provision"]
        monkeypatch.setenv("CHANGE_JOURNAL_RUNTIME_PASSWORD", "test")
        result = provision(url, rules=True, journal=True)
        assert set(result) == {"bookkeeping", "rules", "change_journal"}
        assert provision(url, rules=True, journal=True) == result
        for database, role, table in (("bookkeeping", "bookkeeping_runtime", "bookkeeping.pipeline_run"),
                                      ("rules", "rules_agent", "rules.rules_used")):
            runtime = create_engine(server.url(database, role, driver="postgresql"))
            engines.append(runtime)
            with runtime.connect() as conn:
                assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(f"DELETE FROM {table}"))
        journal_admin = create_engine(server.url("change_journal", driver="postgresql"))
        engines.append(journal_admin)
        with journal_admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM journal.event")) == 0
            assert conn.scalars(text("SELECT schemaname||'.'||tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")).all() == ["journal.event"]
        with admin.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname IN ('rules_owner','bookkeeping_owner','change_journal_owner') AND NOT rolcanlogin AND NOT rolsuper")) == 3
    finally:
        for engine in engines:
            engine.dispose()


def test_a_claim_of_one_passes_a_unit_another_attempt_holds(databases, tmp_path):
    """Workers take one unit at a time: the first unit in order, held under
    another attempt's live lease, must not hide the ready one after it."""
    book, rid, _, _ = submit(databases, tmp_path, count=2)
    held = book.claim(rid, "s0", "0")
    (envelope,) = book.tasks(rid, "artifact.copy", limit=1)
    assert envelope["claim"]["key"] == "1"
    finish(book, envelope, copy)
    finish(book, book.envelope(held), copy)
    assert book.status(rid)["counts"] == {"verified": 2}


def test_a_source_with_acquisition_runs_captured_data_without_its_feed(databases, tmp_path):
    """A source that declares acquisition runs over captured data with no feed named. A run that names a
    feed whose producers the target lacks, or an empty feed, is refused at submit."""
    book = Bookkeeping(databases.runtime)
    body = config()
    name = f"pipes-{uuid4().hex}"
    fixture_feed(body, name, [])
    saved = frozen.of("source", name, body)
    units = book.artifacts.put(tmp_path.as_uri() + "/inputs", {"version": 1, "units": [
        {"keys": {"id": "0", "destination": (tmp_path / "out-0").as_uri()},
         "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", {"row": 0}),
         "output": (tmp_path / "out-0").as_uri(), "cursor": {"offset": 0}}]})
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)

    assert book.start(rules_ref=rules, inputs_ref=units, target="silver", scope={"source": name})
    with pytest.raises(Blocked, match="omits required acquisition producers"):
        book.start(rules_ref=rules, inputs_ref=units, target="silver", scope={"source": name, "feed": "fixture"})
    with pytest.raises(Blocked, match="declared feed's name"):
        book.start(rules_ref=rules, inputs_ref=units, target="silver", scope={"source": name, "feed": ""})


def test_a_capture_runs_only_with_its_feed(databases, tmp_path):
    book = Bookkeeping(databases.runtime)
    body = config()
    body["bookkeeping"]["targets"]["silver"]["steps"][0]["operation"] = "provider.capture"
    name = f"pipes-{uuid4().hex}"
    fixture_feed(body, name, [])
    saved = frozen.of("source", name, body)
    units = book.artifacts.put(tmp_path.as_uri() + "/inputs", {"version": 1, "units": [
        {"keys": {"id": "0", "destination": (tmp_path / "out-0").as_uri()},
         "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", {"row": 0}),
         "output": (tmp_path / "out-0").as_uri(), "cursor": {"offset": 0}}]})
    rules = Artifacts().put(tmp_path.as_uri() + "/rules", saved)
    with pytest.raises(Blocked, match="only as live acquisition"):
        book.start(rules_ref=rules, inputs_ref=units, target="silver", scope={"source": name})


def test_rules_run_submits_a_source_with_acquisition_over_captured_files(databases, tmp_path, monkeypatch, capsys):
    """`rules run` with no `--feed` binds the run to its source, so a switched-on source that
    declares acquisition runs over captured files (ticket 114; the first real run found it unbound)."""
    from edgar_warehouse.cli import main
    book = Bookkeeping(databases.runtime)
    body = config()
    name = f"pipes-{uuid4().hex}"
    fixture_feed(body, name, [])
    saved = frozen.of("source", name, body)
    inputs = book.artifacts.put(tmp_path.as_uri() + "/inputs", {"version": 1, "units": [
        {"keys": {"id": "0", "destination": (tmp_path / "out-0").as_uri()},
         "input": book.artifacts.put(tmp_path.as_uri() + "/inputs", {"row": 0}),
         "output": (tmp_path / "out-0").as_uri(), "cursor": {"offset": 0}}]})
    for key, value in {"DB_URL": databases.loader,
                       "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "cli-manifests").as_uri()}.items():
        monkeypatch.setenv(key, value)
    from edgar_warehouse.rules import files
    files.write_source(body, tmp_path / "rules-root" / "sources" / name)
    assert main(["rules", "run", "--source", name, "--target", "silver", "--root", str(tmp_path / "rules-root"),
                 "--input-manifest", inputs["uri"], "--input-sha256", inputs["sha256"]]) == 0
    submitted = json.loads(capsys.readouterr().out)
    assert submitted["run"]["submission"]["scope"] == {"kind": "source", "name": name, "source": name, "target": "silver"}
