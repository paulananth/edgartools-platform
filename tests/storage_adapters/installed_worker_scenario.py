"""Executed as a string by installed Python in isolated mode outside the repo."""
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select, text

import edgar_control
import source_contract
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.change_journal.database import migrate as migrate_journal
from edgar_warehouse.change_journal.store import ChangeJournal, get_engine
from edgar_warehouse.cli import main
from edgar_warehouse.database_connections import engine_from_env, storage_adapter
from edgar_warehouse.mdm.clean import prepared_runs
from edgar_warehouse.mdm.clean.evidence import assertion
from edgar_warehouse.mdm.clean.run import RunCoordinator
from edgar_warehouse.mdm.clean.store import Store, migrate, register_dataset, register_policy
from edgar_warehouse.workers import mdm_merge, mdm_publish

SPEC = json.loads(sys.stdin.read())
install = Path(os.environ["WORKER_INSTALL"]).resolve()
for module in (prepared_runs,mdm_merge,mdm_publish,edgar_control,source_contract):
    assert Path(module.__file__).resolve().is_relative_to(install)
assert "bundle_data" in str(Path(storage_adapter().__file__).resolve())
owner,runtime = engine_from_env("READ_OWNER_URL"),engine_from_env("READ_RUNTIME_URL")
migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"],prepared=True)
jowner = get_engine(os.environ["READ_JOURNAL_OWNER_URL"])
migrate_journal(jowner,runtime_role=os.environ["READ_JOURNAL_ROLE"],database_name=jowner.url.database)
reader_role = os.environ["READ_VERIFIER_ROLE"]
for database in (owner,jowner):
    quote = database.dialect.identifier_preparer.quote
    with database.begin() as conn:
        if database.dialect.name == "postgresql":
            schemas = ("public","mdm") if database is owner else ("public","journal")
            for schema in schemas:
                conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {quote(schema)} TO {quote(reader_role)}")
                conn.exec_driver_sql(f"GRANT SELECT ON ALL TABLES IN SCHEMA {quote(schema)} TO {quote(reader_role)}")
        else:
            conn.execute(text(f"GRANT SELECT ON {quote(database.url.database)}.* TO '{reader_role}'@'%'"))
api = storage_adapter().Adapter(runtime,prefix="mdm_store",protocol=6)
primary,secondary = SPEC["sources"]
rule = {"rule_id":"invented-bind","version":"1","family":"binding",
    "applies_to_verdict":SPEC["kind"],"emits":["bind"],"on_no_match":"mint","source":primary,
    "when":[{"primitive":"identifier_match@1","args":{"namespace":"invented_number"}},
            {"primitive":"identifier_cardinality@1","args":{"namespace":"invented_number"}}]}
join = {**rule,"rule_id":"invented-join","on_no_match":"wait"}
del join["source"]
rules = [rule,join]
policy = {"version":"invented-installed-worker","required_consumers":["invented-export","journal"],
    "kinds":{SPEC["kind"]:{"version":"1","defaults":{"sources":SPEC["sources"],"allow_unknown_effective":True},
        "rules":rules,"identifiers":{"invented_number":SPEC["identifier"]}}},
    "automatic_rules":[{"kind":SPEC["kind"],"family":"binding","rule_id":r["rule_id"],
        "rule_version":"1","verdict":"bind","activation":"deterministic"} for r in rules]}
with owner.begin() as conn:
    pin = register_policy(conn,policy)
    for source,spec in SPEC["contracts"].items():
        register_dataset(conn,source,spec["body"],rules_authority=spec["authority"])
artifacts = Artifacts()
folder = install/("worker-proof-"+uuid4().hex)
records = [assertion(source_code=source,record_key="invented-one",publication_key="invented-first",
    revision=1,effective_at="2026-01-01T00:00:00Z",kind=SPEC["kind"],
    identifiers={"invented_number":"171"},fields={"invented_value":10**80+1}) for source in SPEC["sources"]]
manifest = {"contract_version":2,"policy_digest":pin,"as_of":"2026-03-01T00:00:00Z",
    "batches":[{"batch_id":"invented-installed-"+str(n),"stage":"mastering","consumer":"invented-worker",
        "expected_checkpoint":n-1,"checkpoint":n,"assertions":[record]} for n,record in enumerate(records,1)]}
reference = artifacts.put_bytes((folder/"manifest.json").as_uri(),json.dumps(manifest).encode())
SQL = importlib.import_module(api.__class__.__module__.rpartition(".")[0]+".adapter_sql").SQL
with runtime.connect() as conn:
    epoch = int(conn.scalar(text("SELECT "+SQL(runtime.dialect,api.tables,protocol=6).now)))
expires = (datetime(1970,1,1,tzinfo=UTC)+timedelta(microseconds=epoch+180000000)).isoformat()
proof = [{"resource":"invented-installed-worker","token":1,"run_id":str(uuid4()),
          "attempt":str(uuid4()),"expires_at":expires}]
envelope = {"checks":["mdm.committed"],"effect_key":"c"*64,"input":reference,
    "output":(folder/"merged.json").as_uri(),"claim":{"proof":proof,"run_id":proof[0]["run_id"],"attempt":proof[0]["attempt"]}}
WORKER = '''
import json,sys
from unittest.mock import patch
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.workers import mdm_merge,mdm_publish
task=json.loads(sys.stdin.read()); envelope=task["envelope"]; artifacts=Artifacts()
worker=mdm_merge if task["operation"]=="merge" else mdm_publish
if task["mode"]=="verify":
    result=worker.verify(envelope,artifacts)
elif task["mode"]=="lost_ack":
    original=artifacts.put_bytes
    def lost(uri,body):
        result=original(uri,body)
        if uri==envelope["output"]: raise RuntimeError("invented terminal interruption")
        return result
    with patch.object(artifacts,"put_bytes",lost):
        try: worker.execute(envelope,artifacts)
        except RuntimeError as error:
            assert str(error)=="invented terminal interruption"; result={"interrupted":True}
        else: raise AssertionError("interruption did not occur")
elif task["mode"]=="lost_delivery":
    with patch("edgar_warehouse.mdm.clean.journal_delivery.JournalPublisher.verify",side_effect=RuntimeError("invented delivery interruption")):
        try: worker.execute(envelope,artifacts)
        except RuntimeError as error:
            assert str(error)=="invented delivery interruption"; result={"interrupted":True}
        else: raise AssertionError("interruption did not occur")
elif task["mode"]=="retry":
    with patch("edgar_warehouse.mdm.clean.merge.MergeStage.apply",side_effect=AssertionError("retry merged again")):
        result=worker.execute(envelope,artifacts)
else: result=worker.execute(envelope,artifacts)
print(json.dumps(result))
'''


def invoke(operation,value,mode="execute"):
    reader = mode == "verify"
    env = {**os.environ,"MDM_DATABASE_URL":os.environ["READ_VERIFIER_URL" if reader else "READ_RUNTIME_URL"],
        "MDM_APPLICATION_ROLE":os.environ["READ_VERIFIER_ROLE" if reader else "READ_RUNTIME_ROLE"],
        "CHANGE_JOURNAL_DATABASE_URL":os.environ["READ_JOURNAL_VERIFIER_URL" if reader else "READ_JOURNAL_RUNTIME_URL"]}
    done = subprocess.run([sys.executable,"-I","-c",WORKER],cwd=install,env=env,
        input=json.dumps({"operation":operation,"mode":mode,"envelope":value}),capture_output=True,text=True,timeout=45)
    if done.returncode:
        (folder/"subprocess-diagnostic.log").write_text(done.stdout+"\n"+done.stderr)
    assert done.returncode == 0, "installed worker subprocess failed; private diagnostic retained"
    return json.loads(done.stdout.splitlines()[-1])


assert invoke("merge",envelope,"lost_ack") == {"interrupted":True}
assert api.generation() == 2
candidate = invoke("merge",envelope,"retry")
assert invoke("merge",{**envelope,"candidate":candidate},"verify") == [{"mdm.committed":True},[]]
run_id = mdm_merge.mdm_run(envelope)
store = Store(runtime,lease_authority=SimpleNamespace(current=lambda:SimpleNamespace(proof=proof)))
coordinator = RunCoordinator(store)
assert coordinator.reconcile(run_id)["pending_publications"] == 4
for n,batch in enumerate(manifest["batches"]):
    rules_ref = artifacts.put_bytes((folder/(str(n)+"-rules.json")).as_uri(),json.dumps({"body":{
        "source":SPEC["sources"][n],"bronze":{"family":"fixture"}}}).encode())
    for consumer in ("invented-export","journal"):
        unit = {"checks":["mdm.published"],"rules":rules_ref,
            "keys":{"batch_id":batch["batch_id"],"consumer":consumer},
            "output":(folder/(consumer+str(n)+".json")).as_uri(),
            "claim":{"proof":proof,"run_id":proof[0]["run_id"],"attempt":proof[0]["attempt"]}}
        if n == 0 and consumer == "journal":
            assert invoke("publish",unit,"lost_delivery") == {"interrupted":True}
            proof = [{**proof[0],"token":2,"run_id":str(uuid4()),"attempt":str(uuid4())}]
            unit["claim"] = {"proof":proof,"run_id":proof[0]["run_id"],"attempt":proof[0]["attempt"]}
        published = invoke("publish",unit)
        assert invoke("publish",{**unit,"candidate":published},"verify") == [{"mdm.published":True},[]]
assert api.generation() == 2 and coordinator.reconcile(run_id)["end_to_end_complete"]
journal = ChangeJournal(get_engine(os.environ["READ_JOURNAL_VERIFIER_URL"]))
assert len(journal.list()) == 2
# The verifier reads receipts but cannot retain even execution metadata.
reader = storage_adapter().Adapter(engine_from_env("READ_VERIFIER_URL"),prefix="mdm_store",protocol=6)
try:
    reader.retain_metadata("invented","forbidden",{})
except storage_adapter().AdapterError:
    pass
else:
    raise AssertionError("read-only verifier wrote metadata")
with runtime.connect() as conn:
    table = api.tables["current"]
    before = list(conn.execute(select(table).order_by(*table.primary_key)))
os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
forced_run = str(uuid4())
args = ["mdm","force-publish","--consumer","invented-export","--run-id",forced_run,
        "--page-size","2","--step","publish","--output",str(folder/"forced")]
def force():
    output = io.StringIO()
    with redirect_stdout(output): assert main(args) == 0
    return json.loads(output.getvalue())
forced = force()
generation = api.generation()
assert force() == forced and api.generation() == generation
for unit in artifacts.json(forced["manifest"])["steps"]["publish"]:
    value = {**unit,"checks":["mdm.published"],"claim":{"proof":proof,
        "run_id":proof[0]["run_id"],"attempt":proof[0]["attempt"]}}
    published = invoke("publish",value)
    assert invoke("publish",{**value,"candidate":published},"verify") == [{"mdm.published":True},[]]
assert invoke("merge",{**envelope,"claim":{"proof":proof,"run_id":proof[0]["run_id"],"attempt":proof[0]["attempt"]}},"retry") == candidate
assert api.generation() == generation
with runtime.connect() as conn:
    assert list(conn.execute(select(table).order_by(*table.primary_key))) == before
for engine in (owner,runtime,jowner,journal.engine,reader.engine): engine.dispose()
print(json.dumps({"installed":True,"separate_reader":True,"sources":2,"commits":2,
    "journal_events":2,"lost_ack":True,"delivery_recovery":True,"forced":True,"zero_work":True}))
