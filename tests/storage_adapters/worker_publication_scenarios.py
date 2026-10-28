"""Invented normal worker inputs; no provider traffic or shared data."""
import os
import runpy
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ["READ_CASE"] = "details" if os.environ["READ_WORKER_CASE"] == "mapping_freeze" else "join"
g = runpy.run_module("tests.storage_adapters.record_read_scenarios")

from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.store import Store, Conflict, storage_adapter
from tests.storage_adapters.test_destination_authority import proof

runtime = g["runtime"]
api = storage_adapter().Adapter(runtime, prefix="mdm_store", protocol=6)
current = proof(api)
authority = SimpleNamespace(current=lambda:SimpleNamespace(proof=current))
stage = MergeStage(Store(runtime, lease_authority=authority))
command = {"batch_id":"invented-worker-batch", "run_id":str(uuid4()),
    "policy_digest":g["seed_pin"], "consumer":"invented-worker",
    "expected_checkpoint":0, "checkpoint":1, "as_of":g["AS_OF"],
    "assertions":[g["record"]("one",revision=2,fields={"invented_value":"changed"})]}
if os.environ["READ_WORKER_CASE"] == "authority":
    generation = api.generation()
    for current in (None, [], {}):
        with pytest.raises(Conflict, match="nonempty destination authority proof"):
            stage.apply(**command)
        assert api.generation() == generation
    current = proof(api, micros=-1000000)
    with pytest.raises(Conflict, match="expired_destination_authority"):
        stage.apply(**command)
    with pytest.raises(Conflict, match="expired_destination_authority"):
        stage.assess(**{**command,"decisions":[g["bind"]]})
    assert api.generation() == generation
    current = proof(api)
    assert stage.apply(**command)["generation"] == generation+1
    assert stage.apply(**command)["duplicate"]
    current = proof(api, micros=-1000000)
    with pytest.raises(Conflict, match="expired_destination_authority"):
        stage.apply(**command)
    assert api.generation() == generation+1
    old = proof(api)
    current = proof(api, token=2)
    assert stage.apply(**command)["duplicate"]
    other_attempt = [{**current[0],"attempt":str(uuid4())}]
    from sqlalchemy import func, select
    def frame():
        with g["owner"].connect() as conn:
            return {name: conn.scalar(select(func.count()).select_from(table))
                    for name,table in api.tables.items()}
    before = frame()
    for current in (old, other_attempt):
        with pytest.raises(Conflict,match="stale_destination_authority"):
            stage.apply(**command)
        assert api.generation() == generation+1 and frame() == before
if os.environ["READ_WORKER_CASE"] == "publication":
    import json
    from pathlib import Path
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.workers import mdm_publish
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-publication"
    sink = LocalContractSink(folder/"earlier")
    while stage.store.deliver_one("invented-export", "seed-worker", sink):
        pass
    result = stage.apply(**command)
    envelope = {"checks":["mdm.published"],
        "keys":{"batch_id":command["batch_id"],"consumer":"invented-export"},
        "claim":{"proof":current,"attempt":str(uuid4()),"run_id":str(uuid4())},
        "output":(folder/"worker.json").as_uri()}
    artifacts = Artifacts()
    candidate = mdm_publish.execute(envelope, artifacts)
    verified = {**envelope,"candidate":candidate}
    assert mdm_publish.verify(verified, artifacts) == ({"mdm.published":True}, [])
    assert mdm_publish.execute(envelope, artifacts) == candidate
    assert api.generation() == result["generation"]
    expired = {**envelope,"claim":{**envelope["claim"],"proof":proof(api,micros=-1000000)}}
    with pytest.raises(Conflict, match="expired_destination_authority"):
        mdm_publish.execute(expired, artifacts)
    body = json.loads(artifacts.verified(candidate))
    assert body["batch_id"] == command["batch_id"] and len(body["payload_hash"]) == 64
if os.environ["READ_WORKER_CASE"] == "merge_worker":
    import json
    from pathlib import Path
    from unittest.mock import patch
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.run import RunCoordinator
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.workers import mdm_merge
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-merge"
    artifacts = Artifacts()
    manifest = {"contract_version":2,"policy_digest":g["seed_pin"],"as_of":g["AS_OF"],
        "batches":[{"batch_id":"invented-worker-"+str(i),"stage":"mastering", "consumer":"invented-worker",
            "expected_checkpoint":i-1,"checkpoint":i,
            "assertions":[g["record"](key,source,revision=2,fields={"invented_value":"root-change"})]}
            for i,(key,source) in enumerate((("one",g["PRIMARY"]),("two",g["SECONDARY"])),1)]}
    reference = artifacts.put_bytes((folder/"manifest.json").as_uri(), json.dumps(manifest).encode())
    current = proof(api, micros=120000000)
    envelope = {"effect_key":"a"*64,"checks":["mdm.committed"],"input":reference,
        "claim":{"proof":current,"attempt":current[0]["attempt"],"run_id":current[0]["run_id"]},
        "output":(folder/"receipt.json").as_uri()}
    original = artifacts.put_bytes
    def lost(uri, data):
        result = original(uri,data)
        if uri == envelope["output"]:
            raise RuntimeError("invented lost terminal acknowledgement")
        return result
    before = api.generation()
    with patch.object(artifacts,"put_bytes",lost):
        with pytest.raises(RuntimeError,match="invented lost terminal acknowledgement"):
            mdm_merge.execute(envelope,artifacts)
    assert api.generation() == before+2
    with patch.object(MergeStage,"apply",side_effect=AssertionError("replay must start no merge")):
        candidate = mdm_merge.execute(envelope,artifacts)
    assert mdm_merge.verify({**envelope,"candidate":candidate},artifacts) == ({"mdm.committed":True},[])
    root_run = mdm_merge.mdm_run(envelope)
    coordinator = RunCoordinator(stage.store)
    pending = coordinator.reconcile(root_run)
    assert pending["observed_batches"] == pending["expected_batches"] == 2
    assert pending["pending_publications"] == 2 and not pending["end_to_end_complete"]
    observer = Store(runtime, read_only=True)
    assert observer.run_status(root_run) == {"batches":2,"pending":2,"publication_complete":False}
    assert observer.run_status(str(uuid4())) == {"batches":0,"pending":0,"publication_complete":False}
    from sqlalchemy import delete
    outbox = api.tables["outbox"]
    retained = api.read_batches([manifest["batches"][0]["batch_id"]],outboxes=True)[0]
    with g["owner"].begin() as conn:
        conn.execute(delete(outbox).where(outbox.c.batch_key == retained["batch_key"]))
    try:
        with pytest.raises(Conflict,match="Required consumer publications"):
            coordinator.reconcile(root_run)
        with pytest.raises(Conflict,match="Required consumer publications"):
            observer.run_status(root_run)
    finally:
        with g["owner"].begin() as conn:
            conn.execute(outbox.insert().values({column.name:retained[column.name] for column in outbox.c}))
    sink = LocalContractSink(folder/"delivered")
    while stage.store.deliver_one("invented-export","invented-delivery",sink):
        pass
    final = coordinator.reconcile(root_run)
    assert final["end_to_end_complete"] and final["pending_publications"] == 0
    assert observer.run_status(root_run) == {"batches":2,"pending":0,"publication_complete":True}
    assert final["attempt_events"] == {"started":2,"finished":2}
    assert final["checks"][g["PRIMARY"]]["records"] == 1
    assert final["checks"][g["SECONDARY"]]["records"] == 1
    assert api.generation() == before+2
    observed_envelope = {**envelope,"effect_key":"9"*64,"output":(folder/"observer.json").as_uri()}
    with patch.object(MergeStage,"_prepare",side_effect=AssertionError("observer prepared another merge")):
        observed_candidate = mdm_merge.execute(observed_envelope,artifacts)
    assert mdm_merge.verify({**observed_envelope,"candidate":observed_candidate},artifacts) == ({"mdm.committed":True},[])
    observer_root = mdm_merge.mdm_run(observed_envelope)
    assert observer_root != root_run and api.generation() == before+2
    observed_report = coordinator.reconcile(observer_root)
    assert observed_report["end_to_end_complete"] and observed_report["checks"] == {}
    assert all(row["run_key"] == storage_adapter().key(root_run)
               for row in api.read_batches([batch["batch_id"] for batch in manifest["batches"]]))
if os.environ["READ_WORKER_CASE"] == "journal":
    import json
    from pathlib import Path
    from unittest.mock import patch
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.change_journal.database import migrate
    from edgar_warehouse.change_journal.store import ChangeJournal, get_engine
    from edgar_warehouse.mdm.clean.journal_delivery import JournalPublisher
    from edgar_warehouse.workers import mdm_publish

    journal_owner = get_engine(os.environ["READ_JOURNAL_OWNER_URL"])
    migrate(journal_owner, runtime_role=os.environ["READ_JOURNAL_ROLE"],
            database_name=journal_owner.url.database)
    journal_owner.dispose()
    os.environ["CHANGE_JOURNAL_DATABASE_URL"] = os.environ["READ_JOURNAL_RUNTIME_URL"]
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    policy = {**g["inactive"], "version":"invented-journal", "required_consumers":["invented-export", "journal"]}
    with g["owner"].begin() as conn:
        command["policy_digest"] = g["register_policy"](conn, policy)
    committed = stage.apply(**command)
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-journal"
    rules = artifacts.put_bytes((folder/"rules.json").as_uri(), json.dumps({"body":{
        "source":g["PRIMARY"], "bronze":{"family":"fixture"}}}).encode())
    envelope = {"checks":["mdm.published"], "rules":rules,
        "keys":{"batch_id":command["batch_id"], "consumer":"journal"},
        "claim":{"proof":current,"attempt":current[0]["attempt"],"run_id":current[0]["run_id"]},
        "output":(folder/"receipt.json").as_uri()}
    # The Journal commits, but MDM has not acknowledged delivery yet.
    with patch.object(JournalPublisher,"verify",side_effect=RuntimeError("invented delivery interruption")):
        with pytest.raises(RuntimeError,match="invented delivery interruption"):
            mdm_publish.execute(envelope,artifacts)
    journal = ChangeJournal(get_engine())
    original = journal.get("mdm", "journal/"+command["batch_id"])
    assert original is not None
    assert api.publication_context(command["batch_id"],"journal") == json.dumps({
        "run_id":current[0]["run_id"],"source":g["PRIMARY"],"feed":"fixture"},
        sort_keys=True,separators=(",",":")).encode()
    replacement = [{**proof(api,token=2)[0], "run_id":str(uuid4()), "attempt":str(uuid4())}]
    retry = {**envelope,"claim":{"proof":replacement,"run_id":replacement[0]["run_id"],
                                 "attempt":replacement[0]["attempt"]}}
    candidate = mdm_publish.execute(retry,artifacts)
    assert mdm_publish.verify({**retry,"candidate":candidate},artifacts) == ({"mdm.published":True},[])
    assert journal.get("mdm","journal/"+command["batch_id"]) == original
    assert len(journal.list(source=g["PRIMARY"],feed="fixture")) == 1
    assert api.generation() == committed["generation"]
    with pytest.raises(Conflict,match="stale_destination_authority"):
        mdm_publish.execute(envelope,artifacts)
    journal.engine.dispose()
if os.environ["READ_WORKER_CASE"] == "forced":
    import io
    import json
    from contextlib import redirect_stdout
    from pathlib import Path
    from sqlalchemy import select
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.cli import main
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.workers import mdm_publish
    current = proof(api,micros=120000000)
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    added = g["record"]("three",identifiers={g["NAMESPACE"]:"272"})
    identity, decision = g["identity"](added,at="2026-03-02T00:00:00+00:00")
    stage.apply(**{**command,"as_of":"2026-04-01T00:00:00+00:00",
        "assertions":[added],"identities":[identity],"decisions":[decision]})
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-forced"
    while stage.store.deliver_one("invented-export","seed-worker",LocalContractSink(folder/"earlier")):
        pass
    def frame():
        with g["owner"].connect() as conn:
            return {name: list(conn.execute(select(api.tables[name]).order_by(*api.tables[name].primary_key)))
                    for name in ("current","history","lookup")}
    before = frame()
    original = api.snapshot_page(limit=10000)
    run_id = str(uuid4())
    argv = ["mdm","force-publish","--consumer","invented-export","--output",str(folder),
            "--run-id",run_id,"--page-size","1","--step","publish"]
    def invoke():
        output = io.StringIO()
        with redirect_stdout(output):
            assert main(argv) == 0
        return json.loads(output.getvalue())
    report = invoke()
    assert report["pages"] == report["records"] == len(original) and len(original) >= 2
    generation = api.generation()
    assert invoke() == report and api.generation() == generation and frame() == before
    units = artifacts.json(report["manifest"])["steps"]["publish"]
    sent = []
    for unit in units:
        batch_id = unit["keys"]["batch_id"]
        row = next(row for row in api.read_batches([batch_id],outboxes=True)
                   if bytes(row["consumer_bytes"]).decode() == "invented-export")
        payload = json.loads(bytes(row["payload"]))
        assert payload["forced"] and all(item["change"] == "snapshot" for item in payload["objects"])
        sent.extend((item["object_type"],item["object_id"]) for item in payload["objects"])
        envelope = {**unit,"checks":["mdm.published"],
            "claim":{"proof":current,"run_id":current[0]["run_id"],"attempt":current[0]["attempt"]}}
        candidate = mdm_publish.execute(envelope,artifacts)
        assert mdm_publish.verify({**envelope,"candidate":candidate},artifacts) == ({"mdm.published":True},[])
    assert sent == [key for key,_ in original] and frame() == before
    from edgar_warehouse.mdm.clean.forced_publication import page
    for consumer in ("journal","invented-unconfigured"):
        with pytest.raises((ValueError,Conflict),match="Journal|does not require"):
            page(stage.store,consumer,str(uuid4()),1,{"object_type":"","object_id":""},1)
    with pytest.raises(Conflict,match="differs from its original"):
        page(stage.store,"invented-export",run_id,1,{"object_type":"","object_id":""},2)
    assert api.generation() == generation
if os.environ["READ_WORKER_CASE"] == "mapping_freeze":
    import json
    from pathlib import Path
    from unittest.mock import patch
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.run import RunCoordinator
    from edgar_warehouse.mdm.clean.record_reads import RecordReader
    from edgar_warehouse.workers import mdm_merge
    from tests.support.reading import reading
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    contract = {"provider":"fixture","family":"fixture","schema_version":"1",
        "record_key":"key","publication_key":"version","effective_time":"effective_at","semantics":"patch",
        "adapter":{"version":"invented-first","kind":g["KIND"],"record_key":["key"],
                   "reading":reading({"invented_value":"first"})}}
    def register(body):
        with g["owner"].begin() as conn:
            g["register_dataset"](conn,g["PRIMARY"],str(uuid4()),body)
    register(contract)
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-mapping"
    raw = artifacts.put_bytes((folder/"records.jsonl").as_uri(),
        (json.dumps({"key":"one","first":"original","second":"corrected"})+"\n").encode())
    def batch(n):
        return {"batch_id":"invented-pinned-"+str(n),"stage":"mastering","consumer":"invented-pinned",
            "expected_checkpoint":n-1,"checkpoint":n,"input":{"path":"records.jsonl","sha256":raw["sha256"],
                "source_code":g["PRIMARY"],"record_count":1,"publication":{"publication_key":"invented-"+str(n),
                "revision":n+10,"effective_at":g["AT"],"observed_at":g["AS_OF"]}}}
    manifest = {"contract_version":2,"policy_digest":g["seed_pin"],"as_of":g["AS_OF"],"batches":[batch(1),batch(2)]}
    reference = artifacts.put_bytes((folder/"manifest.json").as_uri(),json.dumps(manifest).encode())
    current = proof(api,micros=120000000)
    envelope = {"effect_key":"b"*64,"checks":["mdm.committed"],"input":reference,
        "claim":{"proof":current,"run_id":current[0]["run_id"],"attempt":current[0]["attempt"]},
        "output":(folder/"receipt.json").as_uri()}
    corrected = {**contract,"adapter":{**contract["adapter"],"version":"invented-second",
                                            "reading":reading({"invented_value":"second"})}}
    original = RunCoordinator.execute
    def interrupted(self,*args,**kwargs):
        original(self,*args,**kwargs)
        register(corrected)
        raise RuntimeError("invented mapping interruption")
    before = api.generation()
    with patch.object(RunCoordinator,"execute",interrupted):
        with pytest.raises(RuntimeError,match="invented mapping interruption"):
            mdm_merge.execute(envelope,artifacts)
    assert api.generation() == before+1
    root = mdm_merge.mdm_run(envelope)
    assert RunCoordinator(stage.store).scope(root)["mapping_versions"] == {g["PRIMARY"]:2}
    candidate = mdm_merge.execute(envelope,artifacts)
    assert mdm_merge.verify({**envelope,"candidate":candidate},artifacts) == ({"mdm.committed":True},[])
    def current_evidence():
        reader = RecordReader(api)
        pointer = reader.current([g["holder"]["subject"]])[g["holder"]["subject"]]
        key = ("source-reading",pointer["assertion_id"])
        return reader.inputs([key])[key]
    evidence = current_evidence()
    assert evidence["mapping_version"] == 2 and evidence["fields"]["invented_value"]["value"] == "original"
    later = {**manifest,"batches":[batch(3)]}
    reference = artifacts.put_bytes((folder/"later.json").as_uri(),json.dumps(later).encode())
    next_envelope = {**envelope,"effect_key":"e"*64,"input":reference,"output":(folder/"later-receipt.json").as_uri()}
    mdm_merge.execute(next_envelope,artifacts)
    evidence = current_evidence()
    assert evidence["mapping_version"] == 3 and evidence["fields"]["invented_value"]["value"] == "corrected"
    assert api.generation() == before+3
if os.environ["READ_WORKER_CASE"] == "review_recovery":
    import json
    from pathlib import Path
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.evidence import subject_key
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.mdm.clean.run import RunCoordinator
    from edgar_warehouse.workers import mdm_merge
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    from tests.support.relationship_types import pinned_types
    policy = {**g["inactive"],"version":"invented-waiting-policy",
              **pinned_types({"invented_link":{"from":[g["KIND"]],"to":[g["KIND"]]}})}
    with g["owner"].begin() as conn:
        pin = g["register_policy"](conn,policy)
    waiting = g["record"]("one",revision=2,relationships=[{"type":"invented_link",
        "target_subject":subject_key(g["PRIMARY"],"future"),"valid_from":g["AT"],"valid_to":None,"scope":"invented"}])
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-review"
    manifest = {"contract_version":2,"policy_digest":pin,"as_of":g["AS_OF"],"batches":[{
        "batch_id":"invented-waiting","stage":"mastering","consumer":"invented-waiting",
        "expected_checkpoint":0,"checkpoint":1,"assertions":[waiting]}]}
    reference = artifacts.put_bytes((folder/"manifest.json").as_uri(),json.dumps(manifest).encode())
    current = proof(api,micros=120000000)
    envelope = {"effect_key":"f"*64,"checks":["mdm.committed"],"input":reference,
        "claim":{"proof":current,"run_id":current[0]["run_id"],"attempt":current[0]["attempt"]},
        "output":(folder/"receipt.json").as_uri()}
    candidate = mdm_merge.execute(envelope,artifacts)
    assert mdm_merge.verify({**envelope,"candidate":candidate},artifacts) == ({"mdm.committed":True},[])
    root = mdm_merge.mdm_run(envelope)
    coordinator = RunCoordinator(stage.store)
    report = coordinator.reconcile(root)
    assert report["waiting_links"] == 1 and report["unresolved_reviews"] == 0
    assert len(report["waiting_link_list"]) == 1 and not report["end_to_end_complete"]
    sink = LocalContractSink(folder/"delivered")
    while stage.store.deliver_one("invented-export","invented-worker",sink):
        pass
    assert coordinator.reconcile(root)["end_to_end_complete"]
    target = g["record"]("future",identifiers={g["NAMESPACE"]:"393"})
    identity,decision = g["identity"](target,at="2026-03-02T00:00:00+00:00")
    stage.apply(**{**command,"batch_id":"invented-resolution","run_id":str(uuid4()),"policy_digest":pin,
        "as_of":"2026-04-01T00:00:00+00:00","assertions":[target],"identities":[identity],"decisions":[decision]})
    corrected = coordinator.reconcile(root)
    assert corrected["waiting_links"] == 0 and corrected["waiting_link_list"] == []
    assert corrected["pending_publications"] == 1 and not corrected["end_to_end_complete"]
    assert stage.store.deliver_one("invented-export","invented-worker",sink)
    assert coordinator.reconcile(root)["end_to_end_complete"]
if os.environ["READ_WORKER_CASE"] == "held_review":
    import json
    from pathlib import Path
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.evidence import deferred_record
    from edgar_warehouse.mdm.clean.publication import LocalContractSink
    from edgar_warehouse.mdm.clean.run import RunCoordinator
    from edgar_warehouse.workers import mdm_merge
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    held = deferred_record(source_code=g["SECONDARY"],publication_key="invented-held",record_locator="held",
        schema_version="1",reason="invented_missing_key",raw_record={"invented_amount":7},
        provenance={"object":"invented/held.json"})
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-held"
    manifest = {"contract_version":2,"policy_digest":g["seed_pin"],"as_of":g["AS_OF"],"batches":[{
        "batch_id":"invented-held","stage":"mastering","consumer":"invented-held",
        "expected_checkpoint":0,"checkpoint":1,"deferred":[held]}]}
    reference = artifacts.put_bytes((folder/"manifest.json").as_uri(),json.dumps(manifest).encode())
    current = proof(api,micros=120000000)
    envelope = {"effect_key":"7"*64,"checks":["mdm.committed"],"input":reference,
        "claim":{"proof":current,"run_id":current[0]["run_id"],"attempt":current[0]["attempt"]},
        "output":(folder/"receipt.json").as_uri()}
    candidate = mdm_merge.execute(envelope,artifacts)
    assert mdm_merge.verify({**envelope,"candidate":candidate},artifacts) == ({"mdm.committed":True},[])
    sink = LocalContractSink(folder/"delivered")
    while stage.store.deliver_one("invented-export","invented-worker",sink):
        pass
    report = RunCoordinator(stage.store).reconcile(mdm_merge.mdm_run(envelope))
    assert report["pending_publications"] == 0 and report["unresolved_reviews"] == 1
    assert not report["end_to_end_complete"] and report["checks"][g["SECONDARY"]]["set_aside"] == 1
    retained = api.read([("deferred-record",held["deferred_id"])],immutable=True)
    assert json.loads(bytes(retained["deferred-record",held["deferred_id"]]["body"])) == held
print("normal worker publication proof passed")
