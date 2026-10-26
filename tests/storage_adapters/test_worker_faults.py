"""Protocol-6 destination rollback and direct-call fencing guarantees."""
from dataclasses import replace
import json
import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from tests.storage_adapters.test_destination_authority import proof
from tests.storage_adapters.test_prepared_effects import batch


@pytest.mark.parametrize("case", ["late_expiry","held_transaction","invalid_wire"])
def test_worker_commit_faults(case,adapters,storage_api):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    owner,old,role = adapters
    storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=6)
    api = storage_api.Adapter(old.engine,prefix=old.prefix,protocol=6)
    original = batch(storage_api,governed=True,workflow=True,indexes=(),
        objects=(storage_api.Effect("invented","one",{"value":1}),))
    with owner.engine.begin() as conn:
        for name,value in original.pins.items():
            api.admit_pin(conn,name,value)
    lease = api.claim(original.scope,"invented-worker")
    api.apply(original,lease,proposal_body={"command":"invented-first"})
    request = replace(original,batch="invented-next",expected_generation=1,
        expected_checkpoint=1,checkpoint=2,
        objects=(storage_api.Effect("invented","one",{"value":2},expected_version=1),))
    def frame():
        with owner.engine.connect() as conn:
            return {name:list(conn.execute(select(table).order_by(*table.primary_key)))
                    for name,table in api.tables.items()}
    before = frame()
    if case == "late_expiry":
        target = api.engine.dialect.identifier_preparer.format_table(api.tables["current"])
        quote = api.engine.dialect.identifier_preparer.quote
        trigger = quote(api.prefix+"_delay")
        if api.engine.dialect.name == "postgresql":
            function = quote(api.schema)+"."+quote(api.prefix+"_delay_fn")
            create = [f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN PERFORM pg_sleep(1.2); RETURN NEW; END$$",
                      f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {target} FOR EACH ROW EXECUTE FUNCTION {function}()"]
            drop = f"DROP TRIGGER {trigger} ON {target}"
        else:
            create = [f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {target} FOR EACH ROW DO SLEEP(1.2)"]
            drop = f"DROP TRIGGER {trigger}"
        with owner.engine.begin() as conn:
            for statement in create: conn.exec_driver_sql(statement)
        try:
            with pytest.raises(storage_api.AdapterError,match="destination_authority_expired_before_save"):
                api.apply(request,lease,proposal_body={"command":"invented-next"},
                          authority=proof(api,micros=1000000))
        finally:
            with owner.engine.begin() as conn: conn.exec_driver_sql(drop)
    else:
        wire = {"intent":request.intent(),"observer":request.run.encode().hex(),
            "owner":lease.owner.encode().hex(),"fence":str(lease.fence),"expected_generation":"1",
            "proposal_body":storage_api.document({"command":"invented-next"}).hex(),
            "authority":storage_api.authority_wire(proof(api,micros=1000000))}
        name = api.routines["apply"][0]
        if case == "invalid_wire":
            for invalid in ([],{},[{"token":"1"}]):
                wire["authority"] = invalid
                with pytest.raises(DBAPIError),api.engine.begin() as conn:
                    sql = f"SELECT * FROM {name}(:wire)" if api.engine.dialect.name == "postgresql" else f"CALL {name}(:wire)"
                    conn.execute(text(sql),{"wire":json.dumps(wire)}).all()
                assert frame() == before
        else:
            with pytest.raises(DBAPIError),api.engine.begin() as conn:
                if api.engine.dialect.name == "postgresql":
                    conn.execute(text(f"SELECT * FROM {name}(:wire)"),{"wire":json.dumps(wire)}).all()
                    conn.execute(text("SELECT pg_sleep(1.2)"))
                else:
                    conn.execute(select(api.tables["gate"])).all()
                    conn.execute(text(f"CALL {name}(:wire)"),{"wire":json.dumps(wire)}).all()
    assert frame() == before and api.generation() == api.checkpoint(request.scope) == 1
    assert api.apply(request,lease,proposal_body={"command":"invented-next"},authority=proof(api))["changed"]


@pytest.mark.parametrize("case",["input_only","index_only"])
def test_worker_publication_boundary(case,adapters,storage_api):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    owner,old,role = adapters
    storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=6)
    api = storage_api.Adapter(old.engine,prefix=old.prefix,protocol=6)
    original = batch(storage_api,governed=True,workflow=True,indexes=(),publish_inputs=True,
        objects=(storage_api.Effect("invented","one",{"value":1}),))
    with owner.engine.begin() as conn:
        for name,value in original.pins.items():
            api.admit_pin(conn,name,value)
    lease = api.claim(original.scope,"invented-worker",authority=proof(api))
    api.apply(original,lease,proposal_body={"command":"invented-first"},authority=proof(api))
    before = api.read([("invented","one")])
    request = replace(original,batch="invented-next",expected_generation=1,objects=(),
        expected_checkpoint=1,checkpoint=2,
        evidence=original.evidence+((storage_api.Effect("invented-input","two",{"revision":2}),)
                                    if case == "input_only" else ()),
        indexes=(storage_api.IndexChange("invented-lookup","one",{"pointer":"opaque"}),)
                 if case == "index_only" else ())
    result = api.apply(request,lease,proposal_body={"command":"invented-next"},authority=proof(api))
    publications = api.read_batches([request.batch],outboxes=True)
    assert len(publications) == (len(request.consumers) if case == "input_only" else 0)
    assert result["changed"] == (case == "input_only") and api.read([("invented","one")]) == before
    assert api.replay(request.batch,lease,observer="invented-retry",authority=proof(api))["duplicate"]
    assert api.generation() == 2 and api.read_batches([request.batch],outboxes=True) == publications
