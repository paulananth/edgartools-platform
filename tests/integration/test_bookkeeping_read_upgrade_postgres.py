"""Upgrade a populated historical control schema without changing its runs."""
import hashlib
from pathlib import Path
from uuid import uuid4

import edgar_control
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean.database import migrate
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.control_contract import canonical
from tests.support import pg16


def test_populated_run_metadata_gets_an_index_without_changing_frozen_content(monkeypatch):
    with pg16.server() as server:
        admin = create_engine(server.url("postgres", driver="postgresql"))
        owner = runtime = None
        try:
            with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.exec_driver_sql("CREATE DATABASE bookkeeping")
                conn.exec_driver_sql("CREATE ROLE read_proof_runtime LOGIN PASSWORD 'test' NOSUPERUSER NOCREATEDB NOCREATEROLE")
            owner = create_engine(server.url("bookkeeping", driver="postgresql"))
            runtime = create_engine(server.url("bookkeeping", "read_proof_runtime", driver="postgresql"))
            paths = sorted((Path(__file__).resolve().parents[2] /
                "edgar_warehouse/bookkeeping/clean/migrations").glob("[0-9]*.sql"))
            checksums = {}
            rid = str(uuid4())
            frozen = {"kind": "source", "name": "invented.source", "target": "reading",
                      "capture": "invented-capture", "integer": 10**50}
            with owner.begin() as conn:
                for path in paths:
                    if path.name >= "008":
                        continue
                    conn.execute(text(path.read_text()))
                    checksums[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
                conn.exec_driver_sql("COMMENT ON SCHEMA bookkeeping IS '" + canonical(checksums).replace("'", "''") + "'")
                conn.execute(text("INSERT INTO bookkeeping.pipeline_run(run_id,submission,submission_hash,expected_count) "
                                  "VALUES(CAST(:r AS uuid),CAST(:s AS jsonb),:h,0)"),
                             {"r": rid, "s": canonical(frozen), "h": "a" * 64})
            before = Bookkeeping(owner)._run(rid)
            saved = migrate(owner, runtime_role="read_proof_runtime", existing_only=True)
            assert "008_run_document_index.sql" in saved
            assert "009_native_run_checks.sql" in saved
            # Historical migration bytes must not depend on the current native
            # contract or routine generator when a future capability changes.
            from edgar_warehouse.bookkeeping.clean import run_storage
            def changed_generator(_):
                raise AssertionError("Applied migration regenerated from mutable code")
            monkeypatch.setattr(run_storage, "statements", changed_generator)
            assert migrate(owner, runtime_role="read_proof_runtime", existing_only=True) == saved
            assert Bookkeeping(runtime)._run(rid) == before
            with owner.begin() as conn:
                stored = conn.scalar(text("SELECT document_hash FROM bookkeeping.pipeline_run WHERE run_id=CAST(:r AS uuid)"), {"r": rid})
                assert bytes(stored).hex() == edgar_control.hash_text("source:invented.source:reading")
                assert conn.scalar(text("SELECT COUNT(*) FROM bookkeeping.work_item")) == 0
        finally:
            if runtime is not None:
                runtime.dispose()
            if owner is not None:
                owner.dispose()
            admin.dispose()
