"""Source-owned revision, conflict, import and producer manifests; no tables."""

from __future__ import annotations

import hashlib

from edgar_warehouse.bookkeeping.clean.config import (
    Blocked,
    Capability,
    canonical,
    digest,
    reference,
)

from .authority import frozen_authority


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
    if not isinstance(spec["evidence"], list) or not spec["evidence"]:
        raise Blocked("Source manifest requires verified evidence references")
    for ref in spec["evidence"]:
        book.artifacts.verified(ref)
    body = spec["body"]

    def evidence(ref):
        reference(ref)
        if ref not in spec["evidence"]:
            raise Blocked("Source manifest uses undeclared evidence")
        return book.artifacts.verified(ref)

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
            evidence(body["scope_complete"])
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
        evidence(body["scope_complete"])
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
        "source.evidence", Capability("source-manifest-v1", execute, reconcile, verify)
    )
