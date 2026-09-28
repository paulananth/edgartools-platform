"""Source-owned revision, conflict, import and producer manifests; no tables."""

from __future__ import annotations

import hashlib

from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.artifacts import json_value
from edgar_warehouse.bookkeeping.clean.config import (
    Blocked,
    Capability,
    canonical,
    digest,
    reference,
)

from .authority import frozen_authority


def scope_proof(book, spec, authority, evidence):
    """Verify the exact source-owned inventory, including explicit zero scopes.

    Byte producers count captured artifacts; row producers count actual JSON
    records and their business keys. No listing or write acknowledgement is
    interpreted as completion. Destination effects still need their own owner
    verifier before producing this immutable inventory.
    """
    ref = spec["body"]["scope_complete"]
    evidence(ref)
    proof = book.artifacts.json(ref)
    if (
        set(proof)
        != {
            "version",
            "kind",
            "source",
            "feed",
            "scope",
            "producer",
            "expected",
            "members",
        }
        or type(proof["version"]) is not int
        or proof["version"] != 1
        or proof["kind"] != "scope.complete"
        or (proof["source"], proof["feed"], proof["scope"])
        != (spec["source"], spec["feed"], spec["scope"])
        or proof["producer"] not in authority["configuration"]["required_producers"]
        or type(proof["expected"]) is not int
        or proof["expected"] < 0
        or not isinstance(proof["members"], list)
        or len(proof["members"]) > 128
    ):
        raise Blocked(
            "Scope completeness requires an exact typed source/feed inventory"
        )
    total, keys, artifacts = 0, set(), set()
    for member in proof["members"]:
        if (
            not isinstance(member, dict)
            or set(member)
            != {"artifact", "format", "count", "key_fields", "business_keys_sha256"}
            or member["format"] not in {"bytes", "json-array", "ndjson"}
            or type(member["count"]) is not int
            or member["count"] < 0
            or not isinstance(member["key_fields"], list)
            or any(
                not isinstance(field, str) or not field
                for field in member["key_fields"]
            )
            or len(set(member["key_fields"])) != len(member["key_fields"])
        ):
            raise Blocked("Invalid scope member inventory")
        reference(member["artifact"])
        identity = (member["artifact"]["uri"], member["artifact"]["sha256"])
        if identity in artifacts:
            raise Blocked("Scope inventory repeats an artifact")
        artifacts.add(identity)
        bound = (
            authority["configuration"]["completeness"]["max_bytes"]
            if member["format"] == "bytes"
            else 16 * 1024**2
        )
        data = book.artifacts.verified(member["artifact"], max_bytes=bound)
        if member["artifact"] not in spec["evidence"]:
            raise Blocked("Scope inventory uses undeclared member evidence")
        if member["format"] == "bytes":
            from .capture import complete

            if (
                proof["producer"] != "capture"
                or member["key_fields"]
                or not complete(data, authority["configuration"]["completeness"])
            ):
                raise Blocked("Captured scope member fails approved completeness")
            member_keys = [[member["artifact"]["sha256"]]]
        else:
            if not member["key_fields"]:
                raise Blocked("Row inventory requires explicit business key fields")
            try:
                rows = (
                    json_value(data)
                    if member["format"] == "json-array"
                    else [
                        json_value(line) for line in data.splitlines() if line.strip()
                    ]
                )
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict) for row in rows
                ):
                    raise ValueError("Not a record inventory")
                member_keys = [
                    [row[field] for field in member["key_fields"]] for row in rows
                ]
                if any(
                    value is None or isinstance(value, (dict, list))
                    for key in member_keys
                    for value in key
                ):
                    raise ValueError("Invalid business identity")
            except (ValueError, UnicodeError, KeyError, TypeError) as exc:
                raise Blocked(
                    "Scope records lack verified business identities"
                ) from exc
        if (
            len(member_keys) != member["count"]
            or digest(sorted(member_keys, key=canonical))
            != member["business_keys_sha256"]
        ):
            raise Blocked("Scope member count or ordered business key digest differs")
        for key in member_keys:
            encoded = canonical(key)
            if encoded in keys:
                raise Blocked("Scope inventory repeats a business key")
            keys.add(encoded)
        total += len(member_keys)
    if total != proof["expected"]:
        raise Blocked("Scope expected count differs from verified member inventory")
    return proof


def verify_manifest(book, item) -> dict:
    run, _, _, _ = book._frozen(str(item["run_id"]))
    spec = book.artifacts.json(item["unit"]["input"])
    export = book.artifacts.json(run["submission"]["rules"])
    authority = frozen_authority(export, run["submission"]["scope"].get("feed"))
    if (
        set(spec)
        != {
            "version",
            "kind",
            "event_key",
            "source",
            "feed",
            "scope",
            "evidence",
            "body",
        }
        or type(spec["version"]) is not int
        or spec["version"] != 1
        or spec["source"] != authority["name"]
        or spec["feed"] != authority["feed"]
        or not isinstance(spec["scope"], dict)
        or set(spec["scope"]) != set(authority["configuration"]["scope"])
        or any(item["unit"]["keys"].get(k) != v for k, v in spec["scope"].items())
        or not isinstance(spec["body"], dict)
        or not spec["event_key"]
    ):
        raise Blocked("Source manifest differs from frozen authority/scope")
    keys = item["unit"]["keys"]
    if (
        keys.get("journal_event_key") != spec["event_key"]
        or keys.get("journal_event_type") != spec["kind"]
        or keys.get("journal_producer") != "source.evidence"
    ):
        raise Blocked("Source manifest must retain its original producer identity")
    if (
        not isinstance(spec["evidence"], list)
        or not spec["evidence"]
        or len(spec["evidence"]) > 128
    ):
        raise Blocked("Source manifest requires verified evidence references")
    evidence_limit = max(
        32 * 1024**2, authority["configuration"]["completeness"]["max_bytes"]
    )
    for ref in spec["evidence"]:
        book.artifacts.verified(ref, max_bytes=evidence_limit)
    body = spec["body"]

    def evidence(ref):
        reference(ref)
        if ref not in spec["evidence"]:
            raise Blocked("Source manifest uses undeclared evidence")
        return book.artifacts.verified(ref, max_bytes=evidence_limit)

    def operator():
        if (
            body.get("owner_role") != "ACQUISITION_OPERATOR"
            or not isinstance(body.get("reason"), str)
            or not body["reason"].strip()
        ):
            raise Blocked(
                "Operator source action requires its role and explicit reason"
            )
        evidence(body["authorization"])
        if body["authorization"] not in authority["configuration"].get(
            "authorizations", []
        ):
            raise Blocked(
                "Operator action requires authorization pinned in the approved Rules body"
            )
        authorization = book.artifacts.json(body["authorization"])
        decision = {
            "source": spec["source"],
            "feed": spec["feed"],
            "scope": spec["scope"],
            "kind": spec["kind"],
            "event_key": spec["event_key"],
            "body_digest": digest(
                {k: v for k, v in body.items() if k != "authorization"}
            ),
        }
        if authorization != decision:
            raise Blocked("Operator authorization names a different immutable action")

    kind = spec["kind"]
    if kind == "source.revision":
        cursor = item["unit"]["cursor"]
        checkpoint = (
            cursor.get("resource_checkpoint") if isinstance(cursor, dict) else None
        )
        if (
            not checkpoint
            or type(body.get("position")) is not int
            or body["position"] != checkpoint["position"] + 1
        ):
            raise Blocked(
                "Revision requires frozen ordered resource checkpoint advancement"
            )
        for name in ("raw", "canonical", "domain"):
            evidence(body[name])
        if (
            not isinstance(body.get("processing_versions"), dict)
            or set(body["processing_versions"]) != {"parser", "schema", "configuration"}
            or any(
                not isinstance(v, str) or not v
                for v in body["processing_versions"].values()
            )
            or body.get("completeness") not in {"patch", "full_snapshot"}
        ):
            raise Blocked("Revision requires frozen versions and explicit completeness")
        if body["completeness"] == "full_snapshot":
            proof = scope_proof(book, spec, authority, evidence)
            if not any(
                member["artifact"] == body["raw"] and member["format"] == "bytes"
                for member in proof["members"]
            ):
                raise Blocked(
                    "Full revision scope inventory must include its captured raw artifact"
                )
        if body.get("prior") is None:
            if body.get("relationship") != "initial" or checkpoint["position"] != -1:
                raise Blocked("First revision requires explicit baseline")
        else:
            prior = book.artifacts.json(body["prior"])
            evidence(body["prior"])
            if prior.get("kind") != "source.revision" or (
                prior.get("source"),
                prior.get("feed"),
                prior.get("scope"),
            ) != (spec["source"], spec["feed"], spec["scope"]):
                raise Blocked("Prior revision belongs to another source scope")
            if prior["body"]["position"] != checkpoint["position"]:
                raise Blocked(
                    "Revision predecessor differs from frozen checkpoint position"
                )
            with book.engine.connect() as conn:
                committed = (
                    conn.execute(
                        text("""SELECT w.unit FROM bookkeeping.work_item w
                      JOIN bookkeeping.pipeline_run r USING(run_id)
                      JOIN bookkeeping.journal_outbox o
                        ON (o.run_id,o.step,o.unit_key)=(w.run_id,w.step,w.unit_key)
                      WHERE w.state='verified' AND o.delivered_at IS NOT NULL
                        AND w.receipt->>'uri'=:uri AND w.receipt->>'sha256'=:sha
                        AND w.resources ? :resource
                        AND w.unit->'keys' @> CAST(:scope AS jsonb)
                        AND w.unit->'keys'->>'journal_event_type'='source.revision'
                        AND w.unit->'keys'->>'journal_event_key'=:key
                        AND r.submission->>'journal'='change-journal-v1'
                        AND r.submission->'scope'->>'source'=:source
                        AND r.submission->'scope'->>'feed'=:feed
                        AND NOT EXISTS(SELECT 1 FROM bookkeeping.work_item p
                          WHERE p.run_id=w.run_id
                            AND p.unit->'keys' @> CAST(:scope AS jsonb)
                            AND p.state<>'verified')
                      LIMIT 2"""),
                        {
                            "uri": body["prior"]["uri"],
                            "sha": body["prior"]["sha256"],
                            "resource": checkpoint["resource"],
                            "scope": canonical(spec["scope"]),
                            "key": prior.get("event_key"),
                            "source": spec["source"],
                            "feed": spec["feed"],
                        },
                    )
                    .scalars()
                    .all()
                )
            if len(committed) != 1 or committed[0]["cursor"].get(
                "resource_checkpoint"
            ) != {
                **checkpoint,
                "revision": checkpoint["revision"] - 1,
                "position": checkpoint["position"] - 1,
            }:
                raise Blocked(
                    "Revision predecessor lacks committed, acknowledged scope completion"
                )
            relationship = (
                "unchanged"
                if body["domain"]["sha256"] == prior["body"]["domain"]["sha256"]
                else "changed"
            )
            if body.get("relationship") != relationship:
                raise Blocked("Revision relationship differs from verified evidence")
    elif kind == "source.conflict":
        evidence(body["existing"])
        evidence(body["quarantine"])
        if body["existing"]["sha256"] == body["quarantine"]["sha256"]:
            raise Blocked("Conflict requires two different immutable contents")
    elif kind == "source.conflict_resolved":
        operator()
        conflict = book.artifacts.json(body["conflict"])
        evidence(body["conflict"])
        if conflict.get("kind") != "source.conflict" or (
            conflict.get("source"),
            conflict.get("feed"),
            conflict.get("scope"),
        ) != (spec["source"], spec["feed"], spec["scope"]):
            raise Blocked("Resolution requires the exact scoped conflict")
        if body.get("selected") not in (
            conflict["body"]["existing"],
            conflict["body"]["quarantine"],
        ):
            raise Blocked("Conflict resolution selects only retained evidence")
        evidence(body["selected"])
    elif kind in {"source.excluded", "source.imported"}:
        operator()
        if kind == "source.imported":
            evidence(body["foreign_artifact"])
            if (
                not isinstance(body.get("source_environment"), str)
                or not body["source_environment"]
                or body.get("expected_checksum") != body["foreign_artifact"]["sha256"]
            ):
                raise Blocked(
                    "Import requires exact foreign location, environment and checksum"
                )
    elif kind in {"producer.verified", "scope.empty"}:
        if (
            type(body.get("expected")) is not int
            or body["expected"] < 0
            or type(body.get("verified")) is not int
            or body["expected"] != body["verified"]
            or body.get("producer")
            not in authority["configuration"]["required_producers"]
        ):
            raise Blocked("Producer requires exact complete accounting")
        proof = scope_proof(book, spec, authority, evidence)
        if (
            proof["producer"] != body["producer"]
            or proof["expected"] != body["expected"]
        ):
            raise Blocked(
                "Producer accounting differs from its verified scope inventory"
            )
        if kind == "scope.empty" and body["expected"] != 0:
            raise Blocked("Empty scope requires verified zero count")
    else:
        raise Blocked("Unsupported source manifest transition")
    return spec


def register_source_evidence(registry):
    def execute(book, item, authority):
        spec = verify_manifest(book, item)
        updated = book.heartbeat(authority.current())
        with authority.lock:
            authority.claim = updated
        body = spec
        if spec["kind"] == "source.imported":
            ref = spec["body"]["foreign_artifact"]
            local = book.artifacts.put_bytes(
                item["unit"]["output"] + ".import/" + ref["sha256"],
                book.artifacts.verified(ref),
            )
            body = {**spec, "body": {**spec["body"], "local_artifact": local}}
        output = book.artifacts.put_bytes(
            item["unit"]["output"], canonical(body).encode()
        )
        return {**output, "evidence": output}

    def verify(book, item, receipt):
        if not receipt or receipt.get("uri") != item["unit"]["output"]:
            return False
        output = {"uri": receipt["uri"], "sha256": receipt["sha256"]}
        if receipt.get("evidence") != output:
            return False
        book.artifacts.verified(output)
        spec = verify_manifest(book, item)
        body = book.artifacts.json(receipt["evidence"])
        if spec["kind"] == "source.imported":
            local = body["body"]["local_artifact"]
            if (
                local["uri"]
                != item["unit"]["output"]
                + ".import/"
                + spec["body"]["expected_checksum"]
            ):
                return False
            book.artifacts.verified(local)
            if local["sha256"] != spec["body"]["expected_checksum"]:
                return False
            body = {
                **body,
                "body": {
                    k: v for k, v in body["body"].items() if k != "local_artifact"
                },
            }
        return body == spec

    def reconcile(book, item, authority):
        try:
            data = book.artifacts.read(item["unit"]["output"])
        except Blocked:
            return None
        ref = {
            "uri": item["unit"]["output"],
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        receipt = {**ref, "evidence": ref}
        if not verify(book, item, receipt):
            raise Blocked("Source manifest completion failed reconciliation")
        return receipt

    registry.operation(
        "source.evidence", Capability("source-manifest-v2", execute, reconcile, verify)
    )
