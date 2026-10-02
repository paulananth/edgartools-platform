"""Source manifest invariants and original-key delivery under configured work."""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pytest

from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical, digest
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import run
from edgar_warehouse.application.source_evidence import register_source_evidence
from tests.integration.test_change_journal_acquisition_postgres import definition
from tests.integration.test_configured_bookkeeping_postgres import databases
from tests.support.rules_approval import approve


def manifest_run(
    databases,
    tmp_path,
    kind,
    *,
    damage=None,
    proof_damage=None,
    records=None,
    record_format="json-array",
):
    registry = standard_registry()
    register_source_evidence(registry)
    book = Bookkeeping(databases.runtime, registry)
    name = "evidence-" + uuid4().hex
    key = uuid4().hex
    raw = book.artifacts.put(tmp_path.as_uri() + "/raw", {"record": "one"})
    foreign = book.artifacts.put(tmp_path.as_uri() + "/raw", {"record": "different"})
    scope_document = {
        "version": 1,
        "kind": "scope.complete",
        "source": name,
        "feed": "manifests",
        "scope": {"logical_key": "one"},
        "producer": "records"
        if kind in {"producer.verified", "scope.empty"}
        else "capture",
        "expected": 1 if kind == "source.revision" else 0,
        "members": [],
    }
    if kind == "source.revision":
        scope_document["members"] = [
            {
                "artifact": raw,
                "format": "bytes",
                "count": 1,
                "key_fields": [],
                "business_keys_sha256": digest([[raw["sha256"]]]),
            }
        ]
    record_ref = None
    if records is not None:
        record_ref = book.artifacts.put_bytes(
            (tmp_path / "records.json").as_uri(),
            canonical(records).encode()
            if record_format == "json-array"
            else b"".join(canonical(row).encode() + b"\n" for row in records),
        )
        scope_document.update(
            expected=len(records),
            members=[
                {
                    "artifact": record_ref,
                    "format": record_format,
                    "count": len(records),
                    "key_fields": ["id"],
                    "business_keys_sha256": digest(
                        sorted([[row["id"]] for row in records], key=canonical)
                    ),
                }
            ],
        )
    if proof_damage:
        proof_damage(scope_document)
    scope_proof = book.artifacts.put(tmp_path.as_uri() + "/proof", scope_document)
    evidence = [raw, foreign, scope_proof]
    if record_ref:
        evidence.append(record_ref)
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
            "expected": len(records) if records is not None else 0,
            "verified": len(records) if records is not None else 0,
            "producer": "records",
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
    if kind in {"producer.verified", "scope.empty"}:
        selected["required_producers"] = ["records"]
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
                    "counts": {
                        producer: {"expected": 1, "verified": 1}
                        for producer in selected["required_producers"]
                    },
                    "checks": {"offline": True},
                }
            },
        },
    )
    approve(databases.approver, "source", name, "1")
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


@pytest.mark.parametrize(
    "damage",
    [
        lambda proof: proof.update(kind="opaque_assertion"),
        lambda proof: proof.update(feed="another-feed"),
        lambda proof: proof.update(expected=1),
        lambda proof: proof.update(version=True),
    ],
)
def test_empty_scope_requires_typed_exact_inventory(databases, tmp_path, damage):
    book, rid, _, _ = manifest_run(
        databases, tmp_path, "scope.empty", proof_damage=damage
    )
    with pytest.raises(Blocked):
        run(book, rid, databases.ledger)
    assert book.status(rid)["counts"].get("verified", 0) == 0


@pytest.mark.parametrize(
    "damage",
    [
        lambda proof: proof["members"][0].update(count=2),
        lambda proof: proof["members"][0].update(business_keys_sha256="a" * 64),
        lambda proof: proof["members"][0].update(key_fields=["missing"]),
    ],
)
def test_producer_counts_and_business_keys_are_read_back(databases, tmp_path, damage):
    book, rid, _, _ = manifest_run(
        databases,
        tmp_path,
        "producer.verified",
        proof_damage=damage,
        records=[{"id": "one", "name": "Fixture"}],
    )
    with pytest.raises(Blocked):
        run(book, rid, databases.ledger)
    assert book.status(rid)["counts"].get("verified", 0) == 0


def test_duplicate_business_keys_do_not_prove_completeness(databases, tmp_path):
    book, rid, _, _ = manifest_run(
        databases, tmp_path, "producer.verified", records=[{"id": "one"}, {"id": "one"}]
    )
    with pytest.raises(Blocked, match="repeats a business key"):
        run(book, rid, databases.ledger)
    assert book.status(rid)["counts"].get("verified", 0) == 0


@pytest.mark.parametrize("record_format", ["json-array", "ndjson"])
def test_verified_record_inventory_delivers_only_references(
    databases, tmp_path, record_format
):
    book, rid, key, _ = manifest_run(
        databases,
        tmp_path,
        "producer.verified",
        records=[{"id": "one", "name": "Private Fixture Record"}],
        record_format=record_format,
    )
    result = run(book, rid, databases.ledger)
    assert result["run"]["state"] == "complete"
    receipt = databases.ledger.get("source.evidence", key)
    assert "Private Fixture Record" not in canonical(receipt)


@pytest.mark.parametrize("record_format", ["json-array", "ndjson"])
def test_empty_record_inventory_requires_actual_empty_member(
    databases, tmp_path, record_format
):
    book, rid, key, _ = manifest_run(
        databases, tmp_path, "scope.empty", records=[], record_format=record_format
    )
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    receipt = databases.ledger.get("source.evidence", key)
    assert receipt["event"]["event_type"] == "scope.empty"


def successor(book, rid, tmp_path, *, fake=False):
    item = book.status(rid)["items"][0]
    submission = book._run(rid)["submission"]
    original = book.artifacts.json(submission["inputs"])["steps"]["evidence"][0]
    prior = item["receipt"]["evidence"]
    if fake:
        forged = book.artifacts.json(prior)
        forged["event_key"] = "invented-prior"
        prior = book.artifacts.put(tmp_path.as_uri(), forged)
    spec = book.artifacts.json(original["input"])
    key = uuid4().hex
    spec["event_key"] = key
    spec["evidence"].append(prior)
    spec["body"].update(prior=prior, relationship="unchanged", position=1)
    unit = deepcopy(original)
    unit["keys"].update(id=key, journal_event_key=key)
    unit["input"] = book.artifacts.put(tmp_path.as_uri(), spec)
    unit["output"] = (tmp_path / "revision.outcome").as_uri()
    unit["cursor"]["resource_checkpoint"].update(revision=1, position=0)
    inputs = book.artifacts.put(
        tmp_path.as_uri(), {"version": 2, "steps": {"evidence": [unit]}}
    )
    return book.start(
        rules_ref=submission["rules"],
        inputs_ref=inputs,
        target="evidence",
        scope=submission["scope"],
    )


def test_revision_predecessor_is_a_committed_acknowledged_receipt(databases, tmp_path):
    book, rid, _, resource = manifest_run(databases, tmp_path, "source.revision")
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"
    following = successor(book, rid, tmp_path / "next")
    assert run(book, following, databases.ledger)["run"]["state"] == "complete"
    assert book.resource_checkpoint(resource)["ordinal"] == 1


@pytest.mark.parametrize("damage", ["invented", "missing-acknowledgement"])
def test_uncommitted_or_unacknowledged_predecessor_blocks(databases, tmp_path, damage):
    book, rid, _, resource = manifest_run(databases, tmp_path, "source.revision")
    if damage == "missing-acknowledgement":

        class Unavailable:
            def append(self, event):
                raise ConnectionError("Journal unavailable")

        with pytest.raises(ConnectionError):
            run(book, rid, Unavailable())
    else:
        run(book, rid, databases.ledger)
    following = successor(book, rid, tmp_path / "next", fake=damage == "invented")
    with pytest.raises(Blocked, match="committed, acknowledged"):
        run(book, following, databases.ledger)
    assert book.resource_checkpoint(resource)["ordinal"] == 0
    assert book.status(following)["counts"].get("verified", 0) == 0


def test_unsettled_same_scope_work_blocks_next_revision(databases, tmp_path):
    book, rid, _, resource = manifest_run(databases, tmp_path, "source.revision")
    submission = book._run(rid)["submission"]
    manifest = book.artifacts.json(submission["inputs"])
    original = manifest["steps"]["evidence"][0]
    pending = deepcopy(original)
    key = uuid4().hex
    spec = book.artifacts.json(original["input"])
    prior = {"uri": original["output"], "sha256": original["input"]["sha256"]}
    spec["event_key"] = key
    spec["body"].update(prior=prior, position=1, relationship="unchanged")
    spec["evidence"].append(prior)
    pending["input"] = book.artifacts.put(tmp_path.as_uri() + "/pending", spec)
    pending["output"] = (tmp_path / "pending.outcome").as_uri()
    pending["keys"].update(id=key, journal_event_key=key)
    pending["cursor"]["resource_checkpoint"].update(revision=1, position=0)
    manifest["steps"]["evidence"].append(pending)
    first = book.start(
        rules_ref=submission["rules"],
        inputs_ref=book.artifacts.put(tmp_path.as_uri() + "/work", manifest),
        target="evidence",
        scope=submission["scope"],
    )
    assert run(book, first, databases.ledger, limit=1)["run"]["state"] == "waiting"
    following = successor(book, first, tmp_path / "next")
    with pytest.raises(Blocked, match="committed, acknowledged"):
        run(book, following, databases.ledger)
    assert book.resource_checkpoint(resource)["ordinal"] == 0
