"""Convert a populated native MDM store to governed storage (ticket 146).

A native batch kept its whole command in `mdm.batch.effects`: its readings, the
decisions and new masters it applied (a rule's included), its set-aside records
and its `as_of`. The conversion carries the native policies and Dataset
Contract readings as they were approved, then applies every command again, in
the order it was saved, through the Merge Stage into a fresh governed store.
Each master keeps its id and each source record its binding. The native store
is read in a read-only transaction and never written. A rerun skips the
batches already saved (by their batch ids), so a stopped conversion resumes.
"""

from __future__ import annotations

from sqlalchemy import text

from .merge import MergeStage
from .store import Conflict, Store, digest, storage_adapter

COMMAND = ("batch_id", "policy_digest", "consumer", "expected_checkpoint", "checkpoint", "as_of",
           "assertions", "decisions", "identities", "deferred", "occurrences")


def _read_only(engine):
    conn = engine.connect()
    conn.execute(text("SET TRANSACTION READ ONLY"))
    return conn


def pinned(body: dict) -> tuple[dict, set[str]]:
    """A native policy with its inline relationship types replaced by today's
    pinned code set (ticket 132), the one shape today's code refuses. Refused
    when an inline type the code set keeps is defined differently; a type the
    code set dropped is named in the report."""
    from edgar_warehouse.rules import files
    from .relationships import types_of

    section = body.get("relationships")
    if not isinstance(section, dict) or "types" not in section:
        return body, set()
    policy = files.policy()
    name = policy["relationships"]["pin"]
    governed = {**body, "relationships": policy["relationships"],
                "reference_pins": {**body.get("reference_pins", {}), name: policy["reference_pins"][name]}}
    today = types_of(governed)
    if any(section["types"].get(name) != spec for name, spec in today.items()):
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
    """Apply each native batch's command again, oldest first; saved ones are skipped."""
    carried = carry_registrations(native, target)
    report = {"policies": len(carried["policies"]), "types_dropped": carried["types_dropped"],
              "dataset_readings": carried["dataset_readings"], "batches": 0,
              "readings": 0, "decisions": 0, "masters": 0, "set_aside": 0}
    stage = MergeStage(Store(target))
    with _read_only(native) as source:
        batches = source.execute(text("SELECT batch_id, run_id FROM mdm.batch ORDER BY generation")).all()
        for batch_id, run_id in batches[:limit]:
            effects = source.scalar(text("SELECT effects FROM mdm.batch WHERE batch_id=:b"), {"b": batch_id})
            command = {k: effects[k] for k in COMMAND if k in effects}
            command["policy_digest"] = carried["policies"][command["policy_digest"]]
            stage.apply(**command, run_id=str(run_id))
            report["batches"] += 1
            report["readings"] += len(command["assertions"])
            report["decisions"] += len(command["decisions"])
            report["masters"] += len(command["identities"])
            report["set_aside"] += len(command.get("deferred") or [])
    return report


def verify(native, target) -> dict:
    """The same masters, the same binding for every source record, no decision lost."""
    from .consumer import ContractReader
    from .record_reads import for_connection

    with _read_only(native) as source:
        masters = dict(source.execute(text("SELECT entity_id::text, kind FROM mdm.master_entity")).all())
        bound = dict(source.execute(text("SELECT subject, entity_id::text FROM mdm.stage_record")).all())
        decisions = set(source.scalars(text("SELECT decision_id FROM mdm.decision")))
    reader, after, held, generation = ContractReader(target), "", {}, None
    while after is not None:
        page = reader.snapshot_page("entity", after=after, generation=generation, limit=1000)
        generation = page["generation"]
        held.update((row["object_id"], row["body"]["kind"]) for row in page["items"])
        after = page["next_after"]
    with target.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        reader = for_connection(conn)
        found = reader.bindings(sorted(bound))
        kept = {d.get("decision_id") for d in reader.related_decisions(bound)}
    return {
        "masters": len(masters), "masters_kept": sum(held.get(k) == v for k, v in masters.items()),
        "masters_added": len(set(held) - set(masters)),
        "records": len(bound), "bindings_kept": sum(found.get(s) == e for s, e in bound.items()),
        "decisions": len(decisions), "decisions_lost": len(decisions - kept),
    }
