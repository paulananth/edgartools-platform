"""Installed normal-caller boundaries not covered by the earlier slice scenarios."""
from contextlib import contextmanager
import copy
import json
import os
import runpy
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import prepared_registry
from edgar_warehouse.mdm.clean.evidence import decision
from edgar_warehouse.mdm.clean.merge import MergeStage
from edgar_warehouse.mdm.clean.prepared_runs import waiting
from edgar_warehouse.mdm.clean.record_reads import RecordReader
from edgar_warehouse.mdm.clean.store import Conflict, Store, migrate, register_policy
from tests.storage_adapters.test_destination_authority import proof

case = os.environ["WORKFLOW_CASE"].split("-", 1)[1]
os.environ["READ_CASE"] = "join"
if case.startswith("upgrade"):
    # Select the established predecessor owner contract; business state is still
    # created by normal restricted-role MergeStage calls, not prepared seeding.
    with patch.object(prepared_registry, "PROTOCOL", 5), patch.object(prepared_registry, "finish_indexes"):
        g = runpy.run_module("tests.storage_adapters.record_read_scenarios")
else:
    g = runpy.run_module("tests.storage_adapters.record_read_scenarios")
owner, runtime, module = g["owner"], g["runtime"], g["api"]
with runtime.connect() as connection:
    version = module.storage_version(connection)
api = module.Adapter(runtime, prefix="mdm_store", protocol=version)
stage = MergeStage(Store(runtime))
root = g["master"]["entity_id"]
position = 0


def save(**parts):
    global position
    result = stage.apply(batch_id="invented-boundary-"+str(position+1), run_id=str(uuid4()),
        policy_digest=parts.pop("policy_digest", g["seed_pin"]), consumer="invented-boundary",
        expected_checkpoint=position, checkpoint=position+1, as_of=g["AS_OF"], **parts)
    position += 1
    return result


def entity():
    return RecordReader._body(api.read([("entity",root)])["entity",root])


def frame(names=None):
    # Test-only full snapshots compare rollback bytes; normal readers stay indexed.
    with owner.connect() as conn:
        return {name: list(conn.execute(select(table).order_by(*table.primary_key)))
                for name,table in api.tables.items()
                if name in names} if names is not None else {
                    name:list(conn.execute(select(table).order_by(*table.primary_key)))
                    for name,table in api.tables.items() if name not in {"lease","migration"}}


@contextmanager
def fault(table, *, delay=False):
    target = owner.dialect.identifier_preparer.format_table(api.tables[table])
    pg = owner.dialect.name == "postgresql"
    if pg:
        function = "invented_boundary_fault"
        body = "PERFORM pg_sleep(1.2); RETURN NEW;" if delay else "RAISE EXCEPTION 'invented_boundary_fault';"
        statements = [f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} END $$",
                      f"CREATE TRIGGER invented_boundary_fault BEFORE INSERT OR UPDATE ON {target} FOR EACH ROW EXECUTE FUNCTION {function}()"]
        drops = [f"DROP TRIGGER invented_boundary_fault ON {target}", f"DROP FUNCTION {function}()"]
    else:
        body = "DO SLEEP(1.2)" if delay else "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='invented_boundary_fault'"
        statements = [f"CREATE TRIGGER invented_boundary_{action.lower()} BEFORE {action} ON {target} FOR EACH ROW {body}"
                      for action in ("INSERT", "UPDATE")]
        drops = [f"DROP TRIGGER invented_boundary_{action}" for action in ("insert", "update")]
    with owner.begin() as conn:
        for statement in statements:
            conn.exec_driver_sql(statement)
    try:
        yield
    finally:
        with owner.begin() as conn:
            for statement in drops:
                conn.exec_driver_sql(statement)


if case.startswith("fault_"):
    table = case.removeprefix("fault_")
    before, generation = frame(), api.generation()
    record = g["record"]("one", revision=2, fields={"invented_value":10**80+3})
    with fault(table):
        with pytest.raises(Conflict):
            save(assertions=[record])
        assert frame() == before and api.generation() == generation
    assert save(assertions=[record])["generation"] == generation+1
    assert entity()["fields"]["invented_value"]["value"] == 10**80+3
elif case == "late_expiry":
    stage = MergeStage(Store(runtime, lease_authority=SimpleNamespace(current=lambda:SimpleNamespace(proof=proof(api, micros=1000000)))))
    before, generation = frame(), api.generation()
    with fault("current",delay=True):
        with pytest.raises(Conflict, match="destination_authority_expired_before_save"):
            save(assertions=[g["record"]("one", revision=2, fields={"invented_value":9})])
    # Admission refreshes the external lease independently; no business effect commits.
    names = {"batch","current","history","evidence","lookup","checkpoint","outbox","proposal","proposal_event"}
    assert {name:rows for name,rows in frame().items() if name in names} == {name:rows for name,rows in before.items() if name in names}
    assert api.generation() == generation
elif case in {"held_transaction", "invalid_wire"}:
    retained = api.read_batches([g["command"]["batch_id"]])[0]
    intent = bytes(retained["intent"]).decode()
    scope = bytes.fromhex(json.loads(intent)["scope"]).decode()
    current = proof(api, micros=1000000)
    lease = api.claim(scope,"merge-stage",authority=current)
    wire = {"intent":intent,"observer":"invented-raw-retry".encode().hex(),
        "owner":lease.owner.encode().hex(),"fence":str(lease.fence),
        "expected_generation":str(api.generation()),
        "authority":module.authority_wire(current)}
    assert api._rpc("apply",wire)["duplicate"] == 1, "The control request must be valid before injecting a fault"
    wire["authority"] = module.authority_wire(proof(api,micros=1000000))
    before = frame()
    name = api.routines["apply"][0]
    statement = f"SELECT * FROM {name}(:wire)" if owner.dialect.name == "postgresql" else f"CALL {name}(:wire)"
    if case == "held_transaction":
        with pytest.raises(DBAPIError) as refused, runtime.begin() as conn:
            if owner.dialect.name == "mysql":
                conn.execute(select(api.tables["gate"])).all()
            conn.execute(text(statement),{"wire":json.dumps(wire)}).all()
            if owner.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_sleep(1.2)"))
        if owner.dialect.name == "postgresql":
            assert refused.value.orig.diag.message_primary == "lease_invalid_at_commit"
        else:
            assert refused.value.orig.args[0] == 1568
    else:
        for invalid in ([],{},[{"token":"1"}]):
            with pytest.raises(DBAPIError), runtime.begin() as conn:
                conn.execute(text(statement),{"wire":json.dumps({**wire,"authority":invalid})}).all()
    assert frame() == before
elif case.startswith("upgrade"):
    # Add real waiting reviews through the normal predecessor MergeStage.
    policy = {**g["policy"], "version":"invented-upgrade", "relationships":{
        "version":"invented-upgrade", "types":{"invented_link":{"from":[g["KIND"]],"to":[g["KIND"]]}}}}
    with owner.begin() as conn:
        pin = register_policy(conn,policy)
    from edgar_warehouse.mdm.clean.evidence import subject_key
    records = [g["record"]("invented-waiting-"+str(n), identifiers={g["NAMESPACE"]:str(500+n)},
        relationships=[{"type":"invented_link","target_subject":subject_key(g["PRIMARY"],"future"),
                        "valid_from":g["AT"],"valid_to":None,"scope":"invented"}]) for n in range(3)]
    save(policy_digest=pin,assertions=records)
    names = {"current","history","batch","evidence","outbox","checkpoint"}
    before, generation = frame(names), api.generation()
    if case == "upgrade_interrupted":
        def interrupted(conn,cursor,statement,params,context,many):
            if statement.lstrip().upper().startswith("CREATE") and "_retain_metadata" in statement:
                raise RuntimeError("invented upgrade interruption")
        event.listen(owner,"before_cursor_execute",interrupted)
        try:
            with pytest.raises(RuntimeError,match="invented upgrade interruption"):
                migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"],prepared=True)
        finally:
            event.remove(owner,"before_cursor_execute",interrupted)
        assert frame(names) == before
    migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"],prepared=True)
    api = module.Adapter(runtime,prefix="mdm_store",protocol=6)
    assert frame(names) == before and api.generation() == generation
    with runtime.connect() as conn:
        count, rows = waiting(api,conn)
        assert count == len(rows) == 3
    original = g["command"]
    assert MergeStage(Store(runtime)).apply(**original)["duplicate"]
    assert frame(names) == before and api.generation() == generation
    migrate(owner,application_role=os.environ["READ_RUNTIME_ROLE"],prepared=True)
    assert frame(names) == before
elif case.startswith("identifier_"):
    from pathlib import Path
    from unittest.mock import patch
    from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
    from edgar_warehouse.mdm.clean.run import RunCoordinator
    from edgar_warehouse.workers import mdm_merge
    os.environ["MDM_DATABASE_URL"] = os.environ["READ_RUNTIME_URL"]
    os.environ["MDM_APPLICATION_ROLE"] = os.environ["READ_RUNTIME_ROLE"]
    primary = g["record"]("invented-order-primary",identifiers={g["NAMESPACE"]:"777"},fields={"invented_value":"primary"})
    secondary = g["record"]("invented-order-secondary",g["SECONDARY"],identifiers={g["NAMESPACE"]:"777"},fields={"invented_value":"secondary"})
    records = [primary,secondary] if case.endswith("holder_first") else [secondary,primary,secondary]
    artifacts = Artifacts()
    folder = Path(os.environ["EDGAR_RULES_ROOT"])/"invented-order"
    manifest = {"contract_version":2,"policy_digest":g["pin"],"as_of":g["AS_OF"],"batches":[{
        "batch_id":"invented-order-"+str(n),"stage":"mastering","consumer":"invented-order",
        "expected_checkpoint":n-1,"checkpoint":n,"assertions":[record]} for n,record in enumerate(records,1)]}
    reference = artifacts.put_bytes((folder/"manifest.json").as_uri(),json.dumps(manifest).encode())
    current = proof(api,micros=120000000)
    envelope = {"effect_key":"9"*64,"checks":["mdm.committed"],"input":reference,
        "claim":{"proof":current,"run_id":current[0]["run_id"],"attempt":current[0]["attempt"]},
        "output":(folder/"receipt.json").as_uri()}
    if case.endswith("candidate_first"):
        original = RunCoordinator.execute
        def interrupt(self,*args,**kwargs):
            original(self,*args,**kwargs)
            raise RuntimeError("invented first-wait interruption")
        with patch.object(RunCoordinator,"execute",interrupt):
            with pytest.raises(RuntimeError,match="invented first-wait interruption"):
                mdm_merge.execute(envelope,artifacts)
        pointer = RecordReader(api).current([secondary["subject"]])[secondary["subject"]]
        assert pointer["entity_id"] is None
    result = mdm_merge.execute(envelope,artifacts)
    assert mdm_merge.verify({**envelope,"candidate":result},artifacts) == ({"mdm.committed":True},[])
    pointers = RecordReader(api).current([primary["subject"],secondary["subject"]])
    target = pointers[primary["subject"]]["entity_id"]
    assert target and target != root and pointers[secondary["subject"]]["entity_id"] == target
    master = RecordReader._body(api.read([("entity",target)])["entity",target])
    assert master["fields"]["invented_value"]["value"] == "primary"
    generation = api.generation()
    assert mdm_merge.execute(envelope,artifacts) == result and api.generation() == generation
elif case == "exact_values":
    raw = {"unknown":None,"empty":"","zero":0,"false":False,"integer":10**80+1,"unicode":"INVENTED 雪 💠 é"}
    incoming = g["record"]("one", revision=2, fields=raw)
    save(assertions=[incoming])
    fields = entity()["fields"]
    for key,value in raw.items():
        if value is None:
            assert key not in fields
        else:
            assert fields[key]["value"] == value and type(fields[key]["value"]) is type(value)
    retained = RecordReader._body(api.read([("source-reading",incoming["assertion_id"])],immutable=True)["source-reading",incoming["assertion_id"]])
    assert retained == incoming
elif case == "profiles_overrides_kind":
    policy = {**g["inactive"], "version":"invented-state-changes", "profile_fields":{
        "invented-role":{"invented_metric":{"sources":[g["PRIMARY"],g["SECONDARY"]]}}}}
    alternate = "invented-other-kind" if g["KIND"] == "invented-kind" else "invented-kind"
    policy["kinds"] = {**policy["kinds"], alternate:copy.deepcopy(policy["kinds"][g["KIND"]])}
    policy["kinds"][alternate]["rules"] = []
    with owner.begin() as conn:
        pin = register_policy(conn,policy)
    profile = {"role":"invented-role","authority":"invented-register","registration":"invented-one",
               "valid_from":g["AT"],"fields":{"invented_metric":10**80+2}}
    first = g["record"]("one",revision=2,profiles=[profile],fields={"invented_name":"INVENTED FIRST"})
    save(policy_digest=pin,assertions=[first])
    assert entity()["profiles"][0]["fields"]["invented_metric"]["value"] == 10**80+2
    save(policy_digest=pin,assertions=[g["record"]("one",revision=3,profiles=[{**profile,"fields":{"invented_metric":17}}])])
    assert entity()["profiles"][0]["fields"]["invented_metric"]["value"] == 17
    updated = g["record"]("one",revision=4,profiles=[],fields={"invented_name":"INVENTED SOURCE"})
    override = decision("override",actor="fixture",reason="invented reviewed override",at=g["AT"],
        subject=updated["subject"],field="invented_name",value="INVENTED STEWARD",evidence=[updated["assertion_id"]])
    save(policy_digest=pin,assertions=[updated],decisions=[override])
    assert entity()["profiles"] == [] and entity()["fields"]["invented_name"]["value"] == "INVENTED STEWARD"
    save(policy_digest=pin,decisions=[decision("revoke",actor="fixture",reason="invented override release",at="2026-02-01T00:00:00Z",target=override["decision_id"])])
    assert entity()["fields"]["invented_name"]["value"] == "INVENTED SOURCE"
    changed = g["record"]("one",revision=5,kind=alternate)
    save(policy_digest=pin,assertions=[changed])
    assert entity()["kind"] == g["KIND"]
    reviews = [RecordReader._body(row) for _,row in api.iter_type("review")]
    assert any(row["reason"] == "kind_conflict" for row in reviews)
else:
    raise AssertionError("Unknown installed boundary case")
print("normal installed boundary proof passed")
