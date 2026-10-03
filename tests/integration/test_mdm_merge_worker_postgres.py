"""MDM behind the worker protocol on real PG16 (mastering to-do 20e).

A Rules-submitted run's `mdm.merge` step is done by the worker, in its own
process with the MDM application login, and checked by a separate verifier
process that reads MDM back with another login. Bookkeeping never touches MDM.
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.destinations import migrate_guard
from edgar_warehouse.mdm.clean.store import register_policy
from edgar_warehouse.cli import main
from edgar_warehouse.workers import mdm_merge
from tests.integration import test_clean_mdm_postgres as core
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.support.rules_approval import approve

ROOT = Path(__file__).resolve().parents[2]
ENTRY = "import sys; from edgar_warehouse.cli import main; sys.exit(main(sys.argv[1:]))"  # `edgar-warehouse`
CONSUMERS = ("export", "graph", "journal")
PIPELINE = {
    "pipeline": "mdm-merge-fixture",
    "bookkeeping": {"version": 1, "targets": {"mdm": {
        "lease_seconds": 120, "heartbeat_seconds": 30,
        "retry": {"attempts": 5, "base_ms": 100, "cap_ms": 5000},
        "allow_zero_work": False,
        "steps": [{"name": "merge", "operation": "mdm.merge", "requires": [], "key": "{batch_id}",
                   "leases": ["mdm:consumer:{consumer}"],
                   "checks": ["input.hash", "output.receipt", "mdm.committed"]},
                  {"name": "publish", "operation": "mdm.publish", "requires": ["merge"],
                   "key": "{batch_id}:{consumer}", "leases": ["mdm:publication:{consumer}"],
                   "checks": ["input.hash", "output.receipt", "mdm.published"]}],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}},
}


@pytest.fixture
def mdm(databases):
    """A Clean MDM database in the same server, migrated and registered."""
    name = f"mdm_worker_{uuid4().hex[:8]}"
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    admin = create_engine(databases.admin.url.set(database=name))
    app = create_engine(admin.url.set(username="clean_application", password="test"))
    reader = create_engine(admin.url.set(username="bk_verifier", password="test"))
    try:
        built = core.initialize_database(admin, app)
        # Every MDM commit is fenced by the worker's live Bookkeeping lease.
        migrate_guard(admin, runtime_role="clean_application")
        with admin.begin() as conn:  # the Change Journal is a consumer too
            policy = register_policy(conn, {"version": 1, "required_consumers": list(CONSUMERS),
                                            "automatic_rules": [], "fields": {"company": {
                                                "name": {"sources": ["fixture.primary", "fixture.secondary"]}}}})
        with admin.begin() as conn:
            conn.exec_driver_sql("GRANT USAGE ON SCHEMA mdm TO bk_verifier")
            conn.exec_driver_sql("GRANT SELECT ON ALL TABLES IN SCHEMA mdm TO bk_verifier")
        yield SimpleNamespace(admin=admin, application=app, reader=reader, policy=policy)
    finally:
        admin.dispose()
        app.dispose()
        reader.dispose()


def _manifest(policy, tmp_path, store):
    batches = []
    for n, key in enumerate(("acme", "globex"), 1):
        reading = core.source(key=key, fields={"name": key.title()})
        identity, binding = core.identity_and_binding(reading)
        batches.append({"batch_id": f"fixture-{key}", "stage": "mastering", "consumer": f"fixture/{key}",
                        "expected_checkpoint": 0, "checkpoint": 1,
                        "assertions": [reading], "identities": [identity], "decisions": [binding]})
    manifest = {"contract_version": 2, "as_of": core.AS_OF, "policy_digest": policy, "batches": batches}
    return store.put(tmp_path.as_uri() + "/mdm", manifest), batches


def test_a_rules_submitted_merge_is_done_by_a_worker_and_checked_by_another_login(databases, mdm, tmp_path,
                                                                                    monkeypatch, capsys):
    store = Artifacts()
    for profile in ("mdm.merge", "mdm.publish"):
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    saved = databases.rules.save("pipeline", "mdm-merge-fixture", "1", PIPELINE)
    manifest_ref, batches = _manifest(mdm.policy, tmp_path, store)
    out = tmp_path / "out"
    units = store.put(tmp_path.as_uri(), {"version": 2, "steps": {
        "merge": [{"keys": {"batch_id": "fixture", "consumer": "fixture"}, "input": manifest_ref,
                   "output": (out / "merge.json").as_uri(), "cursor": {"offset": 0}}],
        "publish": [{"keys": {"batch_id": b["batch_id"], "consumer": c},
                     "input": {"from": {"step": "merge", "key": "fixture"}},
                     "output": (out / f"{b['batch_id']}.{c}.json").as_uri(), "cursor": {"offset": 0}}
                    for b in batches for c in CONSUMERS]}})
    databases.rules.prove("pipeline", "mdm-merge-fixture", "1",
                          {"digest": saved["digest"], "batch_hash": units["sha256"], "passed": True})
    approve(databases.approver, "pipeline", "mdm-merge-fixture", "1")  # MDM work needs the operator's approval
    databases.rules.activate("pipeline", "mdm-merge-fixture", "1")
    url = lambda engine: engine.url.render_as_string(hide_password=False)
    env = {**os.environ,
           "BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.runtime),
           "RULES_DATABASE_URL": url(databases.rules.engine),
           "CHANGE_JOURNAL_DATABASE_URL": url(databases.ledger.engine),
           "BOOKKEEPING_MANIFEST_ROOT": (tmp_path / "control").as_uri()}
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert main(["rules", "run", "--pipeline", "mdm-merge-fixture", "--target", "mdm",
                 "--input-manifest", units["uri"], "--input-sha256", units["sha256"]]) == 0
    run_id = json.loads(capsys.readouterr().out)["run"]["run_id"]

    def command(*args, **extra):
        done = subprocess.run([sys.executable, "-c", ENTRY, *args], env={**env, **extra},
                              cwd=ROOT, text=True, capture_output=True)
        assert done.returncode == 0, done.stderr
        return done.stdout

    worker = {"MDM_DATABASE_URL": url(mdm.application), "MDM_APPLICATION_ROLE": "clean_application"}
    verifier = {"BOOKKEEPING_CLEAN_DATABASE_URL": url(databases.verifier), "MDM_DATABASE_URL": url(mdm.reader)}
    reports = ("--reports", (tmp_path / "reports").as_uri())
    command("workers", "work", "mdm.merge", run_id, **worker)
    with mdm.admin.connect() as conn:
        assert set(conn.scalars(text("SELECT batch_id FROM mdm.batch"))) == {b["batch_id"] for b in batches}
    state = json.loads(command("bookkeeping", "status", run_id))
    assert state["counts"] == {"reported": 1, "pending": 6}  # no unit completes on the worker's word
    command("workers", "verify", "mdm.merge", run_id, *reports, **verifier)
    # A consumer's publication lease admits one unit at a time, in generation
    # order: each pass delivers one batch per consumer, so passes repeat.
    for _ in range(3):
        command("workers", "work", "mdm.publish", run_id, "--limit", "10", **worker)
        command("workers", "verify", "mdm.publish", run_id, *reports, "--limit", "10", **verifier)
        if json.loads(command("bookkeeping", "status", run_id))["counts"] == {"verified": 7}:
            break
    state = json.loads(command("bookkeeping", "finalize", run_id))
    assert state["counts"] == {"verified": 7} and state["run"]["state"] == "complete"
    receipt = json.loads((out / "merge.json").read_bytes())
    assert [b["batch_id"] for b in receipt["batches"]] == ["fixture-acme", "fixture-globex"]
    with mdm.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.outbox WHERE verified_at IS NULL")) == 0
    for consumer in ("export", "graph"):
        assert len(list((out / consumer).glob("*.json"))) == 2  # one contract file per batch
    owner = create_engine(databases.admin.url.set(database="change_journal_clean"))
    with owner.connect() as conn:
        events = conn.execute(text("SELECT event_key, run_id::text AS run_id, source FROM journal.event "
                                   "WHERE producer='mdm' ORDER BY event_key")).mappings().all()
    assert [e["event_key"] for e in events] == ["journal/fixture-acme", "journal/fixture-globex"]
    owner.dispose()
    assert {e["run_id"] for e in events} == {run_id} and {e["source"] for e in events} == {"mdm-merge-fixture"}


def _proof(minutes):
    expires = datetime.now(UTC) + timedelta(minutes=minutes)
    return [{"resource": "mdm:consumer:fixture", "token": 1, "run_id": str(uuid4()), "attempt": str(uuid4()),
             "expires_at": expires.isoformat()}]


def test_a_lost_acknowledgement_resumes_the_same_mdm_run_and_merges_once(mdm, tmp_path, monkeypatch):
    store = Artifacts()
    manifest_ref, _ = _manifest(mdm.policy, tmp_path, store)
    envelope = {"effect_key": "e" * 64, "input": manifest_ref, "output": (tmp_path / "receipt.json").as_uri(),
                "checks": ["mdm.committed"], "claim": {"proof": _proof(5)}}
    monkeypatch.setenv("MDM_DATABASE_URL", mdm.application.url.render_as_string(hide_password=False))
    monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
    first = mdm_merge.execute(envelope, store)
    second = mdm_merge.execute(envelope, store)  # the first report was lost
    assert first == second
    with mdm.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 2
        assert conn.scalar(text("SELECT count(*) FROM mdm.run")) == 1
    # A receipt that is not what MDM holds is refused by the verifier.
    forged = store.put_bytes((tmp_path / "forged.json").as_uri(), b'{"version":1}')
    monkeypatch.setenv("MDM_DATABASE_URL", mdm.reader.url.render_as_string(hide_password=False))
    with pytest.raises(ValueError, match="differs from what MDM holds"):
        mdm_merge.verify({**envelope, "output": forged["uri"], "candidate": forged}, store)
    checks, _ = mdm_merge.verify({**envelope, "candidate": first}, store)
    assert checks == {"mdm.committed": True}
    changed = store.json(manifest_ref)
    changed["as_of"] = "2026-01-01T00:00:00Z"
    changed_ref = store.put(tmp_path.as_uri() + "/changed", changed)
    with pytest.raises(ValueError, match="scope differs"):
        mdm_merge.verify({**envelope, "input": changed_ref, "candidate": first}, store)
    with mdm.reader.begin() as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            conn.exec_driver_sql("DELETE FROM mdm.batch")


def test_mdm_refuses_a_merge_whose_lease_has_lapsed(mdm, tmp_path, monkeypatch):
    store = Artifacts()
    manifest_ref, _ = _manifest(mdm.policy, tmp_path, store)
    envelope = {"effect_key": "f" * 64, "input": manifest_ref, "output": (tmp_path / "receipt.json").as_uri(),
                "checks": ["mdm.committed"], "claim": {"proof": _proof(-1)}}
    monkeypatch.setenv("MDM_DATABASE_URL", mdm.application.url.render_as_string(hide_password=False))
    monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
    with pytest.raises(DBAPIError, match="Expired destination authority"):
        mdm_merge.execute(envelope, store)
    with mdm.admin.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.batch")) == 0
    assert not (tmp_path / "receipt.json").exists()
