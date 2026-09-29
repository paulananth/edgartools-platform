"""Approval on test evidence, by saying so (rules skill ticket 14): PG16.

Migration 003 is applied to a Rules Database already holding versions,
including one approved the old way, as it will be on the operator's."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.config import Blocked
from edgar_warehouse.rules import db as rules_db
from edgar_warehouse.rules.db import Rules, migrate, proof_holds

BATCH = "a" * 64


def pipeline(change=0):
    return {"source": "fixture", "change": change, "bookkeeping": {"version": 1, "targets": {"silver": {
        "lease_seconds": 120, "heartbeat_seconds": 30, "retry": {"attempts": 2, "base_ms": 1, "cap_ms": 2},
        "allow_zero_work": False, "steps": [{"name": "s0", "operation": "artifact.copy", "requires": [],
                                             "key": "{id}", "leases": ["output:{destination}"],
                                             "checks": ["input.hash", "output.receipt"]}],
        "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}


def proof(saved, passed=True, **extra):
    return {"digest": saved["digest"], "batch_hash": BATCH, "passed": passed, **extra}


@pytest.fixture(scope="module")
def pg():
    assert shutil.which("docker"), "PG16 acceptance requires Docker (Colima on macOS)"
    name = f"rules-approval-{uuid4().hex[:10]}"
    subprocess.run(["docker", "run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_PASSWORD=test", "postgres:16-alpine"], capture_output=True, check=True)
    engines = []
    try:
        for _ in range(100):
            if subprocess.run(["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True).returncode == 0:
                break
            time.sleep(0.1)
        port = subprocess.run(["docker", "port", name, "5432/tcp"], capture_output=True, text=True,
                              check=True).stdout.strip().rsplit(":", 1)[1]

        def engine(db, user="postgres"):
            value = create_engine(f"postgresql://{user}:test@127.0.0.1:{port}/{db}")
            engines.append(value)
            return value

        deadline = time.monotonic() + 30
        while True:
            try:
                with engine("postgres").connect() as conn:
                    conn.execute(text("SELECT 1"))
                break
            except DBAPIError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        with engine("postgres").connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for role in ("rules_agent", "operator"):
                conn.exec_driver_sql(f"CREATE ROLE {role} LOGIN PASSWORD 'test'")
            conn.exec_driver_sql("CREATE ROLE rules_approver NOLOGIN")
            conn.exec_driver_sql("GRANT rules_approver TO operator")
            conn.exec_driver_sql("CREATE DATABASE rules")
        yield {"owner": engine("rules"), "agent": Rules(engine("rules", "rules_agent")),
               "approver": Rules(engine("rules", "operator"))}
    finally:
        for value in engines:
            value.dispose()
        subprocess.run(["docker", "stop", "--time", "1", name], capture_output=True)


@pytest.fixture(scope="module")
def populated(pg):
    """The Rules Database as it stands before 003, holding a draft, a proven
    version and one approved and activated the old way; then 003 applied."""
    # Exactly what migrate() did before 003: its SQL, checksums and grants.
    real = sorted((Path(rules_db.__file__).parent / "migrations").glob("00[12]_*.sql"))
    with pg["owner"].begin() as conn:
        for path in real:
            conn.execute(text(path.read_text()))
        checksums = json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in real},
                               sort_keys=True, separators=(",", ":"))
        conn.exec_driver_sql(f"COMMENT ON SCHEMA rules IS '{checksums}'")
        conn.exec_driver_sql("GRANT USAGE ON SCHEMA rules TO rules_agent,rules_approver")
        conn.exec_driver_sql("GRANT SELECT ON rules.rule_version TO rules_agent,rules_approver")
        conn.exec_driver_sql("GRANT INSERT(kind,name,version,body,digest) ON rules.rule_version TO rules_agent")
        conn.exec_driver_sql("GRANT UPDATE(status,proof,batch_hash,clean_mdm) ON rules.rule_version TO rules_agent")
        conn.exec_driver_sql("GRANT UPDATE(approved_by,approved_at) ON rules.rule_version TO rules_approver")
    agent, approver = pg["agent"], pg["approver"]
    old = {}
    for label in ("draft", "proven", "approved"):
        body = pipeline()
        body["mdm"] = {"fixture": {"contract": {}}}
        saved = agent.save("pipeline", f"old-{label}-{uuid4().hex[:8]}", "1", body)
        old[label] = saved
        if label != "draft":
            agent.prove("pipeline", saved["name"], "1", proof(saved))
    with approver.engine.begin() as conn:  # the old way: the approver's own login
        conn.execute(text("UPDATE rules.rule_version SET approved_by=session_user,approved_at=clock_timestamp() "
                          "WHERE name=:n"), {"n": old["approved"]["name"]})
    agent.activate("pipeline", old["approved"]["name"], "1")
    after = migrate(pg["owner"])
    assert "003_approval_on_evidence.sql" in after
    assert migrate(pg["owner"]) == after  # a rerun changes nothing
    return old


def row(pg, name, version="1"):
    return pg["agent"].version("pipeline", name, version)


def test_rows_approved_the_old_way_survive_003(pg, populated):
    kept = row(pg, populated["approved"]["name"])
    assert (kept["status"], kept["approved_by"], kept["approved_words"]) == ("active", "operator", None)
    assert row(pg, populated["proven"]["name"])["status"] == "proven"
    assert row(pg, populated["draft"]["name"])["proof"] is None
    # A version proven before 003 is approved the new way, on its evidence.
    approved = pg["agent"].approve("pipeline", populated["proven"]["name"], by="Operator", words="approved")
    assert approved["approval_recorded_by"] == "rules_agent"


def test_no_approval_without_test_evidence(pg, populated):
    name = populated["draft"]["name"]
    with pytest.raises(Blocked, match="test evidence"):
        pg["agent"].approve("pipeline", name, by="Operator", words="approved")
    with pytest.raises(Blocked, match="No approval without test evidence"):
        pg["agent"].approve("pipeline", name, "1", by="Operator", words="approved")
    with pytest.raises(DBAPIError, match="No approval without test evidence"), pg["agent"].engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET approved_by='Operator',approved_words='approved' "
                          "WHERE name=:n"), {"n": name})


def test_approval_by_saying_so_records_name_words_evidence_and_login(pg, populated):
    agent = pg["agent"]
    saved = agent.save("pipeline", f"pass-{uuid4().hex[:8]}", "1", pipeline())
    agent.prove("pipeline", saved["name"], "1", proof(saved, evidence={"counts": {"records": 10}}))
    with pytest.raises(DBAPIError, match="exact words"), agent.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET approved_by='Operator',approved_words=' ' WHERE name=:n"),
                     {"n": saved["name"]})
    with pytest.raises(DBAPIError, match="nothing to overrule"):
        agent.approve("pipeline", saved["name"], by="Operator", words="approved", overrule="no need")
    approved = agent.approve("pipeline", saved["name"], by="Operator", words="Yes, approve the fixture source")
    assert (approved["approved_by"], approved["approved_words"], approved["approval_recorded_by"]) == (
        "Operator", "Yes, approve the fixture source", "rules_agent")
    with agent.engine.connect() as conn:
        assert approved["approval_evidence"] == conn.scalar(text(
            "SELECT encode(sha256(convert_to(proof::text,'UTF8')),'hex') FROM rules.rule_version WHERE name=:n"),
            {"n": saved["name"]})
    with pytest.raises(DBAPIError, match="never changed"), agent.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET approved_words='something else' WHERE name=:n"),
                     {"n": saved["name"]})
    with pytest.raises(DBAPIError, match="immutable"):
        agent.prove("pipeline", saved["name"], "1", proof(saved, note="another run"))
    agent.activate("pipeline", saved["name"], "1")
    envelope = Rules.envelope(row(pg, saved["name"]))
    assert envelope["approval"]["words"] == "Yes, approve the fixture source"
    assert envelope["approval"]["recorded_by"] == "rules_agent" and proof_holds(envelope)


def test_a_failing_run_is_kept_and_approved_only_with_an_overrule(pg, populated):
    agent = pg["agent"]
    body = pipeline()
    body["mdm"] = {"fixture": {"contract": {}}}
    saved = agent.save("pipeline", f"fail-{uuid4().hex[:8]}", "1", body)
    agent.prove("pipeline", saved["name"], "1", proof(saved, passed=False, note="first run"))
    assert row(pg, saved["name"])["status"] == "draft"
    agent.prove("pipeline", saved["name"], "1", proof(saved, passed=False, note="second run"))  # replaceable
    assert row(pg, saved["name"])["proof"]["note"] == "second run"
    with pytest.raises(Blocked, match="Only a proven version"):
        agent.activate("pipeline", saved["name"], "1")
    with pytest.raises(Blocked, match="overrule reason"):
        agent.approve("pipeline", saved["name"], by="Operator", words="approved")
    with pytest.raises(DBAPIError, match="overrule reason"), agent.engine.begin() as conn:
        conn.execute(text("UPDATE rules.rule_version SET approved_by='Operator',approved_words='approved' "
                          "WHERE name=:n"), {"n": saved["name"]})
    approved = agent.approve("pipeline", saved["name"], by="Operator", words="approve it anyway",
                             overrule="9 of 10 is enough for a fixture")
    assert (approved["status"], approved["approval_overrule"]) == ("proven", "9 of 10 is enough for a fixture")
    agent.activate("pipeline", saved["name"], "1")
    envelope = Rules.envelope(row(pg, saved["name"]))
    assert envelope["approval"]["overrule"] == "9 of 10 is enough for a fixture" and proof_holds(envelope)
    assert not proof_holds({**envelope, "approval": {**envelope["approval"], "overrule": None}})


def test_pending_lists_evidence_and_changes_from_the_active_version(pg, populated):
    agent = pg["agent"]
    name = f"pending-{uuid4().hex[:8]}"
    first = agent.save("pipeline", name, "1", pipeline())
    agent.prove("pipeline", name, "1", proof(first))
    agent.approve("pipeline", name, by="Operator", words="approved")
    agent.activate("pipeline", name, "1")
    second = agent.save("pipeline", name, "2", pipeline(change=1))
    agent.prove("pipeline", name, "2", proof(second, evidence={"counts": {"changed": 1}, "examples": ["one"]},
                                             note="one value changes"))
    listed = [p for p in agent.pending() if p["name"] == name]
    assert listed == [{"kind": "pipeline", "name": name, "version": "2", "passed": True,
                       "evidence": {"counts": {"changed": 1}, "examples": ["one"]}, "note": "one value changes",
                       "proved_at": listed[0]["proved_at"], "changes": ["changed change: 0 -> 1"]}]
    assert agent.approve("pipeline", name, by="Operator", words="approved")["version"] == "2"
    assert not [p for p in agent.pending() if p["name"] == name]
    json.dumps(agent.pending(), default=str)
