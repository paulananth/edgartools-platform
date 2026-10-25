"""Invented normal worker inputs; no provider traffic or shared data."""
import os
import runpy
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ["READ_CASE"] = "join"
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
    current = proof(api, micros=-1000000)
    with pytest.raises(Conflict, match="expired_destination_authority"):
        stage.apply(**command)
    assert api.generation() == generation
    current = proof(api)
    assert stage.apply(**command)["generation"] == generation+1
    assert stage.apply(**command)["duplicate"]
    current = proof(api, micros=-1000000)
    with pytest.raises(Conflict, match="expired_destination_authority"):
        stage.apply(**command)
    assert api.generation() == generation+1
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
    sink = LocalContractSink(folder/"delivered")
    while stage.store.deliver_one("invented-export","invented-delivery",sink):
        pass
    final = coordinator.reconcile(root_run)
    assert final["end_to_end_complete"] and final["pending_publications"] == 0
    assert final["attempt_events"] == {"started":2,"finished":2}
    assert final["checks"][g["PRIMARY"]]["records"] == 1
    assert final["checks"][g["SECONDARY"]]["records"] == 1
    assert api.generation() == before+2
print("normal worker publication proof passed")
