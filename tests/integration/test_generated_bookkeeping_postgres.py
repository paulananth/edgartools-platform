"""PG16 generated work is sealed atomically within the original root."""
from copy import deepcopy
from uuid import uuid4, uuid5, UUID

import pytest
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import Authority, run
from tests.integration.test_configured_bookkeeping_postgres import databases, expire


def _fixture(databases, tmp_path):
    book = Bookkeeping(databases.runtime, standard_registry())
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
    claim = book.claim(rid, "parent", "p1")
    assert claim is not None
    capability = book.registry.operations["artifact.copy"]
    receipt = capability.execute(book, book.item(claim), Authority(claim))
    book.record_verified_completion(claim, receipt)
    state = book.status(rid)
    assert state["run"]["expected_count"] == 2
    assert state["counts"] == {"verified": 1, "pending": 1}
    assert len(state["deliveries"]) == 1
    book.record_verified_completion(claim, receipt)
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
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    assert book.deliver(databases.ledger, rid) == 0


def test_stale_expansion_cannot_insert_children(databases, tmp_path):
    book, rid, _ = _fixture(databases, tmp_path)
    claim = book.claim(rid, "parent", "p1")
    receipt = book.registry.operations["artifact.copy"].execute(book, book.item(claim), Authority(claim))
    expire(databases, claim)
    with pytest.raises(DBAPIError):
        book.record_verified_completion(claim, receipt)
    assert book.status(rid)["run"]["expected_count"] == 1
    assert book.status(rid)["counts"] == {"running": 1}


def test_unsealed_expansion_blocks_root(databases, tmp_path):
    book, rid, _ = _fixture(databases, tmp_path)
    claim = book.claim(rid, "parent", "p1")
    receipt = book.registry.operations["artifact.copy"].execute(book, book.item(claim), Authority(claim))
    book._call("SELECT bookkeeping.finish(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid))",
               r=rid, s="parent", k="p1", a=claim.attempt, p=canonical(claim.proof),
               v=canonical(receipt), c=canonical({"input.hash": True, "output.receipt": True}),
               e=str(uuid5(UUID(rid), "parent:p1")))
    with pytest.raises(Blocked, match="without sealing"):
        book.finalize(rid)
    assert book.status(rid)["run"]["state"] == "blocked"
