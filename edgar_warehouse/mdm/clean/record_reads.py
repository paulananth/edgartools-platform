"""Transport Rust's affected-record requests through the existing storage adapter."""

from __future__ import annotations

import json

from edgar_warehouse.rules.source_engine import plan_affected_records

from .store import Conflict


def read_affected_records(adapter, assertions: list[dict], decisions: list[dict], *, connection=None) -> dict:
    """Read indexed inputs; the returned generation must guard their later save.

    Rust owns the scope and traversal. Python only transports its grouped read
    requests and validates stored reference envelopes. This does not qualify
    the remaining relationship scope or the normal selected-engine caller.
    """
    if adapter.protocol < 3:
        raise Conflict("Affected-record reads require indexed lookup storage")
    generation = adapter.generation(connection=connection)
    readings, retained_decisions, identities = {}, {}, {}
    completed_lookups, completed_identities = set(), set()
    while True:
        try:
            plan = plan_affected_records({
                "assertions": assertions, "decisions": decisions,
                "retained_readings": list(readings.values()),
                "retained_decisions": list(retained_decisions.values()),
                "completed_lookups": sorted(completed_lookups),
                "completed_identities": sorted(completed_identities),
            })
        except ValueError as error:
            raise Conflict(str(error)) from None
        if plan["ready"]:
            return {
                "generation": generation, "readings": readings,
                "decisions": retained_decisions, "identities": list(identities.values()),
                "subjects": set(plan["subjects"]),
            }
        before = len(completed_lookups) + len(completed_identities)
        groups = adapter.read_lookup_groups(plan["lookups"], connection=connection)
        requested = set()
        for entry in groups.values():
            try:
                reference = json.loads(entry["body"])
            except (ValueError, TypeError):
                raise Conflict("Invalid retained-input reference") from None
            if (not isinstance(reference, dict) or set(reference) != {"type", "id", "immutable"}
                    or reference["immutable"] is not True
                    or not isinstance(reference["type"], str)
                    or reference["type"] not in {"source-reading", "decision"}
                    or not isinstance(reference["id"], str) or not reference["id"]):
                raise Conflict("Invalid retained-input reference")
            requested.add((reference["type"], reference["id"]))
        requested = {key for key in requested if key[1] not in (
            readings if key[0] == "source-reading" else retained_decisions
        )}
        found = adapter.read(sorted(requested), immutable=True, connection=connection)
        if set(found) != requested:
            raise Conflict("Retained-input reference has no saved input")
        for (record_type, record_id), entry in found.items():
            try:
                body = json.loads(entry["body"])
            except (ValueError, TypeError):
                raise Conflict("Invalid retained-input body") from None
            name = "assertion_id" if record_type == "source-reading" else "decision_id"
            if not isinstance(body, dict) or body.get(name) != record_id:
                raise Conflict("Retained-input identity differs from its stored key")
            (readings if record_type == "source-reading" else retained_decisions)[record_id] = body
        completed_lookups.update(plan["lookups"])
        identity_keys = [("identity", record_id) for record_id in plan["identities"]]
        for (_, record_id), entry in adapter.read(identity_keys, immutable=True, connection=connection).items():
            try:
                body = json.loads(entry["body"])
            except (ValueError, TypeError):
                raise Conflict("Invalid saved identity") from None
            if not isinstance(body, dict) or body.get("entity_id") != record_id:
                raise Conflict("Saved identity differs from its stored key")
            identities[record_id] = body
        completed_identities.update(plan["identities"])
        if len(completed_lookups) + len(completed_identities) == before:
            raise Conflict("Affected-record reads made no progress")
