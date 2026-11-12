"""`bookkeeping migrate` on a store that holds runs: the current schema stays as it is, an earlier one is refused."""
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.database import migrate
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.control_contract import Blocked, canonical
from tests.support import pg16


def test_migrate_keeps_a_populated_current_store_and_refuses_an_earlier_schema():
    with pg16.server() as server:
        admin = create_engine(server.url("postgres", driver="postgresql"))
        owner = runtime = None
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("CREATE DATABASE bookkeeping")
                conn.exec_driver_sql("CREATE ROLE read_proof_runtime LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
            owner = create_engine(server.url("bookkeeping", driver="postgresql"))
            runtime = create_engine(server.url("bookkeeping", "read_proof_runtime", driver="postgresql"))
            saved = migrate(owner, runtime_role="read_proof_runtime")
            assert list(saved) == ["schema.sql"]
            rid = str(uuid4())
            frozen = {"kind": "source", "name": "invented.source", "target": "reading",
                      "capture": "invented-capture", "integer": 10**50}
            with owner.begin() as conn:
                conn.execute(text("INSERT INTO bookkeeping.pipeline_run(run_id,submission,submission_hash,expected_count) "
                                  "VALUES(CAST(:r AS uuid),CAST(:s AS jsonb),:h,0)"),
                             {"r": rid, "s": canonical(frozen), "h": "a" * 64})
            before = Bookkeeping(owner)._run(rid)
            assert migrate(owner, runtime_role="read_proof_runtime", existing_only=True) == saved
            assert Bookkeeping(runtime)._run(rid) == before
            with owner.begin() as conn:
                conn.exec_driver_sql("COMMENT ON SCHEMA bookkeeping IS '{\"001_control.sql\":\"" + "0" * 64 + "\"}'")
            with pytest.raises(Blocked, match="does not hold this build's schema; rebuild the store"):
                migrate(owner, runtime_role="read_proof_runtime", existing_only=True)
        finally:
            for engine in (runtime, owner, admin):
                if engine is not None:
                    engine.dispose()
