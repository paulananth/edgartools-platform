"""Configured vocabulary reaches normal PostgreSQL merge and destination checks."""
import copy
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import catalog, schema, store
from edgar_warehouse.rules import files
from tests.integration import test_clean_mdm_postgres as core


def test_populated_kind_constraint_upgrade_preserves_business_rows(database, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(store, "MIGRATIONS", tuple(p for p in store.MIGRATIONS if p != "024_configured_kinds.sql"))
        patch.setattr(schema, "configure_kinds", lambda conn: None)
        old = core.initialize_database(database.admin, database.application)
        item = core.source("invented-existing", fields={"name": "Invented Existing"})
        identity, binding = core.identity_and_binding(item)
        core.apply(old, 1, assertions=[item], identities=[identity], decisions=[binding])
    before = core.documents(old, "entity")
    with database.application.connect() as conn:
        counts = {name: conn.scalar(text("SELECT count(*) FROM mdm." + name))
                  for name in ("source_reading", "master_entity", "current_record", "outbox", "batch")}
    # Hold the same first lock as save_batch. The upgrade must wait on that
    # advisory lock before taking any master table DDL lock.
    with ThreadPoolExecutor(max_workers=1) as pool:
        with database.admin.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(730234)"))
            holder = conn.scalar(text("SELECT pg_backend_pid()"))
            upgrade = pool.submit(store.migrate, database.admin, application_role="clean_application")
            deadline = time.monotonic() + 5
            blocked = []
            while not blocked and time.monotonic() < deadline:
                blocked = conn.execute(text("""SELECT l.locktype FROM pg_locks l
                    WHERE l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
                    AND NOT l.granted
                    AND :holder=ANY(pg_blocking_pids(l.pid))"""), {"holder": holder}).scalars().all()
                if not blocked: time.sleep(0.01)
            conn.execute(text("SET LOCAL lock_timeout='500ms'"))
            assert conn.scalar(text("SELECT count(*) FROM mdm.master_entity")) == 1
        upgrade.result(timeout=15)
    assert blocked == ["advisory"]
    store.migrate(database.admin, application_role="clean_application")
    assert core.documents(old, "entity") == before
    with database.application.connect() as conn:
        assert {name: conn.scalar(text("SELECT count(*) FROM mdm." + name)) for name in counts} == counts
        assert set(conn.scalars(text("SELECT kind FROM mdm.master_kind WHERE enabled"))) == set(catalog.CATALOG["kinds"])
        assert conn.scalar(text("""SELECT count(*) FROM pg_constraint
            WHERE conrelid='mdm.master_entity'::regclass AND conname='master_entity_kind_fkey'""")) == 1


def test_invented_kind_is_merged_replayed_and_read_without_engine_edits(database, tmp_path):
    shutil.copytree(files.ROOT, tmp_path, dirs_exist_ok=True)
    body = copy.deepcopy(catalog.CATALOG)
    body["kinds"].append("invented_kind")
    target = tmp_path / catalog.RELATIVE
    target.write_text(files.dumps(body))
    definitions_path = tmp_path / "context/definitions.yaml"
    definitions = files.load(definitions_path)
    definitions["kinds"]["invented_kind"] = "Invented configured master kind."
    definitions_path.write_text(files.dumps(definitions))
    program = '''
import os
from sqlalchemy import create_engine, text
from tests.integration import test_clean_mdm_postgres as core
from edgar_warehouse.mdm.clean.store import migrate, register_policy
owner = create_engine(os.environ["KIND_TEST_OWNER_URL"])
runtime = create_engine(os.environ["KIND_TEST_RUNTIME_URL"])
try:
    migrate(owner, application_role="clean_application")
    with owner.begin() as conn:
        policy = register_policy(conn, {"version":1,"required_consumers":["export","graph"],"automatic_rules":[],
            "fields":{"invented_kind":{"name":{"sources":["fixture.primary","fixture.secondary"]}}}})
    db = core.Database(owner,runtime,policy,"")
    item = core.source("invented-record",kind="invented_kind",fields={"name":"Invented Label"})
    identity,binding = core.identity_and_binding(item)
    run = "00000000-0000-0000-0000-000000000999"
    first = core.apply(db,1,run_id=run,assertions=[item],identities=[identity],decisions=[binding])
    before = core.documents(db,"entity")
    assert before[identity["entity_id"]]["kind"] == "invented_kind"
    assert before[identity["entity_id"]]["fields"]["name"]["value"] == "Invented Label"
    again = core.apply(db,1,run_id=run,assertions=[item],identities=[identity],decisions=[binding])
    assert again == {**first,"duplicate":True}
    assert core.documents(db,"entity") == before
    import io, json
    from contextlib import redirect_stdout
    from edgar_warehouse.cli import main
    output = io.StringIO()
    with redirect_stdout(output):
        assert main(["context","invented_kind",identity["entity_id"]]) == 0
    answer = json.loads(output.getvalue())
    assert answer["kind"] == "invented_kind"
    assert answer["definition"] == "Invented configured master kind."
    with runtime.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.invented_kind_stage")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.invented_kind_master")) == 1
        assert conn.scalar(text("SELECT count(*) FROM mdm.invented_kind_master_field")) == 1
finally:
    owner.dispose(); runtime.dispose()
'''
    result = subprocess.run([sys.executable, "-c", program], env={**os.environ,
        "EDGAR_RULES_ROOT": str(tmp_path),
        "MDM_DATABASE_URL": database.application.url.render_as_string(hide_password=False),
        "MDM_APPLICATION_ROLE": "clean_application",
        "KIND_TEST_OWNER_URL": database.admin.url.render_as_string(hide_password=False),
        "KIND_TEST_RUNTIME_URL": database.application.url.render_as_string(hide_password=False)},
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    # The original configuration disables the added kind without deleting its
    # historical identity or views. Destination enforcement refuses new ones.
    store.migrate(database.admin, application_role="clean_application")
    with database.application.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM mdm.invented_kind_master")) == 1
        assert conn.scalar(text("SELECT enabled FROM mdm.master_kind WHERE kind='invented_kind'")) is False
    with pytest.raises(DBAPIError, match="not enabled"), database.admin.begin() as conn:
        conn.execute(text("INSERT INTO mdm.master_entity VALUES(:id,'invented_kind',now(),'invented-batch')"), {"id": str(uuid4())})
    for statement in ("UPDATE mdm.master_kind SET enabled=true WHERE kind='invented_kind'",
                      "INSERT INTO mdm.master_kind VALUES('forged',true)",
                      "DELETE FROM mdm.master_kind WHERE kind='invented_kind'"):
        with pytest.raises(DBAPIError, match="permission denied"), database.application.begin() as conn:
            conn.execute(text(statement))
