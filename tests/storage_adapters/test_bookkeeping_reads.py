"""Qualify the control read boundary, separately from transition support.

Only this fixture's disposable database is used. Owner-created invented rows
exercise the same read caller and native decisions on every selected engine;
they do not establish migration, lease-write or worker authorization support.
"""
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import edgar_control
import pytest
from sqlalchemy import Index, MetaData, PrimaryKeyConstraint, Text, Unicode, select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.bookkeeping.clean import storage
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.control_contract import Blocked


@pytest.fixture(scope="module")
def control_tables(database):
    owner, runtime, role = database
    kind = owner.dialect.name
    metadata = MetaData(schema=None if kind == "mysql" else "bookkeeping")
    models = {name: table.to_metadata(metadata) for name, table in storage.tables(kind).items()}
    keys = {"pipeline_run": ("run_id",), "work_item": ("run_id", "step", "unit_key"),
            "lease": ("resource",), "checkpoint": ("run_id", "scope"),
            "journal_outbox": ("event_id",)}
    for name, key in keys.items():
        for field in key:
            if isinstance(models[name].c[field].type, Text):
                models[name].c[field].type = Unicode(180)
        models[name].append_constraint(PrimaryKeyConstraint(*key))
    run = models["pipeline_run"]
    Index("run_document_lookup", run.c.document_hash, run.c.created_at, run.c.run_id)
    checkpoint = models["checkpoint"]
    checkpoint.c.resource.type = Unicode(180)
    Index("one_resource_checkpoint", checkpoint.c.resource, unique=True,
          postgresql_where=checkpoint.c.resource.is_not(None),
          mssql_where=checkpoint.c.resource.is_not(None))
    with owner.begin() as conn:
        if kind != "mysql":
            conn.exec_driver_sql("CREATE SCHEMA bookkeeping")
        metadata.create_all(conn)
        quote = conn.dialect.identifier_preparer
        principal = f"'{role}'@'%'" if kind == "mysql" else quote.quote(role)
        if kind == "postgresql":
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA bookkeeping TO {principal}")
        for table in models.values():
            conn.execute(text(f"GRANT SELECT ON {quote.format_table(table)} TO {principal}"))
    try:
        yield owner, runtime, models
    finally:
        with owner.begin() as conn:
            metadata.drop_all(conn)
            if kind != "mysql":
                conn.exec_driver_sql("DROP SCHEMA bookkeeping")


def add_run(owner, models, *, name=None, capture="invented-capture", state="complete", at=None):
    rid = str(uuid4())
    name = name or "invented." + uuid4().hex
    at = at or datetime.now(UTC)
    body = {"kind": "source", "name": name, "target": "reading", "capture": capture,
            "large": 10**50, "nullable": None, "empty": ""}
    document_hash = bytes.fromhex(edgar_control.hash_text(f"source:{name}:reading"))
    with owner.begin() as conn:
        conn.execute(models["pipeline_run"].insert(), dict(
            run_id=rid, submission=body, submission_hash="a" * 64, expected_count=3,
            state=state, checks={}, summary={}, pinned=False, created_at=at,
            completed_at=at if state == "complete" else None, runtimes={},
            document_hash=document_hash))
    return rid, name


def add_work(owner, models, rid, *, key, ordinal, state="pending", attempt=None, receipt=None):
    with owner.begin() as conn:
        conn.execute(models["work_item"].insert(), dict(
            run_id=rid, step="read", unit_key=key, ordinal=ordinal,
            state=state, attempt=attempt, attempts=1 if attempt else 0,
            resources=["invented.resource"], unit={"input": {}, "cursor": {}},
            checks={}, receipt=receipt, candidate=receipt))


def test_real_typed_reads_preserve_uuid_json_values_and_bounded_status(control_tables):
    owner, runtime, models = control_tables
    rid, name = add_run(owner, models, state="running")
    add_work(owner, models, rid, key="a", ordinal=0)
    add_work(owner, models, rid, key="b", ordinal=1, state="reported")
    add_work(owner, models, rid, key="c", ordinal=2, state="verified")
    book = Bookkeeping(runtime)
    row = book._run(rid)
    assert row["run_id"] == rid
    assert row["submission"]["large"] == 10**50
    assert row["submission"]["nullable"] is None and row["submission"]["empty"] == ""
    assert "document_hash" not in row
    state = book.status(rid, limit=1)
    assert len(state["items"]) == 1
    assert state["counts"] == {"pending": 1, "reported": 1, "verified": 1}
    assert any(row["run_id"] == rid for row in book.runs(state="running"))
    assert storage.reported(runtime, rid, [], 10) == []
    assert storage.reported(runtime, rid, ["read"], 1)[0]["unit_key"] == "b"
    assert storage.available_keys(runtime, rid, "read", 1) == ["a"]
    # Reads use the restricted role; granting a read boundary gives no write authority.
    with pytest.raises(DBAPIError), runtime.begin() as conn:
        conn.execute(models["pipeline_run"].update().where(models["pipeline_run"].c.run_id == rid).values(state="complete"))


def test_real_available_work_observes_server_clock_and_live_attempt(control_tables):
    owner, runtime, models = control_tables
    rid, _ = add_run(owner, models, state="running")
    attempt = str(uuid4())
    add_work(owner, models, rid, key="leased", ordinal=0, state="running", attempt=attempt)
    resource = "invented." + uuid4().hex
    lease = models["lease"]
    with owner.begin() as conn:
        conn.execute(lease.insert(), dict(resource=resource, token=1, run_id=rid, attempt=attempt,
                     expires_at=datetime.now(UTC) + timedelta(hours=1)))
    assert storage.available_keys(runtime, rid, "read", 10) == []
    with owner.begin() as conn:
        conn.execute(lease.update().where(lease.c.resource == resource).values(
            expires_at=datetime.now(UTC) - timedelta(hours=1)))
    assert storage.available_keys(runtime, rid, "read", 10) == ["leased"]


def test_real_latest_capture_uses_all_its_runs_and_never_an_old_rerun(control_tables):
    owner, runtime, models = control_tables
    at = datetime(2026, 1, 1, tzinfo=UTC)
    first, name = add_run(owner, models, capture="older", at=at)
    second, _ = add_run(owner, models, name=name, capture="newer", at=at + timedelta(days=1))
    third, _ = add_run(owner, models, name=name, capture="older", at=at + timedelta(days=2))
    fourth, _ = add_run(owner, models, name=name, capture="newer", at=at + timedelta(days=3))
    for n, rid in enumerate((first, second, third, fourth)):
        add_work(owner, models, rid, key="invented", ordinal=0, state="verified",
                 receipt={"uri": "s3://invented/output", "sha256": str(n + 1) * 64})
    # A repeated output within the newest capture is represented once, by its earliest completion.
    add_work(owner, models, fourth, key="duplicate", ordinal=1, state="verified",
             receipt={"uri": "s3://invented/output", "sha256": "2" * 64})
    book = Bookkeeping(runtime)
    selected = book.verified_units(source=name, target="reading", step="read")
    assert [unit["run"] for unit in selected] == [second, fourth]
    assert book.verified_units(source=name, target="reading", step="read", kind="pipeline") == []
    run = models["pipeline_run"]
    with owner.begin() as conn:
        conn.execute(run.update().where(run.c.run_id == fourth).values(state="waiting"))
    with pytest.raises(Blocked, match="1 runs not finished"):
        book.verified_units(source=name, target="reading", step="read")
    with owner.begin() as conn:
        conn.execute(run.update().where(run.c.run_id == fourth).values(
            state="complete", compacted_at=at + timedelta(days=4)))
    with pytest.raises(Blocked, match="1 compacted"):
        book.verified_units(source=name, target="reading", step="read")


def test_real_capture_metadata_uses_its_document_index(control_tables):
    owner, runtime, models = control_tables
    _, name = add_run(owner, models)
    statement = storage.capture_runs_statement(runtime, kind="source", source=name, target="reading")
    assert_index_seek(owner, runtime, statement, "run_document_lookup")


def assert_index_seek(owner, runtime, statement, index_name=None):
    compiled = statement.compile(dialect=runtime.dialect, compile_kwargs={"render_postcompile": True})
    sql = str(compiled)
    params = {key: compiled._bind_processors[key](value) if key in compiled._bind_processors else value
              for key, value in compiled.params.items()}
    with owner.connect() as conn:
        if owner.dialect.name == "postgresql":
            conn.exec_driver_sql("SET LOCAL enable_seqscan=off")
            plan = "\n".join(conn.exec_driver_sql("EXPLAIN " + sql, params).scalars())
            assert "Index" in plan and "Seq Scan" not in plan
            assert index_name is None or index_name in plan
        elif owner.dialect.name == "mysql":
            plan = list(conn.exec_driver_sql("EXPLAIN " + sql, params).mappings())
            assert any((index_name is None or row["key"] == index_name)
                       and row["type"] in ("const", "ref", "eq_ref") for row in plan), plan
        else:
            conn.exec_driver_sql("SET SHOWPLAN_XML ON")
            try:
                plan = conn.exec_driver_sql(sql, params).scalar()
            finally:
                conn.exec_driver_sql("SET SHOWPLAN_XML OFF")
            from xml.etree import ElementTree
            xml = ElementTree.fromstring(plan)
            assert "Index Seek" in plan, [node.attrib for node in xml.iter()
                if node.tag.endswith(("RelOp", "PlanAffectingConvert"))]
            assert index_name is None or index_name in plan


def test_exact_resource_and_work_lookups_keep_index_seeks(control_tables):
    owner, runtime, models = control_tables
    rid, _ = add_run(owner, models)
    key = "invented-clé "
    add_work(owner, models, rid, key=key, ordinal=0)
    checkpoint = models["checkpoint"]
    with owner.begin() as conn:
        conn.execute(checkpoint.insert(), dict(run_id=rid, scope="read", resource=key,
                     ordinal=0, revision=1, cursor={}, receipt={}))
    assert storage.checkpoint(runtime, key)[0]["resource"] == key
    assert storage.checkpoint(runtime, key.rstrip()) == []
    stored = storage.tables(runtime.dialect.name)
    checkpoint, work = stored["checkpoint"], stored["work_item"]
    checkpoint_read = select(checkpoint).where(storage.text_equal(runtime, checkpoint.c.resource, key))
    if runtime.dialect.name == "mssql":
        checkpoint_read = checkpoint_read.with_hint(checkpoint, "WITH (FORCESEEK)", "mssql")
    assert_index_seek(owner, runtime, checkpoint_read, "one_resource_checkpoint")
    assert_index_seek(owner, runtime, select(work).where(work.c.run_id == rid,
        storage.text_equal(runtime, work.c.step, "read"), storage.text_equal(runtime, work.c.unit_key, key)))


def test_long_capture_and_document_names_and_unicode_keys_are_retained(control_tables):
    owner, runtime, models = control_tables
    name = "invented." + "x" * 5000 + uuid4().hex
    capture = "invented-capture-" + "c" * 5000
    rid, _ = add_run(owner, models, name=name, capture=capture)
    key = "invented-clé-漢字-😀"
    add_work(owner, models, rid, key=key, ordinal=0, state="verified",
             receipt={"uri": "s3://invented/output", "sha256": "a" * 64})
    assert storage.capture_runs(runtime, kind="source", source=name, target="reading")[0]["capture"] == capture
    assert Bookkeeping(runtime).verified_units(source=name, target="reading", step="read") == [
        {"run": rid, "step": "read", "key": key, "sha256": "a" * 64}]


def test_original_work_keys_are_exact_under_default_collations(control_tables):
    owner, runtime, models = control_tables
    for key, other in [("A", "a"), ("é", "e"), ("a ", "a"), ("é", "e\u0301")]:
        rid, _ = add_run(owner, models)
        add_work(owner, models, rid, key=key, ordinal=0)
        assert storage.work(runtime, rid, step="read", key=key)[0]["unit_key"] == key
        assert storage.work(runtime, rid, step="read", key=other) == []


def test_capture_outputs_and_metadata_share_one_observation_set(control_tables, monkeypatch):
    owner, runtime, models = control_tables
    rid, name = add_run(owner, models)
    add_work(owner, models, rid, key="invented", ordinal=0, state="verified",
             receipt={"sha256": "a" * 64})
    original = storage.verified_units
    entered = Event()

    def compact():
        entered.set()
        with owner.begin() as conn:
            run, work = models["pipeline_run"], models["work_item"]
            conn.execute(run.update().where(run.c.run_id == rid).values(compacted_at=datetime.now(UTC)))
            conn.execute(work.delete().where(work.c.run_id == rid))

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = []

        def between_reads(*args, **kwargs):
            future = pool.submit(compact)
            pending.append(future)
            assert entered.wait(5)
            if owner.dialect.name != "mssql":
                future.result(timeout=5)
            return original(*args, **kwargs)

        monkeypatch.setattr(storage, "verified_units", between_reads)
        assert Bookkeeping(runtime).verified_units(source=name, target="reading", step="read") == [
            {"run": rid, "step": "read", "key": "invented", "sha256": "a" * 64}]
        pending[0].result(timeout=5)
    with pytest.raises(Blocked, match="1 compacted"):
        Bookkeeping(runtime).verified_units(source=name, target="reading", step="read")
