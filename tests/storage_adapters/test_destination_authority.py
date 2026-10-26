"""Commit-local worker fences on the first-priority storage engines."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from tests.storage_adapters.test_prepared_effects import batch, count

CASES = ["proof", "expired", "overtaken", "same_token_other_attempt", "late_expiry",
         "held_transaction", "input_publication", "indexes", "interrupted_upgrade", "rights", "invalid_wire"]
if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
    CASES = ["sql_server_deferred"]


def proof(runtime, *, token=1, micros=30_000_000):
    # Clock comes from the selected destination.
    from importlib import import_module
    package = runtime.__class__.__module__.rpartition(".")[0]
    SQL = import_module((package + "." if package else "") + "adapter_sql").SQL
    clock = SQL(runtime.engine.dialect,runtime.tables,protocol=4).now
    with runtime.engine.connect() as conn:
        epoch = int(conn.scalar(text("SELECT "+clock)))
    expires = datetime(1970,1,1,tzinfo=UTC)+timedelta(microseconds=epoch+micros)
    return [{"resource":"invented-resource","token":token,
             "run_id":"00000000-0000-0000-0000-000000000001",
             "attempt":"00000000-0000-0000-0000-000000000002","expires_at":expires.isoformat()}]


def snapshot(owner):
    return {name: count(owner,name) for name in ("current","history","evidence","outbox","batch")}


@pytest.mark.parametrize("case",CASES)
def test_destination_authority(case, adapters, storage_api):
    owner, runtime, role = adapters
    if case == "sql_server_deferred":
        with pytest.raises(storage_api.AdapterError,match="not yet qualified for SQL Server"):
            storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
        return
    original = batch(storage_api)
    lease = runtime.claim(original.scope,"writer")
    runtime.apply(original,lease)
    if case == "interrupted_upgrade":
        storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=3)
        before = snapshot(owner)
        def interrupt(conn,cursor,statement,params,context,many):
            if "authority_ready" in statement:
                raise RuntimeError("interrupted capability installation")
        event.listen(owner.engine,"before_cursor_execute",interrupt)
        try:
            with pytest.raises(RuntimeError,match="interrupted capability"):
                storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
        finally:
            event.remove(owner.engine,"before_cursor_execute",interrupt)
        with pytest.raises(storage_api.AdapterError,match="storage_not_initialized"):
            runtime.apply(original,lease)
        assert snapshot(owner) == before
    storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
    storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
    owner = storage_api.Adapter(owner.engine,prefix=owner.prefix,protocol=4)
    runtime = storage_api.Adapter(runtime.engine,prefix=runtime.prefix,protocol=4)
    assert runtime.apply(original,lease)["duplicate"]
    request = replace(original,batch="guarded",expected_generation=1,expected_checkpoint=1,checkpoint=2,
        objects=tuple(replace(obj,expected_version=1,body={"changed":True}) for obj in original.objects),indexes=())
    before = snapshot(owner)
    held = proof(runtime)
    if case in {"proof","interrupted_upgrade"}:
        assert runtime.apply(request,lease,authority=held)["changed"]
        assert runtime.apply(request,lease,authority=proof(runtime))["duplicate"]
        assert count(owner,"authority") == 1
    elif case == "expired":
        with pytest.raises(storage_api.AdapterError,match="expired_destination_authority"):
            runtime.apply(request,lease,authority=proof(runtime,micros=-1_000_000))
        assert snapshot(owner) == before and count(owner,"authority") == 0
    elif case in {"overtaken","same_token_other_attempt"}:
        runtime.apply(request,lease,authority=held)
        next_request = replace(request,batch="later",expected_generation=2,expected_checkpoint=2,checkpoint=3,objects=())
        if case == "overtaken":
            assert not runtime.apply(next_request,lease,authority=proof(runtime,token=2))["changed"]
            bad = held
        else:
            bad = [{**held[0],"attempt":str(uuid4())}]
        before = snapshot(owner)
        with pytest.raises(storage_api.AdapterError,match="stale_destination_authority"):
            runtime.apply(request,lease,authority=bad)
        assert snapshot(owner) == before
    elif case == "late_expiry":
        target = runtime.engine.dialect.identifier_preparer.format_table(runtime.tables["current"])
        quoted = runtime.engine.dialect.identifier_preparer.quote
        trigger = quoted(owner.prefix+"_delay")
        if runtime.engine.dialect.name == "postgresql":
            function = quoted(owner.schema)+"."+quoted(owner.prefix+"_delay_fn")
            statements = [f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN PERFORM pg_sleep(1.2); RETURN NEW; END$$",
                f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {target} FOR EACH ROW EXECUTE FUNCTION {function}()"]
            drop = f"DROP TRIGGER {trigger} ON {target}"
        else:
            statements = [f"CREATE TRIGGER {trigger} BEFORE UPDATE ON {target} FOR EACH ROW DO SLEEP(1.2)"]
            drop = f"DROP TRIGGER {trigger}"
        with owner.engine.begin() as conn:
            for statement in statements: conn.exec_driver_sql(statement)
        try:
            with pytest.raises(storage_api.AdapterError,match="destination_authority_expired_before_save"):
                runtime.apply(request,lease,authority=proof(runtime,micros=1_000_000))
        finally:
            with owner.engine.begin() as conn: conn.exec_driver_sql(drop)
        assert snapshot(owner) == before and count(owner,"authority") == 0
        assert runtime.generation() == runtime.checkpoint(request.scope) == 1
        assert runtime.apply(request,lease,authority=proof(runtime))["changed"]
    elif case == "held_transaction":
        # MySQL owns the commit and refuses an existing transaction. PostgreSQL
        # also rejects expiry deferred to a caller-controlled commit.
        held = proof(runtime,micros=1_000_000)
        expires = datetime.fromisoformat(held[0]["expires_at"])
        delta = expires-datetime(1970,1,1,tzinfo=UTC)
        wire = {"intent":request.intent(),"owner":lease.owner.encode().hex(),"fence":str(lease.fence),
            "expected_generation":"1","authority":[{"resource":held[0]["resource"].encode().hex(),"token":"1",
                "run":held[0]["run_id"].encode().hex(),"attempt":held[0]["attempt"].encode().hex(),
                "expires":str((delta.days*86400+delta.seconds)*1000000+delta.microseconds)}]}
        name = runtime.routines["apply"][0]
        with pytest.raises(DBAPIError),runtime.engine.begin() as conn:
            if runtime.engine.dialect.name == "postgresql":
                conn.execute(text(f"SELECT * FROM {name}(:wire)"),{"wire":json.dumps(wire)}).all()
                conn.execute(text("SELECT pg_sleep(1.2)"))
            else:
                conn.execute(select(runtime.tables["gate"])).all()
                conn.execute(text(f"CALL {name}(:wire)"),{"wire":json.dumps(wire)}).all()
        assert snapshot(owner) == before and count(owner,"authority") == 0
    elif case == "indexes":
        from adapter_sql import SQL, authority_checks
        offset = datetime.fromisoformat(held[0]["expires_at"])-datetime(1970,1,1,tzinfo=UTC)
        expires = (offset.days*86400+offset.seconds)*1000000+offset.microseconds
        resources = ["invented-resource"]+["invented-resource-"+str(n) for n in range(5000)]
        with owner.engine.begin() as conn:
            conn.execute(owner.tables["authority"].insert(), [{"resource_key":storage_api.key(resource),
                "resource_bytes":resource.encode(),"token":1,"run_bytes":held[0]["run_id"].encode(),
                "attempt_bytes":held[0]["attempt"].encode(),"expires":expires} for resource in resources])
            if runtime.engine.dialect.name == "postgresql": conn.exec_driver_sql("ANALYZE "+runtime.tables["authority"].fullname)
            else: conn.exec_driver_sql("ANALYZE TABLE "+runtime.tables["authority"].fullname)
        guard = SQL(runtime.engine.dialect,runtime.tables,protocol=4)
        checks,_ = authority_checks(guard)
        update = next(query for query in checks if query.startswith("UPDATE "))
        packet = {"authority":[{"resource":held[0]["resource"].encode().hex(),"token":"1",
            "run":held[0]["run_id"].encode().hex(),"attempt":held[0]["attempt"].encode().hex(),"expires":str(expires)}]}
        cast = "TEXT" if runtime.engine.dialect.name == "postgresql" else "CHAR"
        statement = update.replace("p_wire","CAST(:proof_wire AS "+cast+")")
        # Writes execute as the definer; the runtime deliberately has no direct UPDATE.
        with owner.engine.connect() as conn:
            prefix = "EXPLAIN (FORMAT JSON) " if runtime.engine.dialect.name == "postgresql" else "EXPLAIN FORMAT=JSON "
            plan = conn.execute(text(prefix+statement),{"proof_wire":json.dumps(packet)}).scalar()
        if isinstance(plan,str): plan = json.loads(plan)
        def nodes(value):
            if isinstance(value,dict):
                yield value
                for child in value.values(): yield from nodes(child)
            elif isinstance(value,list):
                for child in value: yield from nodes(child)
        if runtime.engine.dialect.name == "postgresql":
            accesses = [node for node in nodes(plan) if node.get("Relation Name") == runtime.tables["authority"].name and node.get("Node Type") != "ModifyTable"]
            assert accesses and all(node["Node Type"] in {"Index Scan","Index Only Scan","Tid Scan"} for node in accesses)
            assert all("Index Cond" in node or "TID Cond" in node for node in accesses)
        else:
            accesses = [node for node in nodes(plan) if node.get("table_name") == "c"]
            assert accesses and all(node.get("access_type") in {"ref","eq_ref","const"} for node in accesses)
            assert all(node.get("key") == "PRIMARY" for node in accesses)
        assert runtime.apply(request,lease,authority=proof(runtime))["changed"]
    elif case == "input_publication":
        request = replace(request,objects=(),publish_inputs=True,
            evidence=(storage_api.Effect("reading","invented-input",{"amount":10**80}),))
        assert runtime.apply(request,lease,authority=held)["changed"]
        assert count(owner,"outbox") == before["outbox"]+len(request.consumers)
        repeated = replace(request,batch="unchanged-input",expected_generation=2,expected_checkpoint=2,checkpoint=3)
        assert not runtime.apply(repeated,lease,authority=proof(runtime))["changed"]
        assert runtime.apply(request,lease,authority=proof(runtime))["duplicate"]
        assert count(owner,"outbox") == before["outbox"]+len(request.consumers)
    elif case == "rights":
        table = runtime.engine.dialect.identifier_preparer.format_table(runtime.tables["authority"])
        with pytest.raises(DBAPIError), runtime.engine.begin() as conn:
            conn.exec_driver_sql(f"DELETE FROM {table}")
        if runtime.engine.dialect.name == "mysql":
            with owner.engine.begin() as conn:
                conn.execute(text(f"GRANT UPDATE(token) ON {table} TO :role@'%'"),{"role":role})
            with pytest.raises(storage_api.AdapterError,match="direct storage column writes"):
                storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
            with owner.engine.begin() as conn:
                conn.execute(text(f"REVOKE UPDATE(token) ON {table} FROM :role@'%'"),{"role":role})
            storage_api.migrate(owner.engine,runtime_role=role,prefix=owner.prefix,protocol=4)
        assert runtime.apply(request,lease,authority=held)["changed"]
    elif case == "invalid_wire":
        for bad in ([],[held[0],held[0]],[{**held[0],"token":True}],[{**held[0],"token":2**63}]):
            with pytest.raises(storage_api.AdapterError): runtime.apply(request,lease,authority=bad)
        # Bypass Python validation: the destination itself must refuse malformed
        # proofs without admitting any part of the prepared business write.
        expires = datetime.fromisoformat(held[0]["expires_at"])-datetime(1970,1,1,tzinfo=UTC)
        valid = {"resource":held[0]["resource"].encode().hex(),"token":"1",
            "run":held[0]["run_id"].encode().hex(),"attempt":held[0]["attempt"].encode().hex(),
            "expires":str((expires.days*86400+expires.seconds)*1000000+expires.microseconds)}
        wire = {"intent":request.intent(),"owner":lease.owner.encode().hex(),"fence":str(lease.fence),
                "expected_generation":"1"}
        invalid = [None, {}, [], [valid,valid]]
        invalid += [[{**valid,field:value}] for field,value in (
            ("token","0"),("token","-1"),("token","true"),("token","9223372036854775808"),
            ("expires","0"),("resource",""),("resource","not-hex"),("run",""),("attempt",None))]
        invalid += [[{key:value for key,value in valid.items() if key != field}]
                    for field in valid]
        for bad in invalid:
            with pytest.raises(storage_api.AdapterError):
                runtime._rpc("apply",{**wire,"authority":bad})
            assert snapshot(owner) == before and count(owner,"authority") == 0
        malformed_publication = json.loads(request.intent())
        malformed_publication.update(version="4",publish_inputs="true")
        with pytest.raises(storage_api.AdapterError,match="invalid_input_publication"):
            runtime._rpc("apply",{**wire,"intent":json.dumps(malformed_publication)})
        assert snapshot(owner) == before and count(owner,"authority") == 0


# Captured from the committed pre-protocol-4 implementation (7ce5acbe),
# using the pinned SQLAlchemy compiler and invented schema/prefix.
# Protocol 4 was captured separately from merged main fd95de34 before the
# governed registry installation was added; SQL Server still defers it.
@pytest.mark.parametrize("engine,expected", [
    ("postgresql", ("08bd177086b94177a75f542a52e72158bf8f8f89e741bfbb721e3d5d9ad9ddf3",
                    "a7b48ad7d0eae0b9ad4e7ef31e8919421b031fe12b933fc106c3261dc9658a7a",
                    "e74b0a48a84d488425518c3e4af975b0e4341d9195f4e89e34ffe9bd8661533b",
                    "c5956454fdf8f02a453d13a5d615fecb8069ad56c4f98377fce8da593eda04ef")),
    ("mysql", ("aa3e6dd5ff01e752d7be38891aeb8b8a4b988a0227bfa849c5da8cf41ed3bba9",
               "8d04821d53724ba88136b6283177f778fd0fd05cdd2a3b0457fe067e50eed778",
               "26cf604355cf38f723d8147c48e9f5bdbe6028cc903e8b91cca4b95b7820f976",
               "4f426e9f62817ce047e135e49d32f7836a8f509b971e7d8c311af34cc33accb0")),
    ("mssql", ("77f851249b359c239a0beb57b2d13ab8dcd8231ba2874537a9b099796d941620",
               "dcc3e4347f45814c48e670499ee74974622a7befcff161099fa43b78a349f8fb",
               "0b243f03c34ac319c893f26b8049ecdbbd0ef9c59aa66a2e23bb3c5f22fa1515")),
])
def test_protocol_four_preserves_historical_migration_fingerprints(storage_api,engine,expected):
    from hashlib import sha256
    from types import SimpleNamespace
    from sqlalchemy.dialects import postgresql,mysql,mssql
    dialect = {"postgresql":postgresql,"mysql":mysql,"mssql":mssql}[engine].dialect()
    for protocol, fingerprint in enumerate(expected,1):
        metadata,tables = storage_api.model("fingerprint","fixture",protocol=protocol)
        build = SimpleNamespace(engine=SimpleNamespace(dialect=dialect),metadata=metadata,
            routines=storage_api.capabilities(dialect,tables,"fingerprint",protocol=protocol),
            commit_guards=storage_api.commit_guards(dialect,tables,"fingerprint"),
            migration_guards=storage_api.migration_guards(dialect,tables,"fingerprint") if protocol>=2 else [])
        assert sha256("\n".join(storage_api._migration_statements(build)).encode()).hexdigest() == fingerprint
