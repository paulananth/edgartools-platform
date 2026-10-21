"""The normal journal caller uses the same native contract on every real engine."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.change_journal import ChangeJournal, JournalConflict, envelope
from edgar_warehouse.change_journal.database import migrate
from edgar_warehouse.change_journal import storage
from edgar_warehouse.control_contract import Blocked


def event(**changes):
    values=dict(producer="invented.producer", event_key="Invented clé "+uuid4().hex,
        run_id=str(uuid4()), source="invented.source", feed="invented.feed", event_type="work.verified",
        occurred_at=datetime.now(UTC).isoformat(),
        evidence=[{"uri":"s3://invented/retained", "sha256":"a"*64}])
    values.update(changes)
    return envelope(**values)


@pytest.fixture(scope="module")
def journal_database(database_factory):
    with database_factory() as value:
        yield value


@pytest.fixture
def journal(journal_database):
    owner,runtime,role=journal_database
    checksums=migrate(owner,runtime_role=role,database_name=owner.url.database)
    assert migrate(owner,runtime_role=role,database_name=owner.url.database,existing_only=True)==checksums
    return owner,runtime,role,ChangeJournal(runtime)


def test_real_caller_retries_conflicts_receipts_and_bounded_reads(journal):
    owner,runtime,role,journal=journal
    before=journal.status()["events"]
    value=event()
    first=journal.append(value)
    assert journal.append(deepcopy(value))==first
    assert journal.verify(first,expected=value)==first
    with pytest.raises(JournalConflict):journal.append({**value,"feed":"different.feed"})
    with pytest.raises(JournalConflict):journal.verify({**first,"id":first["id"]+1})
    assert journal.found(value["producer"],[value["event_key"],"absent"])=={value["event_key"]}
    assert journal.list(run_id=value["run_id"],limit=1)==[first]
    assert journal.list(run_id=value["run_id"].upper(),limit=1)==[first]
    assert journal.list(run_id=value["run_id"].replace("-", ""),limit=1)==[first]
    assert journal.list(after=first["id"])==[]
    assert journal.status()["events"]==before+1
    assert journal.get(value["producer"],"absent") is None
    for limit in [0,1001,True,-1]:
        with pytest.raises(ValueError):journal.list(limit=limit)
    for keys in [[True],["a"]*10001,"bad"]:
        with pytest.raises(ValueError):journal.found(value["producer"],keys)


def test_migration_refuses_runtime_capability_administration(journal):
    owner, runtime, role, journal = journal
    if owner.dialect.name != "mssql":
        # MySQL role/global grants and PostgreSQL inherited ownership have
        # different authorization models; no SQL Server-only grant is issued.
        return
    principal = owner.dialect.identifier_preparer.quote(role)
    cases = [
        (f"EXEC(N'USE master; GRANT CONTROL SERVER TO {principal}')",
         f"EXEC(N'USE master; REVOKE CONTROL SERVER FROM {principal}')"),
        (f"GRANT IMPERSONATE ON USER::dbo TO {principal}", f"REVOKE IMPERSONATE ON USER::dbo FROM {principal}"),
        (f"ALTER ROLE db_ddladmin ADD MEMBER {principal}", f"ALTER ROLE db_ddladmin DROP MEMBER {principal}"),
        (f"GRANT ALTER ON SCHEMA::journal TO {principal}", f"REVOKE ALTER ON SCHEMA::journal FROM {principal}"),
        (f"GRANT ALTER ON OBJECT::journal.record_event TO {principal}", f"REVOKE ALTER ON OBJECT::journal.record_event FROM {principal}"),
        (f"GRANT ALTER ON OBJECT::journal.event_records TO {principal}", f"REVOKE ALTER ON OBJECT::journal.event_records FROM {principal}"),
    ]
    receipt = journal.append(event())
    for grant, revoke in cases:
        with owner.begin() as conn:
            conn.exec_driver_sql(grant)
        try:
            with pytest.raises(Blocked, match="administer Journal"):
                migrate(owner, runtime_role=role, database_name=owner.url.database, existing_only=True)
        finally:
            with owner.begin() as conn:
                conn.exec_driver_sql(revoke)
        migrate(owner, runtime_role=role, database_name=owner.url.database, existing_only=True)
        assert journal.verify(receipt) == receipt


def test_concurrent_same_key_is_one_event_and_conflicting_content_has_one_winner(journal):
    owner,runtime,role,journal=journal
    before=journal.status()["events"]
    value=event()
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts=list(pool.map(lambda _:journal.append(value),range(12)))
    assert all(receipt==receipts[0] for receipt in receipts)
    other=event()
    def deliver(n):
        try:return journal.append({**other,"feed":f"invented.{n}"})
        except JournalConflict:return None
    with ThreadPoolExecutor(max_workers=6) as pool:receipts=list(pool.map(deliver,range(6)))
    assert sum(receipt is not None for receipt in receipts)==1
    assert journal.status()["events"]==before+2


def test_exact_keys_unicode_trailing_spaces_and_grouped_lookup(journal):
    owner,runtime,role,journal=journal
    before=journal.status()["events"]
    import random
    draw=random.Random(1234)
    long_key="".join(chr(draw.randrange(0x4e00,0x9fff)) for _ in range(2048))
    keys=[long_key,"a","A","a ","é","e\u0301","漢字 😀","😀"*2048]
    for key in keys:journal.append(event(event_key=key))
    assert journal.found("invented.producer",keys+['absent'])==set(keys)
    assert journal.status()["events"]==before+len(keys)
    for key in keys:assert journal.get("invented.producer",key)["event"]["event_key"]==key


def test_direct_writes_base_reads_and_bad_hash_are_rejected(journal):
    owner,runtime,role,journal=journal
    before=journal.status()["events"]
    value=event();receipt=journal.append(value)
    table=storage.event_table(runtime)
    name=runtime.dialect.identifier_preparer.format_table(table)
    for statement in [f"SELECT * FROM {name}",f"UPDATE {name} SET feed='bad'",f"DELETE FROM {name}",f"TRUNCATE TABLE {name}"]:
        with pytest.raises(DBAPIError),runtime.begin() as conn:conn.exec_driver_sql(statement)
    # Mutation guards protect existing history even through an owner connection.
    for statement in [f"UPDATE {name} SET feed='bad'",f"DELETE FROM {name}"]:
        with pytest.raises(DBAPIError),owner.begin() as conn:conn.exec_driver_sql(statement)
    from edgar_warehouse.control_contract import canonical
    with pytest.raises(DBAPIError):storage.record_event(runtime,canonical(event()),"b"*64)
    assert journal.status()["events"]==before+1 and journal.verify(receipt)==receipt
    with pytest.raises(Blocked):migrate(runtime,runtime_role=role,database_name=runtime.url.database)


def test_populated_migration_drift_interruption_and_recovery(journal):
    owner,runtime,role,journal=journal
    receipt=journal.append(event())
    kind=owner.dialect.name
    if kind=="postgresql":
        select_saved="SELECT obj_description(oid,'pg_namespace') FROM pg_namespace WHERE nspname='journal'"
        with owner.begin() as conn:
            saved=conn.scalar(text(select_saved))
            conn.exec_driver_sql("COMMENT ON SCHEMA journal IS '{\"001_event.sql\":\"bad\"}'")
        try:
            with pytest.raises(Blocked):migrate(owner,runtime_role=role,database_name=owner.url.database)
        finally:
            with owner.begin() as conn:conn.exec_driver_sql("COMMENT ON SCHEMA journal IS '"+saved.replace("'","''")+"'")
    else:
        table="journal_migrations" if kind=="mysql" else "journal.migrations"
        with owner.begin() as conn:
            saved=conn.scalar(text(f"SELECT checksum FROM {table} WHERE id=1"))
            conn.execute(text(f"UPDATE {table} SET checksum=:h WHERE id=1"),{"h":"b"*64})
        try:
            with pytest.raises(Blocked):migrate(owner,runtime_role=role,database_name=owner.url.database)
        finally:
            with owner.begin() as conn:conn.execute(text(f"UPDATE {table} SET checksum=:h,complete=0 WHERE id=1"),{"h":saved})
        with pytest.raises(Blocked,match="migration incomplete"):journal.append(event())
        with pytest.raises(Blocked,match="migration incomplete"):journal.get(receipt["event"]["producer"],receipt["event"]["event_key"])
    migrate(owner,runtime_role=role,database_name=owner.url.database,existing_only=True)
    assert journal.verify(receipt)==receipt


def test_postgres_populated_original_store_upgrades_without_rewriting_receipts(journal_database):
    owner,runtime,role=journal_database
    if owner.dialect.name!="postgresql":
        # Other engines have no earlier native Journal schema. Their populated
        # native upgrade/recovery path is exercised above on the same retained rows.
        return
    from pathlib import Path
    import hashlib,json
    from edgar_warehouse.change_journal import database as migrations
    from edgar_warehouse.control_contract import canonical
    with owner.begin() as conn:
        # This is a disposable proof database owned exclusively by this fixture.
        conn.exec_driver_sql("DROP SCHEMA IF EXISTS journal CASCADE")
        checksums={}
        for path in sorted((Path(migrations.__file__).parent/"migrations").glob("*.sql")):
            source=path.read_text();conn.execute(text(source));checksums[path.name]=hashlib.sha256(source.encode()).hexdigest()
        conn.exec_driver_sql("COMMENT ON SCHEMA journal IS '"+canonical(checksums).replace("'","''")+"'")
        value=event();body=canonical(value)
        original=conn.scalar(text("SELECT journal.append(:b,:h)"),{"b":body,"h":hashlib.sha256(body.encode()).hexdigest()})
    migrate(owner,runtime_role=role,database_name=owner.url.database,existing_only=True)
    journal=ChangeJournal(runtime)
    assert journal.get(value["producer"],value["event_key"])==original
    assert journal.append(value)==original


def test_grouped_lookup_uses_the_key_index_on_the_real_engine(journal):
    owner,runtime,role,journal=journal
    value=event();journal.append(value)
    query=storage.find_keys_statement(runtime,value["producer"],[value["event_key"],"absent"])
    with runtime.connect() as conn:
        compiled=query.compile(dialect=conn.dialect,compile_kwargs={"render_postcompile":True})
        sql=str(compiled);params=compiled.params
        if runtime.dialect.name=="postgresql":
            conn.exec_driver_sql("SET LOCAL enable_seqscan=off")
            plan="\n".join(conn.exec_driver_sql("EXPLAIN "+sql,params).scalars())
            assert "event_key_unique" in plan and "Seq Scan on event" not in plan,plan
        elif runtime.dialect.name=="mysql":
            with owner.connect() as inspection:
                plan=list(inspection.exec_driver_sql("EXPLAIN "+sql,params).mappings())
            assert any(row["key"]=="event_key_unique" for row in plan),plan
        else:
            # SHOWPLAN needs a narrowly granted inspection permission; the query
            # itself is still the runtime's actual indexed view statement.
            with owner.begin() as admin:
                role_sql=owner.dialect.identifier_preparer.quote(role)
                admin.exec_driver_sql(f"GRANT SHOWPLAN TO {role_sql}")
            conn.exec_driver_sql("SET SHOWPLAN_XML ON")
            try:
                plan=conn.exec_driver_sql(sql,params).scalar()
            finally:conn.exec_driver_sql("SET SHOWPLAN_XML OFF")
            assert "event_key_unique" in plan and 'PhysicalOp="Index Seek"' in plan, 'Grouped event lookup did not use a key seek'


def test_receipt_time_is_independent_of_the_reading_sessions_timezone(journal):
    owner,runtime,role,journal=journal
    first=journal.append(event())
    from sqlalchemy import create_engine
    kind=runtime.dialect.name
    settings=({"init_command":"SET time_zone = '+09:00'"} if kind=="mysql" else
              {"options":"-c timezone=America/New_York"} if kind=="postgresql" else {})
    alternate=create_engine(runtime.url,connect_args=settings,hide_parameters=True)
    try:
        reader=ChangeJournal(alternate)
        assert reader.get(first["event"]["producer"],first["event"]["event_key"])==first
        assert reader.verify(first)==first
    finally:alternate.dispose()
