"""Durable manifest progress over opaque destination-owned execution metadata."""
from collections import Counter
import hashlib
import json
from uuid import uuid4

from .prepared import authority, _refusals
from .prepared_publication import adapter
from .prepared_registry import WAITING_INDEX
from .quality import run_checks
from .record_reads import RecordReader
from .store import Conflict, canonical, storage_adapter


def scope(store, run_id, *, connection=None):
    api = adapter(store)
    row = api.read([("run_scope", run_id)], metadata=True, connection=connection).get(("run_scope",run_id))
    return None if row is None else RecordReader._body(row)


def start(store, run_id, expected_batches, *, manifest_digest, mapping_versions=None):
    if not expected_batches or len(expected_batches) != len(set(expected_batches)):
        raise ValueError("A root run requires a nonempty frozen batch manifest")
    body = {"expected_batches":sorted(expected_batches),"manifest_digest":manifest_digest,"contract_version":2}
    if mapping_versions:
        body["mapping_versions"] = mapping_versions
    _refusals(lambda: adapter(store).retain_metadata("run_scope", run_id, body,
        immutable=True, authority=authority(store)))


def batches(store, run_id, expected, *, connection=None):
    api = adapter(store)
    return (api.observed_batches(run_id, connection=connection),
            {bytes(row["batch_bytes"]).decode() for row in api.read_batches(expected, connection=connection)})


def execute(store, run_id, batch_id, action, *, checks=None):
    frozen = scope(store, run_id)
    if frozen is None or batch_id not in frozen["expected_batches"]:
        raise Conflict("Batch differs from the frozen root run")
    attempt, api = str(uuid4()), adapter(store)
    def record(phase, detail):
        body = {"attempt":attempt,"batch_id":batch_id,"event":phase,**detail}
        _refusals(lambda: api.retain_metadata(RecordReader.group("run_attempts",run_id),
            canonical([attempt,phase]),body,immutable=True,authority=authority(store)))
    # Keep the checks before the action: a lost terminal acknowledgement must
    # retain the report profile of the business batch that actually committed.
    record("started", {} if checks is None else {"checks":checks})
    try:
        result = action()
    except Exception as error:
        try:
            record("error", {"error_type":type(error).__name__})
        except Exception as acknowledgement:
            raise error from acknowledgement
        raise
    record("finished", {"generation":result["generation"],"duplicate":result["duplicate"]})
    return result


def receipt(store, manifest, run_id, manifest_digest):
    api = adapter(store)
    expected = sorted(batch["batch_id"] for batch in manifest["batches"])
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        frozen = scope(store, run_id, connection=conn)
        if (frozen is None or frozen.get("manifest_digest") != manifest_digest
                or frozen.get("expected_batches") != expected):
            raise ValueError("MDM run scope differs from the input manifest")
        observed = api.observed_batches(run_id, connection=conn)
        rows = api.read_batches(expected, connection=conn)
    if set(expected) != observed or len(rows) != len(expected):
        raise ValueError("MDM has not committed every batch of this run")
    found = []
    for row in rows:
        raw = bytes(row["intent"])
        if hashlib.sha256(raw).hexdigest() != row["request_hash"]:
            raise Conflict("Retained batch request hash differs from original bytes")
        effects = json.loads(bytes(row["assessment"]))["effects"]
        batch = bytes(row["batch_bytes"]).decode()
        if effects["batch_id"] != batch or effects["policy_digest"] != manifest["policy_digest"]:
            raise Conflict("Committed batch differs from its frozen run")
        found.append({"batch_id":batch,"request_hash":row["request_hash"],
            "policy_digest":effects["policy_digest"],"consumer":effects["consumer"],
            "checkpoint":int(row["position"]),"generation":int(row["generation"])})
    return canonical({"version":1,"mdm_run":run_id,"policy_digest":manifest["policy_digest"],
                      "batches":sorted(found,key=lambda row:row["batch_id"])}).encode()


def waiting(api, conn):
    marker = api.read([("derived-index",WAITING_INDEX)], metadata=True, connection=conn)
    if not marker:
        raise Conflict("Waiting-review index owner qualification is incomplete")
    count, earliest, keys = 0, [], []
    def collect(keys):
        nonlocal count, earliest
        saved = api.read([("review",key) for key in keys],connection=conn)
        if len(saved) != len(keys):
            raise Conflict("Waiting-review reference has no current review")
        for (_,key), row in saved.items():
            body = RecordReader._body(row)
            if body.get("waiting_for_end") is not True or body.get("retired") is True:
                raise Conflict("Waiting-review reference differs from its current review")
            count += 1
            earliest.append((key,body))
        earliest = sorted(earliest,key=lambda row:row[0])[:100]
    for (_,key), row in api.iter_type(RecordReader.group("waiting_reviews"),lookup=True,connection=conn):
        if RecordReader._body(row) != {"type":"review","id":key,"immutable":False}:
            raise Conflict("Invalid waiting-review reference")
        keys.append(key)
        if len(keys) == 200:
            collect(keys)
            keys.clear()
    if keys:
        collect(keys)
    return count, [{"subject":body.get("subject"),"type":body.get("relationship",{}).get("type"),
        "target_subject":body.get("relationship",{}).get("target_subject"),
        "missing":body.get("missing"),"reason":body.get("reason")} for _,body in earliest]


def reconcile(store, run_id):
    api = adapter(store)
    with store.engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        frozen = scope(store,run_id,connection=conn)
        if frozen is None:
            raise Conflict("Root run was not registered")
        generation = api.generation(connection=conn)
        expected = set(frozen["expected_batches"])
        observed = api.observed_batches(run_id,connection=conn)
        saved = api.read_batches(sorted(observed),connection=conn)
        reviews = set()
        for row in saved:
            effects = json.loads(bytes(row["assessment"]))["effects"]
            reviews.update(item["object_id"] for item in effects["projections"] if item["object_type"] == "review")
        latest = api.read_origins([("review",key) for key in sorted(reviews)],connection=conn)
        required = observed | {row["origin"]["batch"] for row in latest.values()}
        pending = sum(not row["verified"] for row in api.read_batches(sorted(required),outboxes=True,connection=conn))
        unresolved = sum(RecordReader._body(row).get("open") is True and
                         RecordReader._body(row).get("blocking") is not False for row in latest.values())
        waiting_count, waiting_rows = waiting(api,conn)
        events, profiles = Counter(), {}
        produced = {bytes(row["batch_bytes"]).decode() for row in saved if row["run_key"] == storage_adapter().key(run_id)}
        for _,row in api.iter_type(RecordReader.group("run_attempts",run_id),metadata=True,connection=conn):
            body = RecordReader._body(row)
            if body["event"] not in ("started","finished","error") or body["batch_id"] not in expected:
                raise Conflict("Attempt differs from the frozen root run")
            events[body["event"]] += 1
            if body["batch_id"] in produced and "checks" in body:
                old = profiles.setdefault(body["batch_id"],body["checks"])
                if old != body["checks"]:
                    raise Conflict("A batch run-check profile changed")
        kept = api.read([("run_report",run_id)],metadata=True,connection=conn).get(("run_report",run_id))
    checks = list(profiles.values())
    report = {"expected_batches":len(expected),"observed_batches":len(observed),
        "missing_batches":sorted(expected-observed),"unexpected_batches":sorted(observed-expected),
        "pending_publications":pending,"unresolved_reviews":unresolved,
        "waiting_links":waiting_count,"waiting_link_list":waiting_rows,"attempt_events":dict(events),
        "checks":run_checks([item["profile"] for item in checks],as_of=checks[0]["as_of"]) if checks else {},
        "end_to_end_complete":expected == observed and pending == 0 and unresolved == 0}
    _refusals(lambda: api.retain_metadata("run_report",run_id,report,
        expected_version=0 if kept is None else kept["version"],
        authority=authority(store),expected_generation=generation))
    return report
