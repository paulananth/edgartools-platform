"""Convert a populated native MDM store to governed storage (ticket 146).

A native batch kept its whole command in `mdm.batch.effects`: its readings, the
decisions and new masters it applied (a rule's included), its set-aside records
and its `as_of`. The conversion carries the native policies and Dataset
Contract readings as they were approved, then applies every command again, in
the order it was saved, through the Merge Stage into a fresh governed store.
Each master keeps its id and each source record its binding. The native store
is read on read-only sessions and never written. A rerun skips the batches
already saved (by their batch ids), so a stopped conversion resumes.

An owner's one-off pass over a store of a fixed size: it reads the native
tables whole (tens of thousands of rows at most), never on a merge's path.
"""

from __future__ import annotations

from sqlalchemy import text

from .merge import MergeStage
from .store import Conflict, Store, digest, storage_adapter

COMMAND = ("batch_id", "policy_digest", "consumer", "expected_checkpoint", "checkpoint", "as_of",
           "assertions", "decisions", "identities", "deferred", "occurrences")


def _read_only(engine):
    """A native connection whose session refuses every write."""
    return engine.connect().execution_options(postgresql_readonly=True)


def _adapter(target):
    """The target's governed storage adapter."""
    return storage_adapter().Adapter(target, prefix="mdm_store", protocol=Store(target).protocol)


def pinned(body: dict) -> tuple[dict, set[str]]:
    """A native policy with its inline relationship types replaced by today's
    pinned code set (ticket 132), the one shape today's code refuses. Refused
    when a type both name is defined differently; a type the code set dropped
    is named in the report (a type added since needs no native record)."""
    from edgar_warehouse.rules import files
    from .relationships import types_of

    section = body.get("relationships")
    if not isinstance(section, dict) or "types" not in section:
        return body, set()
    policy = files.policy()
    pin = policy["relationships"]["pin"]
    governed = {**body, "relationships": policy["relationships"],
                "reference_pins": {**body.get("reference_pins", {}), pin: policy["reference_pins"][pin]}}
    today = types_of(governed)
    if any(name in section["types"] and section["types"][name] != spec for name, spec in today.items()):
        raise Conflict("A native relationship type differs from today's code set")
    return governed, set(section["types"]) - set(today)


def carry_registrations(native, target) -> dict:
    """The native policies (`pinned`) and every Dataset Contract reading, as
    approved. Returns each native policy digest's governed one."""
    from .prepared_registry import approve_mapping, approve_policy

    adapter = storage_adapter()
    digests, dropped = {}, set()
    with _read_only(native) as source, target.begin() as conn:
        policies = source.execute(text("SELECT digest, body FROM mdm.policy ORDER BY digest")).all()
        for key, body in policies:
            if digest(body) != key:
                raise Conflict("Native policy differs from its digest")
            governed, gone = pinned(body)
            dropped |= gone
            digests[key] = digest(governed)
            adapter.retain_policy(conn, governed, digests[key])
            approve_policy(conn, digests[key])
        readings = source.execute(text("""SELECT source_code, mapping_version, body, registry_version
            FROM mdm.dataset_mapping ORDER BY source_code, mapping_version""")).all()
        for code, version, body, registry in readings:
            held = adapter.dataset_reading(conn, code, version)
            if held is None:
                adapter.retain_dataset_reading(conn, code, version, body, str(registry))
            elif held["body"] != body:
                raise Conflict(f"Dataset {code} reading {version} differs from the native one")
            approve_mapping(conn, code, version, body)
    return {"policies": digests, "types_dropped": sorted(dropped), "dataset_readings": len(readings)}


def convert(native, target, *, limit: int | None = None) -> dict:
    """Apply each native batch's command again, oldest first. A batch already
    saved is skipped and not counted, so `limit` counts batches this run applies."""
    carried = carry_registrations(native, target)
    report = {"policies": len(carried["policies"]), "types_dropped": carried["types_dropped"],
              "dataset_readings": carried["dataset_readings"], "batches": 0, "already_saved": 0,
              "readings": 0, "decisions": 0, "masters": 0, "set_aside": 0}
    stage = MergeStage(Store(target))
    saved = _adapter(target).read_batch
    with _read_only(native) as source:
        batches = source.execute(text("SELECT batch_id, run_id FROM mdm.batch ORDER BY generation")).all()
    for batch_id, run_id in batches:
        if saved(batch_id) is not None:
            report["already_saved"] += 1
            continue
        if limit is not None and report["batches"] >= limit:
            break
        # One short read a batch: no native transaction stays open across saves.
        with _read_only(native) as source:
            effects = source.scalar(text("SELECT effects FROM mdm.batch WHERE batch_id=:b"), {"b": batch_id})
        command = {k: effects[k] for k in COMMAND if k in effects}
        command["policy_digest"] = carried["policies"][command["policy_digest"]]
        stage.apply(**command, run_id=str(run_id))
        report["batches"] += 1
        for key, part in (("readings", "assertions"), ("decisions", "decisions"),
                          ("masters", "identities"), ("set_aside", "deferred")):
            report[key] += len(command.get(part) or [])
    return report


def verify(native, target, *, page: int = 1000) -> dict:
    """The hard checks: the same masters, every source record present with the
    same binding, no decision lost (`passed`). Field values that differ from the
    native master's are counted by field, not failed. Reads every current
    master record whole, on purpose: a one-off check of the whole store."""
    import json
    from collections import Counter

    from .record_reads import for_connection

    with _read_only(native) as source:
        masters = dict(source.execute(text("SELECT entity_id::text, kind FROM mdm.master_entity")).all())
        bound = dict(source.execute(text("SELECT subject, entity_id::text FROM mdm.stage_record")).all())
        decisions = set(source.scalars(text("SELECT decision_id FROM mdm.decision")))
        native_fields = dict(source.execute(text(
            "SELECT object_id, body->'fields' FROM mdm.current_record WHERE object_type='entity'")).all())
    subjects, present, bindings, kept = sorted(bound), set(), {}, set()
    adapter = _adapter(target)
    with target.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        # Current master records only: a consumer page also returns each
        # master's whole saved batch request, once a row (ticket 147).
        held = {key: json.loads(record["body"]) for (_, key), record in adapter.iter_type("entity", connection=conn)}
        records = for_connection(conn)
        for i in range(0, len(subjects), page):
            chunk = subjects[i:i + page]
            present |= set(records.current(chunk))
            bindings.update(records.bindings(chunk))
            kept |= {d.get("decision_id") for d in records.related_decisions(chunk)}
    differ = Counter(name for key, fields in native_fields.items() if key in held
                     for name in set(fields or {}) | set(held[key].get("fields") or {})
                     if (fields or {}).get(name) != (held[key].get("fields") or {}).get(name))
    report = {
        "masters": len(masters), "masters_kept": sum((held.get(k) or {}).get("kind") == v for k, v in masters.items()),
        "masters_added": len(set(held) - set(masters)),
        "records": len(bound), "records_present": len(present),
        "bindings_kept": sum(bindings.get(s) == e for s, e in bound.items()),
        "decisions": len(decisions), "decisions_lost": len(decisions - kept),
        "fields_differing": dict(sorted(differ.items())),
    }
    report["passed"] = (report["masters_kept"] == report["masters"] and not report["masters_added"]
                        and report["records_present"] == report["bindings_kept"] == report["records"]
                        and not report["decisions_lost"])
    return report
