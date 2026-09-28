"""Bounded configured capture fixtures; no production feed qualification claim."""

from __future__ import annotations

import hashlib
import io
import zipfile
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean.capabilities import standard_registry
from edgar_warehouse.bookkeeping.clean.config import Blocked, canonical
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.runner import Authority, run
from edgar_warehouse.change_journal.capture import register_capture
from edgar_warehouse.infrastructure.sec_client import ConditionalSecResponse
from tests.integration.test_configured_bookkeeping_postgres import (
    complete,
    config,
    databases,
    expire,
    submit,
)


def definition(format="json", required=None):
    return {
        "family": "fixture",
        "datasets": [],
        "scope": ["logical_key"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {
            "format": format,
            "required": required or [],
            "allow_empty": False,
            "max_bytes": 1024 * 1024,
        },
        "required_producers": ["capture"],
        "url_prefixes": ["https://example.test/feed/"],
    }


def capture_run(
    databases,
    tmp_path,
    monkeypatch,
    *,
    payload=b'{"records":[1]}',
    feed="new-feed",
    declared=None,
    fetch=None,
    existing=None,
    prior=None,
    request_changes=None,
):
    monkeypatch.setenv("EDGAR_IDENTITY", "Fixture operator@example.test")
    calls = []

    def provider(url, identity, *, before_request, etag, last_modified, definition):
        before_request()
        calls.append({"url": url, "etag": etag, "last_modified": last_modified})
        return ConditionalSecResponse(
            False, payload, '"v1"', "Wed, 01 Jan 2025 00:00:00 GMT"
        )

    registry = standard_registry()
    register_capture(
        registry, databases.ledger, fetchers={"http.conditional": fetch or provider}
    )
    book = Bookkeeping(databases.runtime, registry)
    name = existing[0] if existing else "new-" + uuid4().hex
    selected = declared or definition()
    body = {
        "source": name,
        "acquisition": {"version": 1, "feeds": {feed: selected}},
        "bookkeeping": {
            "version": 1,
            "targets": {
                "capture": {
                    "steps": [
                        {
                            "name": "capture",
                            "operation": "provider.capture",
                            "requires": [],
                            "key": "{candidate_id}",
                            "leases": ["source:{logical_key}"],
                            "checks": ["input.hash", "output.receipt"],
                        }
                    ],
                    "checks": ["manifest.hash", "work.accounting", "journal.delivered"],
                }
            },
        },
    }
    cause = book.artifacts.put(
        tmp_path.as_uri() + "/authorization", {"scope": "one", "policy": "due"}
    )
    candidate = uuid4().hex
    request = {
        "candidate_id": candidate,
        "source_family": selected["family"],
        "logical_source_key": "one",
        "source_url": selected["url_prefixes"][0] + "one",
        "cause": "DUE_POLICY",
        "cause_reference": cause["uri"],
        "disposition": "FETCH_AUTHORIZED",
        "blocker": None,
        "next_action": "capture",
        "owner_role": "ACQUISITION_COORDINATOR",
        **(request_changes or {}),
    }
    scope = {key: "one" for key in selected["scope"]}
    decision = {
        "version": 1,
        "source": name,
        "feed": feed,
        "scope": scope,
        "request": request,
        "prior": prior,
        "evidence": [cause],
    }
    ref = book.artifacts.put(tmp_path.as_uri() + "/decisions", decision)
    unit = {
        "keys": {"candidate_id": candidate, "logical_key": "one", **scope},
        "input": ref,
        "output": (tmp_path / (candidate + ".outcome.json")).as_uri(),
        "cursor": {"candidate_id": candidate},
    }
    inputs = book.artifacts.put(
        tmp_path.as_uri() + "/manifests", {"version": 2, "steps": {"capture": [unit]}}
    )
    if existing:
        rules_ref = existing[1]
    else:
        saved = databases.rules.save("source", name, "1", body)
        proof = {
            "passed": True,
            "digest": saved["digest"],
            "batch_hash": inputs["sha256"],
            "acquisition": {
                feed: {
                    "manifest": inputs,
                    "counts": {"capture": {"expected": 1, "verified": 1}},
                    "checks": {"fixture": True},
                }
            },
        }
        databases.rules.prove("source", name, "1", proof)
        with pytest.raises(DBAPIError):
            databases.rules.activate("source", name, "1")
        databases.approver.approve("source", name, "1", saved["digest"])
        databases.rules.activate("source", name, "1")
        rules_ref = databases.rules.resolve(
            "source", name, root=tmp_path.as_uri() + "/rules"
        )
    rid = book.start(
        rules_ref=rules_ref,
        inputs_ref=inputs,
        target="capture",
        scope={"source": name, "feed": feed},
    )
    return book, rid, candidate, calls, (name, rules_ref), unit


@pytest.mark.parametrize(
    "feed,payload,required",
    [
        (
            "filings",
            b'{"accession":"0000320193-26-000001","form":"4"}',
            ["accession", "form"],
        ),
        (
            "submissions",
            b'{"cik":"0000320193","filings":{"recent":{"accessionNumber":[]}}}',
            ["cik", "filings.recent.accessionNumber"],
        ),
        (
            "company_facts",
            b'{"cik":320193,"facts":{"us-gaap":{"Assets":{}}}}',
            ["cik", "facts.us-gaap"],
        ),
        (
            "reference_catalogs",
            b'{"0":{"cik_str":320193,"ticker":"AAPL"}}',
            ["0.ticker"],
        ),
        ("adv_feeds", b'{"firms":[{"crd":1,"name":"Fixture"}]}', ["firms"]),
        ("unseen.calendar", b'{"days":["2026-01-01"]}', ["days"]),
    ],
)
def test_bounded_family_capture_uses_configuration_only(
    databases, tmp_path, monkeypatch, feed, payload, required
):
    book, rid, candidate, calls, _, unit = capture_run(
        databases,
        tmp_path,
        monkeypatch,
        feed=feed,
        payload=payload,
        declared=definition(required=required),
    )
    operations = set(book.registry.operations)
    state = run(book, rid, databases.ledger)
    assert state["run"]["state"] == "complete" and state["counts"] == {"verified": 1}
    assert len(calls) == 1 and operations == set(book.registry.operations)
    receipt = state["items"][0]["receipt"]
    outcome = book.artifacts.json(receipt["evidence"])
    assert book.artifacts.verified(outcome["artifact"]) == payload
    authorization = databases.ledger.get("acquisition", candidate)
    assert authorization["event"]["event_type"] == "fetch.authorized"
    assert (
        authorization["event"]["run_id"] == rid
        and authorization["event"]["feed"] == feed
    )
    assert authorization["event"]["event_key"] == candidate
    result_receipt = databases.ledger.get("acquisition.outcome", candidate)
    assert result_receipt["event"]["event_type"] == "fetch.outcome"
    assert receipt["evidence"] in result_receipt["event"]["evidence"]
    assert len(databases.ledger.list(run_id=rid)) == 2


@pytest.mark.parametrize(
    "feed,tag",
    [
        ("gleif.level1", "LEIData"),
        ("gleif.relationships", "RelationshipData"),
        ("gleif.reporting_exceptions", "ReportingExceptions"),
    ],
)
def test_gleif_zip_completeness_without_source_dispatch(
    databases, tmp_path, monkeypatch, feed, tag
):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr(
            "member.xml",
            f"<{tag}><Header><RecordCount>1</RecordCount></Header><Records><Record/></Records></{tag}>",
        )
    book, rid, _, calls, _, _ = capture_run(
        databases,
        tmp_path,
        monkeypatch,
        feed=feed,
        payload=raw.getvalue(),
        declared=definition("zip", ["member.xml"]),
    )
    assert (
        run(book, rid, databases.ledger)["run"]["state"] == "complete"
        and len(calls) == 1
    )


def test_conditional_unchanged_links_verified_bytes(databases, tmp_path, monkeypatch):
    book, rid, _, calls, binding, _ = capture_run(databases, tmp_path, monkeypatch)
    first = run(book, rid, databases.ledger)
    prior = first["items"][0]["receipt"]["evidence"]
    conditional = []

    def not_modified(url, identity, *, before_request, etag, last_modified, definition):
        before_request()
        conditional.append((etag, last_modified))
        return ConditionalSecResponse(True, b"", etag, last_modified)

    other, resumed, _, _, _, _ = capture_run(
        databases,
        tmp_path,
        monkeypatch,
        existing=binding,
        prior=prior,
        fetch=not_modified,
    )
    done = run(other, resumed, databases.ledger)
    outcome = other.artifacts.json(done["items"][0]["receipt"]["evidence"])
    assert (
        outcome["outcome"] == "unchanged"
        and outcome["artifact"] == book.artifacts.json(prior)["artifact"]
    )
    assert conditional == [('"v1"', "Wed, 01 Jan 2025 00:00:00 GMT")]


def test_journal_outage_blocks_request_and_resume_reconciles_lost_ack(
    databases, tmp_path, monkeypatch
):
    book, rid, candidate, calls, _, _ = capture_run(databases, tmp_path, monkeypatch)
    append = databases.ledger.append

    def lost_ack(value):
        append(value)
        raise ConnectionError("journal committed, acknowledgement lost")

    monkeypatch.setattr(databases.ledger, "append", lost_ack)
    with pytest.raises(ConnectionError):
        run(book, rid, databases.ledger)
    assert not calls and book.status(rid)["counts"] == {"waiting": 1}
    monkeypatch.setattr(databases.ledger, "append", append)
    assert databases.ledger.get("acquisition", candidate)
    book.resume(rid)
    assert (
        run(book, rid, databases.ledger)["run"]["state"] == "complete"
        and len(calls) == 1
    )


def test_lost_capture_completion_ack_does_not_refetch(databases, tmp_path, monkeypatch):
    book, rid, candidate, calls, _, _ = capture_run(databases, tmp_path, monkeypatch)
    claim = book.claim(rid, "capture", candidate)
    capability = book.registry.operations["provider.capture"]
    authority = Authority(claim)
    receipt = capability.execute(book, book.item(claim), authority)
    expire(databases, authority.current())
    recovered = book.claim(rid, "capture", candidate)
    assert (
        capability.reconcile(book, book.item(recovered), Authority(recovered))
        == receipt
    )
    book.record_verified_completion(recovered, receipt)
    assert (
        run(book, rid, databases.ledger)["run"]["state"] == "complete"
        and len(calls) == 1
    )


@pytest.mark.parametrize(
    "damage", ["outside_url", "bad_cause_role", "incomplete", "missing_prior"]
)
def test_invalid_acquisition_fails_closed(databases, tmp_path, monkeypatch, damage):
    changes = {}
    if damage == "outside_url":
        changes["source_url"] = "https://example.test.attacker/feed/one"
    if damage == "bad_cause_role":
        changes["cause"] = "OPERATOR_REQUEST"
    fetch = None
    if damage == "missing_prior":

        def fetch(url, identity, *, before_request, **kwargs):
            before_request()
            return ConditionalSecResponse(True, b"", None, None)

    book, rid, _, calls, _, _ = capture_run(
        databases,
        tmp_path,
        monkeypatch,
        request_changes=changes,
        payload=b"{}",
        declared=definition(required=["records"]),
        fetch=fetch,
    )
    with pytest.raises((Blocked, PermissionError)):
        run(book, rid, databases.ledger)
    assert book.status(rid)["run"]["state"] != "complete"
    if damage in {"outside_url", "bad_cause_role"}:
        assert not calls


def checkpoint_run(databases, tmp_path, resource, *, revision=0, position=-1, count=1):
    book, original, inputs, _ = submit(
        databases, tmp_path, count=count, body=config(resource=resource)
    )
    manifest = book.artifacts.json(inputs)
    for i, unit in enumerate(manifest["units"]):
        unit["cursor"]["resource_checkpoint"] = {
            "resource": resource,
            "revision": revision + i,
            "position": position + i,
        }
    ref = book.artifacts.put(tmp_path.as_uri() + "/checkpoints", manifest)
    rid = book.start(
        rules_ref=book._run(original)["submission"]["rules"],
        inputs_ref=ref,
        target="silver",
        scope={"checkpoint": resource},
    )
    return book, rid


def test_resource_checkpoint_spans_runs_and_cas_rejects_stale_completion(
    databases, tmp_path
):
    resource = "scope:" + uuid4().hex
    book, rid = checkpoint_run(databases, tmp_path / "first", resource)
    complete(book, rid)
    checkpoint = book.resource_checkpoint(resource)
    assert checkpoint["ordinal"] == 0 and checkpoint["revision"] == 1
    successor, other = checkpoint_run(
        databases, tmp_path / "second", resource, revision=1, position=0
    )
    complete(successor, other)
    assert successor.resource_checkpoint(resource)["ordinal"] == 1
    stale, old = checkpoint_run(
        databases, tmp_path / "stale", resource, revision=1, position=0
    )
    with pytest.raises(DBAPIError):
        complete(stale, old)
    assert stale.status(old)["counts"] == {"running": 1}
    assert stale.status(old)["pending_deliveries"] == 0
    assert stale.resource_checkpoint(resource)["revision"] == 2


def test_resource_checkpoint_hole_and_takeover_are_atomic(databases, tmp_path):
    resource = "scope:" + uuid4().hex
    book, rid = checkpoint_run(databases, tmp_path, resource, count=2)
    with pytest.raises(DBAPIError):
        complete(book, rid, key="1")
    assert book.resource_checkpoint(resource) is None
    with databases.admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' WHERE resource=:s"
            ),
            {"s": resource},
        )
    first, receipt = complete(book, rid, key="0")
    complete(book, rid, key="1")
    assert book.resource_checkpoint(resource)["ordinal"] == 1
    with pytest.raises(DBAPIError):
        book.heartbeat(first)
    assert run(book, rid, databases.ledger)["run"]["state"] == "complete"


@pytest.mark.parametrize(
    "source,feed,payload",
    [
        (
            "sec.submissions.company",
            "submissions",
            b'{"cik":"0000320193","filings":{}}',
        ),
        ("sec.company-facts", "company_facts", b'{"cik":320193,"facts":{}}'),
        (
            "sec.reference-catalogs",
            "reference_catalog",
            b'{"0":{"cik_str":320193,"ticker":"AAPL"}}',
        ),
        (
            "sec.filings",
            "filings",
            b"<ownershipDocument><documentType>4</documentType></ownershipDocument>",
        ),
        ("sec.adv", "adv_filing", b"<ADV><Name>Fixture Adviser</Name></ADV>"),
        ("sec.adv", "firm_roster", b"CRD,Name\n1,Fixture Adviser\n"),
    ],
)
def test_current_rules_capture_policy_on_bounded_provider_bytes(
    databases, tmp_path, monkeypatch, source, feed, payload
):
    from edgar_warehouse.rules.files import source as source_document

    declared = deepcopy(source_document(source)["acquisition"]["feeds"][feed])
    # Use the real selected transport capability with an injected bounded
    # response; capture still invokes the same authorization callback.
    selected_transport = declared["capabilities"]["fetch"]
    calls = []

    def transport(url, identity, *, before_request, **kwargs):
        before_request()
        calls.append(url)
        return ConditionalSecResponse(False, payload, None, None)

    book, rid, _, _, _, _ = capture_run(
        databases, tmp_path, monkeypatch, feed=feed, declared=declared
    )
    registry = standard_registry()
    register_capture(
        registry, databases.ledger, fetchers={selected_transport: transport}
    )
    book.registry = registry
    assert (
        run(book, rid, databases.ledger)["run"]["state"] == "complete"
        and len(calls) == 1
    )


@pytest.mark.parametrize(
    "counts",
    [
        {"capture": {"expected": 1.5, "verified": 1.5}},
        {
            "capture": {"expected": 1, "verified": 1},
            "undeclared": {"expected": 0, "verified": 0},
        },
    ],
)
def test_direct_rules_proof_cannot_bypass_exact_integer_producer_accounting(
    databases, tmp_path, counts
):
    from sqlalchemy.exc import DBAPIError
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.bookkeeping.clean.config import canonical

    name = "proof-" + uuid4().hex
    body = {
        **config(1),
        "source": name,
        "acquisition": {"version": 1, "feeds": {"new-feed": definition()}},
    }
    saved = databases.rules.save("source", name, "1", body)
    manifest = Artifacts().put(tmp_path.as_uri(), {"scope": "verified"})
    proof = {
        "digest": saved["digest"],
        "passed": True,
        "batch_hash": manifest["sha256"],
        "acquisition": {
            "new-feed": {
                "manifest": manifest,
                "counts": counts,
                "checks": {"offline": True},
            }
        },
    }
    with pytest.raises(DBAPIError), databases.rules.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rules.rule_version SET status='proven',proof=CAST(:p AS jsonb),batch_hash=:h WHERE name=:n"
            ),
            {"p": canonical(proof), "h": manifest["sha256"], "n": name},
        )


@pytest.mark.parametrize(
    "damage", ["null_proof", "null_revision", "null_checks", "null_hash"]
)
def test_restricted_sql_control_functions_reject_missing_fencing_or_completion_evidence(
    databases, tmp_path, damage
):
    from uuid import UUID, uuid5

    resource = "sql-boundary:" + uuid4().hex
    book, rid = checkpoint_run(databases, tmp_path, resource)
    claim = book.claim(rid, "s0", "0", sleep=lambda _: None)
    item = book.item(claim)
    receipt = book.registry.operations["artifact.copy"].execute(
        book, item, Authority(claim)
    )
    parameters = {
        "r": rid,
        "s": "s0",
        "k": "0",
        "a": claim.attempt,
        "p": canonical(claim.proof),
        "v": canonical(receipt),
        "c": canonical({"input.hash": True, "output.receipt": True}),
        "e": str(uuid5(UUID(rid), "s0:0")),
        "resource": resource,
        "revision": 0,
        "position": -1,
    }
    if damage == "null_proof":
        parameters["p"] = None
    elif damage == "null_revision":
        parameters["revision"] = None
    elif damage == "null_checks":
        parameters["c"] = None
    else:
        parameters["v"] = canonical({**receipt, "sha256": None})
    with pytest.raises(DBAPIError):
        book._call(
            "SELECT bookkeeping.finish_resource(CAST(:r AS uuid),:s,:k,CAST(:a AS uuid),CAST(:p AS jsonb),CAST(:v AS jsonb),CAST(:c AS jsonb),CAST(:e AS uuid),:resource,:revision,:position)",
            **parameters,
        )
    assert book.resource_checkpoint(resource) is None
    assert (
        book.status(rid)["counts"] == {"running": 1}
        and book.status(rid)["pending_deliveries"] == 0
    )
    book.record_verified_completion(claim, receipt)
    assert book.resource_checkpoint(resource)["revision"] == 1
