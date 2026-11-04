"""Versioned public master reads over the existing opaque storage contract."""

import json
from datetime import UTC, datetime, timedelta

from .store import Conflict, digest
from .record_reads import RecordReader


def _body(raw):
    try:
        body = json.loads(raw)
    except (ValueError, TypeError):
        raise Conflict("Invalid retained master read body") from None
    if not isinstance(body, dict):
        raise Conflict("Retained master read body must be an object")
    return body


def _projection(row):
    origin = row["origin"]
    effects = _body(origin["assessment"]).get("effects")
    if (not isinstance(effects, dict) or effects.get("batch_id") != origin["batch"]
            or not isinstance(effects.get("policy_digest"), str)
            or not isinstance(effects.get("as_of"), str)):
        raise Conflict("Retained master has invalid projection provenance")
    return {"generation": origin["generation"], "origin_run_id": origin["run"],
            "policy_digest": effects["policy_digest"], "as_of": effects["as_of"],
            "recorded_at": (datetime(1970, 1, 1, tzinfo=UTC)
                            + timedelta(microseconds=origin["recorded_at"])).isoformat()}


def snapshot_page(adapter, connection, object_type, generation, after, limit):
    """Pin bodies to one generation and page through indexed opaque keys.

    `next_after` names the last object; storage hashes establish a stable order
    on both engines without imposing a length or collation on original IDs.
    Future objects are skipped through bounded key pages and historical seeks.
    """
    latest = adapter.generation(connection=connection)
    if generation is None:
        generation = latest
    elif type(generation) is not int or not 1 <= generation <= latest:
        raise KeyError("Unknown generation")
    items, cursor = [], after
    while len(items) <= limit and generation:
        keys = adapter.record_keys(object_type, after=cursor, limit=limit + 1,
                                   connection=connection)
        if not keys:
            break
        rows = adapter.read_origins([(object_type, key) for key in keys],
                                    generation=generation, connection=connection)
        for key in keys:
            row = rows.get((object_type, key))
            if row is not None:
                projection = _projection(row)
                items.append({"object_id": key, "body": _body(row["body"]),
                              "projection_generation": projection["generation"],
                              "projection_as_of": projection["as_of"],
                              "policy_digest": projection["policy_digest"],
                              "origin_run_id": projection["origin_run_id"]})
        cursor = keys[-1]
        if len(keys) <= limit:
            break
    more, items = len(items) > limit, items[:limit]
    return {"contract_version": 2, "generation": generation, "object_type": object_type,
            "items": items, "next_after": items[-1]["object_id"] if more else None,
            "business_hash": digest([{k: row[k] for k in ("object_id", "body")} for row in items])}


def entity(adapter, connection, requested_id, generation=None):
    latest = adapter.generation(connection=connection)
    if generation is None:
        generation = latest
    if type(generation) is not int or generation < 1 or generation > latest:
        raise KeyError(requested_id if latest == 0 else "Unknown generation")
    key, seen = requested_id, set()
    while True:
        if key in seen:
            raise Conflict("Alias cycle")
        seen.add(key)
        row = adapter.read_origins([("entity", key)], generation=generation,
                                   connection=connection).get(("entity", key))
        if row is None:
            raise KeyError(key)
        body = _body(row["body"])
        if (body.get("entity_id") != key or not isinstance(body.get("kind"), str)
                or not isinstance(body.get("canonical_id"), str) or not body["canonical_id"]):
            raise Conflict("Retained master identity differs from its requested key")
        if body["canonical_id"] == key:
            break
        key = body["canonical_id"]
    groups = [body.get("fields", {}), *(p.get("fields", {}) for p in body.get("profiles", []))]
    wanted = set()
    for fields in groups:
        for field in fields.values():
            identifier = field.get("winner", {}).get("assertion_id")
            if not isinstance(identifier, str) or not identifier:
                raise Conflict("Selected field has missing provenance")
            wanted.add(identifier)
    records = adapter.read_origins([(kind, identifier) for identifier in sorted(wanted)
                                   for kind in ("source-reading", "decision")],
                                  immutable=True, generation=generation, connection=connection)

    def provenance(fields):
        result = {}
        for name, field in fields.items():
            identifier = field["winner"]["assertion_id"]
            matches = [(kind, records[kind, identifier]) for kind in ("source-reading", "decision")
                       if (kind, identifier) in records]
            if len(matches) != 1:
                raise Conflict("Selected field has missing or ambiguous provenance")
            kind, source = matches[0]
            evidence = RecordReader.input_body(kind, identifier, source)
            result[name] = {"evidence": evidence, "origin_run_id": source["origin"]["run"],
                            "policy_digest": field["policy_digest"]}
        return result

    return {"contract_version": 2, "generation": generation, "requested_id": requested_id,
            "canonical_id": key, "identity": body, "projection": _projection(row),
            "business_hash": digest(body), "field_provenance": provenance(body.get("fields", {})),
            "profile_field_provenance": {p["profile_id"]: provenance(p.get("fields", {}))
                                         for p in body.get("profiles", [])}}
