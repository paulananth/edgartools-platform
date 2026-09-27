"""Source manifest invariants and original-key delivery under configured work."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, digest
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import run
from edgar_warehouse.change_journal.source_evidence import register_source_evidence
from tests.integration.test_change_journal_acquisition_postgres import definition
from tests.integration.test_configured_bookkeeping_postgres import databases


def manifest_run(databases, tmp_path, kind, *, damage=None):
    registry = standard_registry()
    register_source_evidence(registry)
    book = Bookkeeping(databases.runtime, registry)
    name = "evidence-" + uuid4().hex
    key = uuid4().hex
    raw = book.artifacts.put(tmp_path.as_uri() + "/raw", {"record": "one"})
    foreign = book.artifacts.put(tmp_path.as_uri() + "/raw", {"record": "different"})
    scope_proof = book.artifacts.put(
        tmp_path.as_uri() + "/proof", {"scope": "one", "expected": 0, "verified": True}
    )
    evidence = [raw, foreign, scope_proof]
    body = {"reason": "bounded operator fixture", "owner_role": "ACQUISITION_OPERATOR"}
    if kind == "source.revision":
        body = {
            "raw": raw,
            "canonical": raw,
            "domain": raw,
            "processing_versions": {"parser": "1", "schema": "1", "configuration": "1"},
            "completeness": "full_snapshot",
            "scope_complete": scope_proof,
            "prior": None,
            "relationship": "initial",
            "position": 0,
        }
    elif kind == "source.conflict":
        body = {"existing": raw, "quarantine": foreign}
    elif kind == "source.imported":
        body.update(
            foreign_artifact=foreign,
            source_environment="offline-other",
            expected_checksum=foreign["sha256"],
        )
    elif kind in {"producer.verified", "scope.empty"}:
        body = {
            "expected": 0,
            "verified": 0,
            "producer": "capture",
            "scope_complete": scope_proof,
        }
    elif kind == "source.conflict_resolved":
        conflict = book.artifacts.put(
            tmp_path.as_uri() + "/conflicts",
            {
                "version": 1,
                "source": name,
                "feed": "manifests",
                "scope": {"logical_key": "one"},
                "kind": "source.conflict",
                "event_key": "original-conflict",
                "evidence": [raw, foreign],
                "body": {"existing": raw, "quarantine": foreign},
            },
        )
        body.update(conflict=conflict, selected=foreign)
        evidence.append(conflict)
    authorizations = []
    if kind in {"source.imported", "source.excluded", "source.conflict_resolved"}:
        authorization = book.artifacts.put(
            tmp_path.as_uri() + "/authorization",
            {
                "source": name,
                "feed": "manifests",
                "scope": {"logical_key": "one"},
                "kind": kind,
                "event_key": key,
                "body_digest": digest(body),
            },
        )
        body["authorization"] = authorization
        evidence.append(authorization)
        authorizations.append(authorization)
    if damage:
        damage(body)
    spec = {
        "version": 1,
        "source": name,
        "feed": "manifests",
        "scope": {"logical_key": "one"},
        "kind": kind,
        "event_key": key,
        "evidence": evidence,
        "body": body,
    }
    ref = book.artifacts.put(tmp_path.as_uri() + "/manifests", spec)
    resource = "manifest:" + name
    cursor = (
        {"resource_checkpoint": {"resource": resource, "revision": 0, "position": -1}}
        if kind == "source.revision"
        else {}
    )
    unit = {
        "keys": {
            "id": key,
            "logical_key": "one",
            "journal_event_key": key,
            "journal_event_type": kind,
            "journal_producer": "source.evidence",
        },
        "input": ref,
        "output": (tmp_path / (key + ".outcome")).as_uri(),
        "cursor": cursor,
    }
    inputs = book.artifacts.put(
        tmp_path.as_uri() + "/work", {"version": 2, "steps": {"evidence": [unit]}}
    )
    selected = definition()
    selected["authorizations"] = authorizations
    document = {
        "source": name,
        "acquisition": {"version": 1, "feeds": {"manifests": selected}},
        "bookkeeping": {
            "version": 1,
            "targets": {
                "evidence": {
                    "steps": [
                        {
                            "name": "evidence",
                            "operation": "source.evidence",
                            "requires": [],
                            "key": "{id}",
                            "leases": [resource],
                            "checks": ["input.hash", "output.receipt"],
                        }
                    ],
                    "checks": ["manifest.hash", "work.accounting", "journal.delivered"],
                }
            },
        },
    }
    saved = databases.rules.save("source", name, "1", document)
    databases.rules.prove(
        "source",
        name,
        "1",
        {
            "digest": saved["digest"],
            "passed": True,
            "batch_hash": inputs["sha256"],
            "acquisition": {
                "manifests": {
                    "manifest": inputs,
                    "counts": {"capture": {"expected": 1, "verified": 1}},
                    "checks": {"offline": True},
                }
            },
        },
    )
    databases.approver.approve("source", name, "1", saved["digest"])
    databases.rules.activate("source", name, "1")
    rules_ref = databases.rules.resolve(
        "source", name, root=tmp_path.as_uri() + "/rules"
    )
    rid = book.start(
        rules_ref=rules_ref,
        inputs_ref=inputs,
        target="evidence",
        scope={"source": name, "feed": "manifests"},
    )
    return book, rid, key, resource


@pytest.mark.parametrize(
    "kind",
    [
        "source.revision",
        "source.conflict",
        "source.conflict_resolved",
        "source.imported",
        "source.excluded",
        "producer.verified",
        "scope.empty",
    ],
)
def test_source_manifests_keep_business_evidence_and_original_journal_keys(
    databases, tmp_path, kind
):
    book, rid, key, resource = manifest_run(databases, tmp_path, kind)
    result = run(book, rid, databases.ledger)
    assert result["run"]["state"] == "complete"
    receipt = databases.ledger.get("source.evidence", key)
    assert (
        receipt["event"]["event_key"] == key and receipt["event"]["event_type"] == kind
    )
    book.resume(rid)
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    assert databases.ledger.get("source.evidence", key) == receipt
    if kind == "source.revision":
        assert book.resource_checkpoint(resource)["ordinal"] == 0
    if kind == "source.imported":
        outcome = book.artifacts.json(result["items"][0]["receipt"]["evidence"])
        assert book.artifacts.verified(
            outcome["body"]["local_artifact"]
        ) == book.artifacts.verified(outcome["body"]["foreign_artifact"])


@pytest.mark.parametrize(
    "kind,damage",
    [
        ("source.revision", lambda body: body.pop("scope_complete")),
        ("source.revision", lambda body: body.update(position=2)),
        ("source.imported", lambda body: body.update(expected_checksum="b" * 64)),
        ("source.excluded", lambda body: body.update(reason="")),
        ("source.excluded", lambda body: body.update(reason="changed after approval")),
        ("producer.verified", lambda body: body.update(expected=1)),
        ("source.conflict", lambda body: body.update(quarantine=body["existing"])),
    ],
)
def test_missing_evidence_or_authorization_never_becomes_success(
    databases, tmp_path, kind, damage
):
    book, rid, _, _ = manifest_run(databases, tmp_path, kind, damage=damage)
    with pytest.raises((Blocked, KeyError)):
        run(book, rid, databases.ledger)
    state = book.status(rid)
    assert (
        state["run"]["state"] != "complete" and state["counts"].get("verified", 0) == 0
    )
    assert state["pending_deliveries"] == 0
