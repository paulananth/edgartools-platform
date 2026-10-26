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
print("normal worker publication proof passed")
