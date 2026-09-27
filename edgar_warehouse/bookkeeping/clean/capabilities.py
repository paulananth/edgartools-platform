"""Shared control checks and a bounded immutable-artifact capability.

Production stage operations must register an executor, destination reconciler
and verifier. The artifact copy capability proves the generic engine; it is
not a replacement for a parser, MDM commit or publication verifier.
"""
from __future__ import annotations

import hashlib

from .config import Blocked, Capability, Registry


def receipt_for(book, item, output: dict) -> dict:
    body = {"version": 1, "run_id": str(item["run_id"]), "step": item["step"],
            "key": item["unit_key"], "input": item["unit"]["input"], "output": output}
    evidence = book.artifacts.put(item["unit"]["output"] + ".receipts", body)
    return {**output, "evidence": evidence}


def _copy(book, item, authority):
    data = book.artifacts.verified(item["unit"]["input"])
    # Immutable file/S3 persistence uses its own conditional-write fence. No
    # mutable destination transaction is implied by this capability.
    output = book.artifacts.put_bytes(item["unit"]["output"], data)
    return receipt_for(book, item, output)


def _reconcile_copy(book, item, authority):
    try:
        data = book.artifacts.read(item["unit"]["output"])
    except Blocked:
        return None
    if hashlib.sha256(data).hexdigest() != item["unit"]["input"]["sha256"]:
        raise Blocked("Existing output conflicts with frozen copy input")
    return receipt_for(book, item, {"uri": item["unit"]["output"], "sha256": hashlib.sha256(data).hexdigest()})


def _verify_copy(book, item, receipt):
    if not receipt or receipt.get("uri") != item["unit"]["output"] or receipt.get("sha256") != item["unit"]["input"]["sha256"]:
        return False
    book.artifacts.verified({"uri": receipt["uri"], "sha256": receipt["sha256"]})
    evidence = book.artifacts.json(receipt["evidence"])
    return evidence == {"version": 1, "run_id": str(item["run_id"]), "step": item["step"],
                        "key": item["unit_key"], "input": item["unit"]["input"],
                        "output": {"uri": receipt["uri"], "sha256": receipt["sha256"]}}


def standard_registry() -> Registry:
    result = Registry()
    result.operation("artifact.copy", Capability("1", _copy, _reconcile_copy, _verify_copy))

    def input_hash(book, context):
        book.artifacts.verified(context["item"]["unit"]["input"])
        return True

    def output_receipt(book, context):
        book.artifacts.verified(context["receipt"]["evidence"])
        return True

    def manifest_hash(book, context):
        book.artifacts.verified(context["run"]["submission"]["inputs"])
        return True

    def accounting(book, context):
        status = context["status"]
        return status["counts"].get("verified", 0) == context["run"]["expected_count"]

    def deliveries(book, context):
        return context["status"]["pending_deliveries"] == 0

    result.check("input.hash", input_hash)
    result.check("output.receipt", output_receipt)
    result.check("manifest.hash", manifest_hash)
    result.check("work.accounting", accounting)
    result.check("journal.delivered", deliveries)
    return result
