"""Versioned source evidence contracts; adapters never write master state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .store import Conflict, digest

KINDS = {
    "company",
    "person",
    "security",
    "fund_structure",
    "branch",
    "government",
    "international_organization",
    "venue",
}
PROFILE_KINDS = {
    "adviser": {"company", "person"},
    "audit_firm": {"company"},
    "fund": {"company", "fund_structure"},
}


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Effective time must include a timezone")
    return result.astimezone(UTC)


def subject_key(source_code: str, record_key: str) -> str:
    return digest([source_code, record_key])


def assertion(
    *,
    source_code: str,
    record_key: str,
    publication_key: str,
    revision: int,
    effective_at: str | None,
    kind: str,
    fields: dict[str, Any],
    schema_version: str = "1",
    mapping_version: int = 1,
    identifiers: dict[str, str] | None = None,
    profiles: list[dict] | None = None,
    relationships: list[dict] | None = None,
    provenance: dict | None = None,
) -> dict:
    if (
        kind not in KINDS
        or not all((source_code, record_key, publication_key))
        or type(revision) is not int
        or revision < 0
    ):
        raise ValueError(
            "Assertion requires a supported kind, source keys and nonnegative native revision"
        )
    # The platform's own reading number, not the source's schema_version. It is
    # hashed with the rest of the body so that a second reading of one
    # publication is a distinct assertion rather than a silent duplicate
    # (company mastering ticket 01, amendment 7).
    if type(mapping_version) is not int or mapping_version < 1:
        raise ValueError("Mapping version must be a positive integer")
    normalized = {}
    for name, item in fields.items():
        if not name:
            raise ValueError("Empty field name")
        if not isinstance(item, dict) or "op" not in item:
            item = {"op": "unknown"} if item is None else {"op": "value", "value": item}
        if item["op"] not in {"value", "unknown", "clear", "retract"}:
            raise ValueError("Unknown assertion operation")
        if item["op"] == "value" and item.get("value") is None:
            raise ValueError("Use unknown for null evidence")
        normalized[name] = item
    body = {
        "source_code": source_code,
        "record_key": record_key,
        "publication_key": publication_key,
        "revision": revision,
        "schema_version": schema_version,
        "effective_at": instant(effective_at).isoformat()
        if effective_at is not None
        else None,
        "kind": kind,
        "subject": subject_key(source_code, record_key),
        "fields": normalized,
        "identifiers": identifiers or {},
        "profiles": profiles or [],
        "relationships": relationships or [],
        "provenance": provenance or {},
    }
    # The first reading has one canonical form: absent. Stating it explicitly
    # would move every assertion id already written, orphaning the decisions
    # that cite them, and a body that says 1 and a body that says nothing
    # describe the same reading. A re-read states its version and so hashes
    # differently, which is what lets it sit beside its predecessor.
    if mapping_version > 1:
        body["mapping_version"] = mapping_version
    body["assertion_id"] = digest(body)
    return body


def validate_assertion(body: dict) -> None:
    expected = assertion(
        **{
            k: body[k]
            for k in (
                "source_code",
                "record_key",
                "publication_key",
                "revision",
                "effective_at",
                "kind",
                "fields",
                "schema_version",
                "identifiers",
                "profiles",
                "relationships",
                "provenance",
            )
        },
        # Incoming only: `merge.py` validates what a batch carries, never a
        # stored row, so an assertion written before mapping versions existed
        # is not re-hashed. Absent means the first reading.
        mapping_version=body.get("mapping_version", 1),
    )
    if expected != body:
        raise Conflict("Normalized assertion hash or shape mismatch")


def deferred_record(
    *,
    source_code: str,
    publication_key: str,
    record_locator: str,
    schema_version: str,
    reason: str,
    raw_record: Any,
    provenance: dict,
    probable_kind: str | None = None,
) -> dict:
    """A record held in the Stage, with the reason it waits.

    `probable_kind` is the kind the rule step or contract that held it back
    names for it: it sorts the Stage and never creates an identity (CONTEXT.md,
    Probable Kind). It is written only when known, so a record given none keeps
    the id it had. A record given one has a new body, so re-reading a
    publication already committed collides: the limit the operator accepted
    for any record that waits differently when re-read (2026-09-23,
    `test_a_deferred_reread_that_changes_its_body_still_collides`).
    """
    if not all((source_code, publication_key, record_locator, schema_version, reason)):
        raise ValueError(
            "Deferred evidence requires dataset/publication/record location and reason"
        )
    if probable_kind is not None and probable_kind not in KINDS:
        raise ValueError(f"Probable Kind {probable_kind} is not a kind")
    body = {
        "source_code": source_code,
        "publication_key": publication_key,
        "record_locator": record_locator,
        "schema_version": schema_version,
        "reason": reason,
        "raw_record": raw_record,
        "provenance": provenance,
    }
    if probable_kind is not None:
        body["probable_kind"] = probable_kind
    return {**body, "deferred_id": digest(body)}


def validate_deferred(body: dict) -> None:
    try:
        expected = deferred_record(
            **{k: v for k, v in body.items() if k != "deferred_id"}
        )
    except (TypeError, ValueError) as exc:
        raise Conflict("Invalid deferred evidence") from exc
    if expected != body:
        raise Conflict("Deferred evidence hash mismatch")


def decision(operation: str, *, actor: str, reason: str, at: str, **values) -> dict:
    if not actor or not reason:
        raise ValueError("Steward decisions require actor and evidence-bound reason")
    body = {
        "operation": operation,
        "actor": actor,
        "reason": reason,
        "at": instant(at).isoformat(),
        **values,
    }
    body["decision_id"] = digest(body)
    return body
