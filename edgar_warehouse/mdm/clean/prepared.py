"""Coordinate one shared Merge Stage calculation and destination admission."""

from dataclasses import dataclass
import json

from . import assessment, catalog, matching
from .evidence import instant
from .identifier_types import TYPES
from .prepared_registry import PREFIX, mapping_pin, schema_pin
from .record_reads import RecordReader
from .store import Conflict, canonical, digest, storage_adapter


@dataclass(frozen=True)
class Admission:
    batch: object
    proposal: dict | None = None
    proposal_key: str | None = None


def _refusals(operation):
    """Translate data-free adapter refusals into the normal retry contract."""
    try:
        return operation()
    except storage_adapter().AdapterError as error:
        if str(error) in {
            "stale_generation", "stale_scope_lease", "stale_object_version",
            "stale_index_version", "assessed_effects_changed", "proposal_not_ready",
        }:
            raise assessment.StaleAssessment("Prepared state changed; re-assess") from None
        raise Conflict(str(error)) from None


def commit(store, request, run_id):
    if store.lease_authority is not None:
        raise Conflict("Prepared worker authority requires its qualified destination integration")
    if not isinstance(request, Admission):
        raise Conflict("Prepared admission requires the normal Merge Stage preparation")
    api = storage_adapter().Adapter(store.engine, prefix=PREFIX, protocol=5)
    lease = _refusals(lambda: api.claim(request.batch.scope, "merge-stage"))
    return _refusals(lambda: api.apply(
        request.batch, lease, proposal_body=request.proposal,
        proposal_key=request.proposal_key, observer=run_id,
    ))


def proposal_body(body):
    """Keep the command and effect digest beside the separately retained intent."""
    result = {key: value for key, value in body.items() if key != "effects"}
    if "effects" in body:
        result["effects_sha256"] = digest(body["effects"])
    return result


def record(store, body, run_id, *, intent=None):
    api = storage_adapter().Adapter(store.engine, prefix=PREFIX, protocol=5)
    key = _refusals(lambda: api.record_proposal(
        body["command"]["batch_id"], proposal_body(body), run_id,
        outcome=body["outcome"],
        expected_generation=body.get("observed_generation", api.generation()),
        intent=intent,
    ))
    return {"assessment_id": key, **body}


def _source_pins(conn, assertions, deferred):
    api = storage_adapter()
    keys = {(a["source_code"], a.get("mapping_version", 1)) for a in assertions}
    keys.update((a["source_code"], 1) for a in [*assertions, *deferred])
    registered = api.dataset_readings(conn, keys)
    pins = {}
    for source in {a["source_code"] for a in [*assertions, *deferred]}:
        first = registered.get((source, 1))
        if first is None:
            raise Conflict("Dataset has no pinned registry authority")
        evidence = first["body"].get("registry_evidence", {})
        if (evidence.get("status") != "active"
                or evidence.get("version_id") != str(first["registry_version"])
                or evidence.get("source_family") != first["body"].get("family")):
            raise Conflict("Dataset has no pinned registry authority")
    for item in assertions:
        version = item.get("mapping_version", 1)
        mapped = registered.get((item["source_code"], version))
        if mapped is None or mapped["body"].get("schema_version") != item["schema_version"]:
            raise Conflict("Unsupported source schema")
        pins[mapping_pin(item["source_code"], version)] = digest(mapped["body"])
    for item in deferred:
        pins[schema_pin(item["source_code"], item["schema_version"])] = digest(
            [item["source_code"], item["schema_version"]]
        )
    return pins


def _changes(api, conn, entries):
    """Resolve all optimistic versions in grouped key probes."""
    unique = {}
    for entry in entries:
        key = entry["type"], entry["id"]
        if key in unique and unique[key] != entry:
            raise Conflict("Prepared lookup changes disagree")
        unique[key] = entry
    held = api.read(sorted(unique), lookup=True, connection=conn)
    result = []
    for key, entry in unique.items():
        old = held.get(key)
        raw = entry.get("body_json")
        removed = entry.get("removed", False)
        if old and key[0].startswith(("lookup/record_revision/", "lookup/deferred_record/")):
            if removed or bytes(old["body"]) != raw.encode():
                raise Conflict("Source publication identity has contradictory content")
        if old and not removed and bytes(old["body"]) == raw.encode():
            continue
        if removed and old is None:
            continue
        result.append(storage_adapter().IndexChange(
            *key, raw, expected_version=old["version"] if old else 0, removed=removed
        ))
    return tuple(result)


def execute(stage, *, command, assertions, decisions, identities, deferred,
            automatic, input_hash, run_id, preview, assessment_id, record):
    from edgar_warehouse.rules.source_engine import (
        prepare_record_history, prepare_record_lookups, prepare_scope_lookups,
    )

    if stage.store.lease_authority is not None:
        raise Conflict("Prepared worker authority requires its qualified destination integration")
    api_module = storage_adapter()
    api = api_module.Adapter(stage.store.engine, prefix=PREFIX, protocol=5)
    with stage.store.engine.connect() as conn:
        generation = api.generation(connection=conn)
        previous = api.read_batch(command["batch_id"], connection=conn)
        if previous is not None:
            kept = json.loads(bytes(previous["assessment"]))
            if kept.get("input_hash") != input_hash:
                raise Conflict("Batch key reused with different command")
            if preview:
                return {"preview": True, "duplicate": True, "effects": kept["effects"]}
            duplicate = True
        else:
            duplicate = False
            if automatic.get("observed_generation", generation) != generation:
                raise assessment.StaleAssessment("The proposal's observed state changed")
            reader = RecordReader(api, connection=conn, routes=matching.candidate_routes())
            policy = stage._check_rule_proposals(reader, command["policy_digest"],
                                                 None if preview else automatic, decisions)
            required = _source_pins(conn, assertions, deferred)
            allocated = api.read([("identity", i["entity_id"]) for i in identities],
                                 immutable=True, connection=conn)
            if allocated:
                raise Conflict("Identity allocation already exists")
            publications = reader.publications(sorted({i["kind"] for i in identities}))
            for identity in identities:
                old = publications.get(identity["kind"])
                if old and instant(identity["published_at"]) <= instant(old["published_at"]):
                    raise Conflict("New identity publication must follow its kind's retained floor")
            request, before, prepared = stage._prepare(
                reader, policy=policy, command=command, assertions=assertions,
                decisions=decisions, identities=identities, deferred=deferred,
                automatic=automatic, input_hash=input_hash,
            )
            if request["expected_generation"] != generation:
                raise assessment.StaleAssessment("Affected-record state changed during preparation")
            scope, state = prepared["scope"], prepared["state"]
            readings = {**scope.readings, **prepared["readings"]}
            readings = [a for a in readings.values() if a["subject"] in scope.subjects]
            subjects = sorted(scope.subjects)
            pointers = reader.current(subjects)
            evidence, history = prepare_record_history({
                "readings": readings, "identities": identities, "decisions": request["decisions"],
                "deferred": deferred, "occurrences": command.get("occurrences", []),
            })
            _, current = prepare_record_lookups({
                "readings": readings, "previous": pointers, "subjects": subjects,
                "bindings": {subject: identity for subject, identity in scope.replayed.items() if identity is not None},
                "quarantined": state.quarantined,
                "policy": policy, "normalizers": {kind.normalizer_name: kind.upper for kind in TYPES.values()},
                "batch_id": command["batch_id"],
                "occurrences": {o["assertion_id"]: o for o in command.get("occurrences", [])},
                "candidate_routes": matching.candidate_routes(),
            })
            old = prepared["old"]
            objects = {**old, **{(p["object_type"], p["object_id"]): p["body"]
                                 for p in request["projections"]}}
            _, projections = prepare_scope_lookups({
                "previous": [{"type": kind, "id": key, "body": body} for (kind, key), body in old.items()],
                "objects": [{"type": kind, "id": key, "body": body} for (kind, key), body in objects.items()],
                "identities": identities, "previous_publications": publications,
            })
            indexes = _changes(api, conn, [*history, *current, *projections])
            keys = [(p["object_type"], p["object_id"]) for p in request["projections"]]
            versions = api.read(keys, connection=conn)
            effects = {key: value for key, value in request.items() if key != "expected_generation"}
            frozen = {"catalog": digest(catalog.CATALOG), "policy": command["policy_digest"]}
            payload = {"contract_version": 2, "generation": generation + 1,
                       "policy_digest": command["policy_digest"],
                       "objects": request["projections"]}
            consumers = tuple(policy["required_consumers"])
            payloads = {}
            for consumer in consumers:
                content = {**payload, **({"effects": effects} if consumer == "journal" else {})}
                payloads[consumer] = api_module.ProducerPayload(
                    canonical(content).encode()[:-1] + b',"run_id":', b'}'
                )
            scope_key = canonical([command["consumer"], command.get("source_family", ""),
                                   command.get("publication_family", "")])
            batch = api_module.PreparedBatch(
                batch=command["batch_id"], run=run_id, scope=scope_key, pins=frozen,
                required_pins=required, assessment={"input_hash": input_hash, "effects": effects},
                expected_generation=generation, expected_checkpoint=command["expected_checkpoint"],
                checkpoint=command["checkpoint"], consumers=consumers, payload=payload,
                payloads=payloads, governed=True, publish_inputs=True, indexes=indexes,
                objects=tuple(api_module.Effect(*key, p["body"],
                    expected_version=versions[key]["version"] if key in versions else 0)
                    for p, key in zip(request["projections"], keys)),
                evidence=tuple(api_module.Effect(e["type"], e["id"], e["body_json"]) for e in evidence),
            )
            candidate = {"version": 1, "command": command, "outcome": "ready",
                         "observed_generation": generation, "rule_version": "merge-validation-v1",
                         "vetoes": [], "before": sorted(before, key=lambda p: (p["object_type"], p["object_id"])),
                         "effects": effects, **(record or {})}
            if preview:
                _refusals(lambda: api.preview(batch, proposal_body=proposal_body(candidate)))
                result = {"preview": True, "duplicate": False, "effects": request, "assessment": candidate}
                if record is not None:
                    result["_prepared_intent"] = batch.intent()
                return result
    if duplicate:
        original = json.loads(bytes(previous["intent"]))
        lease = _refusals(lambda: api.claim(bytes.fromhex(original["scope"]).decode(), "merge-stage"))
        return _refusals(lambda: api.replay(command["batch_id"], lease, observer=run_id))
    admission = Admission(batch, proposal=None if assessment_id else proposal_body(candidate),
                          proposal_key=assessment_id)
    return stage.store.commit(None, admission, run_id)
