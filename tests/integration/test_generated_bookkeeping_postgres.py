"""PG16 generated work is sealed atomically within the original root."""
from copy import deepcopy
from uuid import uuid4, uuid5, UUID

import pytest
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.workers import copy
from tests.integration.test_configured_bookkeeping_postgres import databases, expire
from tests.support.bookkeeping_protocol import RUNTIME, drive, verification_for, verification_report


def _reported(book, rid):
    """Claim the parent, copy its expansion manifest and report it."""
    claim = book.claim(rid, "parent", "p1")
    envelope = book.envelope(claim)
    candidate = copy.execute(envelope, book.artifacts)
    book.report(envelope, candidate, RUNTIME)
    return claim, candidate


def _fixture(databases, tmp_path):
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    body = {"source": "generated-fixture", "bookkeeping": {"version": 1, "targets": {
        "generated": {"allow_zero_work": True,
            "steps": [
                {"name": "parent", "operation": "artifact.copy", "requires": [], "key": "{id}",
                 "leases": ["output:{id}"], "checks": ["input.hash", "output.receipt"]},
                {"name": "child", "operation": "artifact.copy", "requires": ["parent"], "key": "{id}",
                 "leases": ["output:{id}"], "checks": ["input.hash", "output.receipt"]},
            ], "checks": ["manifest.hash", "work.accounting", "journal.delivered"]}}}}
    saved = databases.rules.save("source", "generated-fixture", uuid4().hex, body)
    databases.rules.prove("source", "generated-fixture", saved["version"],
                          {"digest": saved["digest"], "batch_hash": "0" * 64, "passed": True})
    databases.rules.activate("source", "generated-fixture", saved["version"])
    rules_ref = databases.rules.resolve("source", "generated-fixture",
                                        root=tmp_path.as_uri() + "/rules")
    source = book.artifacts.put(tmp_path.as_uri() + "/source", {"row": 1})
    child = {"keys": {"id": "c1"}, "input": source,
             "output": (tmp_path / "child.json").as_uri(), "cursor": {}}
    parent = {"step": "parent", "key": "p1", "generated_step": "child", "ordinal_base": 0}
    expansion = {"version": 1, "parent": parent, "children": [child]}
    input_ref = book.artifacts.put(tmp_path.as_uri() + "/expansion-input", expansion)
    unit = {"keys": {"id": "p1"}, "input": input_ref,
            "output": (tmp_path / "expansion.json").as_uri(),
            "cursor": {"generated_step": "child", "ordinal_base": 0}}
    manifest = book.artifacts.put(tmp_path.as_uri() + "/manifest",
        {"version": 2, "steps": {"parent": [unit], "child": []}})
    rid = book.start(rules_ref=rules_ref, inputs_ref=manifest, target="generated", scope={})
    return book, rid, child


def test_generated_children_and_parent_intent_commit_together(databases, tmp_path):
    book, rid, child = _fixture(databases, tmp_path)
    claim, candidate = _reported(book, rid)
    verification = verification_for(book, rid, "parent", "p1")
    report = verification_report(book, verification, copy)
    book.verifier.admit(verification, report)
    receipt = {**candidate, "evidence": report}
    state = book.status(rid)
    assert state["run"]["expected_count"] == 2
    assert state["counts"] == {"verified": 1, "pending": 1}
    assert len(state["deliveries"]) == 1
    book.verifier.admit(verification, report)  # lost acknowledgement
    assert book.status(rid)["run"]["expected_count"] == 2
    changed = deepcopy(book._frozen(rid)[3][1])
    changed["unit"]["output"] += ".changed"
    with pytest.raises(DBAPIError):
        book._call("SELECT bookkeeping.finish_expand(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),CAST(:children AS jsonb),:child_step)",
                   r=rid, s="parent", k="p1", a=claim.attempt, p=canonical(claim.proof),
                   v=canonical(receipt), c=canonical({"input.hash": True, "output.receipt": True}),
                   e=str(uuid5(UUID(rid), "parent:p1")), children=canonical([changed]),
                   child_step="child")
    with pytest.raises(DBAPIError):
        book._call("SELECT bookkeeping.finish_expand(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),CAST(:children AS jsonb),:child_step)",
                   r=rid, s="parent", k="p1", a=claim.attempt, p=canonical(claim.proof),
                   v=canonical(receipt), c=canonical({"input.hash": True, "output.receipt": True}),
                   e=str(uuid5(UUID(rid), "parent:p1")), children=canonical([book._frozen(rid)[3][1]] * 2),
                   child_step="child")
    assert book.status(rid)["run"]["expected_count"] == 2
    assert drive(book, rid, databases.ledger)["run"]["state"] == "complete"
    assert book.deliver(databases.ledger, rid) == 0


def test_stale_expansion_cannot_insert_children(databases, tmp_path):
    book, rid, _ = _fixture(databases, tmp_path)
    claim, _ = _reported(book, rid)
    verification = verification_for(book, rid, "parent", "p1")
    report = verification_report(book, verification, copy)
    expire(databases, claim)
    with pytest.raises(DBAPIError):
        book.verifier.admit(verification, report)
    assert book.status(rid)["run"]["expected_count"] == 1
    assert book.status(rid)["counts"] == {"reported": 1}


def test_unsealed_expansion_blocks_root(databases, tmp_path):
    book, rid, _ = _fixture(databases, tmp_path)
    claim, candidate = _reported(book, rid)
    receipt = {**candidate, "evidence": book.artifacts.put(tmp_path.as_uri() + "/evidence", {"unsealed": True})}
    book.verifier._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
               r=rid, s="parent", k="p1", a=claim.attempt, p=canonical(claim.proof),
               v=canonical(receipt), c=canonical({"input.hash": True, "output.receipt": True}),
               e=str(uuid5(UUID(rid), "parent:p1")))
    with pytest.raises(Blocked, match="without sealing"):
        book.finalize(rid)
    assert book.status(rid)["run"]["state"] == "blocked"


def test_task_protocol_migration_keeps_populated_control_rows(databases):
    """005 applied over 001-004 with runs and work in every old state."""
    from pathlib import Path
    from sqlalchemy import create_engine, text

    folder = Path(__file__).resolve().parents[2] / "edgar_warehouse/bookkeeping/clean/migrations"
    name = "bk_populated_" + uuid4().hex[:8]
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    engine = create_engine(databases.admin.url.set(database=name))
    try:
        with engine.begin() as conn:
            for path in sorted(folder.glob("00[1-4]_*.sql")):
                conn.exec_driver_sql(path.read_text().replace("%", "%%"))
            rid = str(uuid4())
            conn.execute(text("INSERT INTO bookkeeping.pipeline_run(run_id,submission,submission_hash,expected_count) "
                              "VALUES(CAST(:r AS uuid),'{}',:h,3)"), {"r": rid, "h": "0" * 64})
            for n, state in enumerate(("pending", "running", "verified")):
                conn.execute(text("INSERT INTO bookkeeping.work_item(run_id,step,unit_key,ordinal,resources,unit,state,receipt) "
                                  "VALUES(CAST(:r AS uuid),'s0',:k,:o,'[\"a\"]','{}',:s,CAST(:v AS jsonb))"),
                             {"r": rid, "k": str(n), "o": n, "s": state,
                              "v": '{"uri":"file:///x","sha256":"%s","evidence":{}}' % ("0" * 64) if state == "verified" else None})
        with engine.begin() as conn:
            conn.exec_driver_sql((folder / "005_task_protocol.sql").read_text().replace("%", "%%"))
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT unit_key,state,candidate FROM bookkeeping.work_item ORDER BY ordinal")).all()
            assert [(r.unit_key, r.state, r.candidate) for r in rows] == [
                ("0", "pending", None), ("1", "running", None), ("2", "verified", None)]
            assert conn.scalar(text("SELECT runtimes FROM bookkeeping.pipeline_run")) == {}
            conn.execute(text("UPDATE bookkeeping.work_item SET state='reported',candidate='{}' WHERE unit_key='1'"))
        with pytest.raises(DBAPIError), engine.begin() as conn:
            conn.execute(text("UPDATE bookkeeping.work_item SET state='done' WHERE unit_key='0'"))
        with pytest.raises(DBAPIError, match="reported candidate"), engine.begin() as conn:
            conn.execute(text("UPDATE bookkeeping.work_item SET state='verified' WHERE unit_key='0'"))
    finally:
        engine.dispose()


def test_issuer_migration_keeps_populated_runs_and_refuses_unfrozen_profiles(databases):
    """006 over 001-005 with a run in every state; a run frozen before 006
    names no profiles, so no login may work it."""
    from pathlib import Path
    from sqlalchemy import create_engine, text

    folder = Path(__file__).resolve().parents[2] / "edgar_warehouse/bookkeeping/clean/migrations"
    name = "bk_issuers_" + uuid4().hex[:8]
    with databases.admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    engine = create_engine(databases.admin.url.set(database=name))
    try:
        with engine.begin() as conn:
            for path in sorted(folder.glob("00[1-5]_*.sql")):
                conn.exec_driver_sql(path.read_text().replace("%", "%%"))
            rid = str(uuid4())
            conn.execute(text("INSERT INTO bookkeeping.pipeline_run(run_id,submission,submission_hash,expected_count) "
                              "VALUES(CAST(:r AS uuid),'{}',:h,4)"), {"r": rid, "h": "0" * 64})
            for n, state in enumerate(("pending", "running", "reported", "waiting")):
                conn.execute(text("INSERT INTO bookkeeping.work_item(run_id,step,unit_key,ordinal,resources,unit,state,candidate) "
                                  "VALUES(CAST(:r AS uuid),'s0',:k,:o,'[\"a\"]','{}',:s,CAST(:c AS jsonb))"),
                             {"r": rid, "k": str(n), "o": n, "s": state,
                              "c": '{"uri":"file:///x","sha256":"%s"}' % ("0" * 64) if state == "reported" else None})
        with engine.begin() as conn:
            conn.exec_driver_sql((folder / "006_issuer_roles.sql").read_text().replace("%", "%%"))
        with engine.begin() as conn:
            rows = conn.execute(text("SELECT unit_key,state,candidate,reporter FROM bookkeeping.work_item ORDER BY ordinal")).all()
            assert [(r.unit_key, r.state, r.reporter) for r in rows] == [
                ("0", "pending", None), ("1", "running", None), ("2", "reported", None), ("3", "waiting", None)]
            assert rows[2].candidate == {"uri": "file:///x", "sha256": "0" * 64}
            assert conn.scalar(text("SELECT bookkeeping.frozen_profile(CAST(:r AS uuid),'s0')"), {"r": rid}) is None
            names = {conn.scalar(text("SELECT bookkeeping.profile_role(:p,'worker')"), {"p": p}) for p in ("a.b", "a_b", "a-b")}
            assert len(names) == 3 and all(len(n) <= 63 for n in names)
        with pytest.raises(DBAPIError, match="no worker role for profile \\(none\\)"), engine.begin() as conn:
            conn.execute(text("SELECT bookkeeping.claim(CAST(:r AS uuid),'s0','0',CAST(:a AS uuid),60,'[]')"),
                         {"r": rid, "a": str(uuid4())})
    finally:
        engine.dispose()
