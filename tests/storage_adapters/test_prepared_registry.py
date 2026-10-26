"""Normal owner installation and approved references; not full workflow proof."""

import os
import json
import subprocess
import sys
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError

from edgar_warehouse.mdm.clean import catalog
from edgar_warehouse.mdm.clean.prepared_registry import mapping_pin, schema_pin
from edgar_warehouse.mdm.clean.store import Conflict, Store, digest, migrate, register_policy
from tests.storage_adapters.test_governed_mdm_storage import seed
from tests.storage_adapters.test_prepared_effects import batch


CASES = ["registration", "registration_rollback", "rerun", "legacy_refusal", "cli", "interrupted_registry"]
if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "postgresql":
    CASES.append("native_populated")
if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
    CASES = ["deferred"]


@pytest.mark.parametrize("case", CASES)
def test_prepared_owner_registry(case, database_factory, storage_api):
    with database_factory() as (owner, runtime, role):
        if case == "deferred":
            with pytest.raises(ValueError, match="PostgreSQL"):
                migrate(owner, application_role=role, prepared=True)
            return
        if case == "native_populated":
            from edgar_warehouse.mdm.clean.merge import MergeStage
            migrate(owner, application_role=role)
            _, pin, _, _ = seed(owner)
            command = {"batch_id": "invented-native", "run_id": str(uuid4()), "policy_digest": pin,
                       "consumer": "invented", "expected_checkpoint": 0, "checkpoint": 1,
                       "as_of": "2026-01-01T00:00:00Z"}
            stage = MergeStage(Store(runtime))
            stage.apply(**command)
            with pytest.raises(Conflict, match="Populated native"):
                migrate(owner, application_role=role, prepared=True)
            assert stage.apply(**command)["duplicate"]
            with owner.connect() as conn:
                assert storage_api.storage_version(conn) == 0
            return
        migrate(owner, application_role=role, prepared=True)
        if case == "cli":
            result = subprocess.run(
                [sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())",
                 "mdm", "migrate", "--application-role", role, "--prepared-store"],
                env={**os.environ, "MDM_DATABASE_URL": owner.url.render_as_string(hide_password=False)},
                capture_output=True, text=True, timeout=90,
            )
            assert result.returncode == 0, "prepared owner migration CLI failed"
            assert json.loads(result.stdout)["prepared_storage"] == 6
        policy, policy_key, first, second = seed(owner)
        api = storage_api.Adapter(runtime, prefix="mdm_store", protocol=6)
        pins = {"catalog": digest(catalog.CATALOG), "policy": policy_key,
                mapping_pin("invented.source", first[0]): digest(first[1]),
                schema_pin("invented.source", "1"): digest(["invented.source", "1"]),
                mapping_pin("invented.source", second[0]): digest(second[1]),
                schema_pin("invented.source", "2"): digest(["invented.source", "2"])}
        b = batch(storage_api, governed=True, workflow=True, pins=pins, indexes=(),
                  objects=(storage_api.Effect("invented-kind", "one", {"value": 1}),))
        lease = api.claim(b.scope, "invented-worker")
        body = {"command": "invented-approved-command"}
        if case == "registration_rollback":
            rejected = {**policy, "version": "invented-rolled-back"}
            with pytest.raises(RuntimeError), owner.begin() as conn:
                new_key = register_policy(conn, rejected)
                raise RuntimeError("invented interruption")
            with pytest.raises(storage_api.AdapterError, match="unregistered_frozen_pins"):
                api.apply(replace(b, pins={**pins, "policy": new_key}), lease,
                          proposal_body=body)
            with owner.connect() as conn:
                assert storage_api.registered_policy(conn, new_key) is None
            assert api.generation() == 0
            return
        if case == "legacy_refusal":
            with pytest.raises(ValueError, match="prepared owner installation"):
                migrate(owner, application_role=role)
            if owner.dialect.name == "postgresql":
                with pytest.raises(DBAPIError), runtime.begin() as conn:
                    conn.execute(text("SELECT mdm.save_batch('{}',CAST(:run AS uuid))"),
                                 {"run": str(uuid4())})
        api.apply(b, lease, proposal_body=body)
        if case == "interrupted_registry":
            interrupted = []

            def fail_after_pending(conn, cursor, statement, parameters, context, executemany):
                if (not interrupted and statement.lstrip().upper().startswith("UPDATE")
                        and "mdm_store_migration" in statement and "WHERE" in statement.upper()
                        and isinstance(parameters, dict) and parameters.get("complete") == 0):
                    interrupted.append(True)
                    raise RuntimeError("invented owner interruption")

            event.listen(owner, "after_cursor_execute", fail_after_pending)
            try:
                with pytest.raises(RuntimeError, match="invented owner interruption"):
                    migrate(owner, application_role=role, prepared=True)
            finally:
                event.remove(owner, "after_cursor_execute", fail_after_pending)
            assert interrupted
            with pytest.raises(storage_api.AdapterError):
                api.replay(b.batch, lease, observer="during-interruption")
            migrate(owner, application_role=role, prepared=True)
            assert api.replay(b.batch, lease, observer="after-recovery")["duplicate"]
        if case == "rerun":
            migrate(owner, application_role=role, prepared=True)
            assert api.replay(b.batch, lease, observer="after-rerun")["duplicate"]
        with runtime.connect() as conn:
            active = conn.execute(select(api.tables["pin"].c.value_bytes)
                                 .where(api.tables["pin"].c.active == 1)).all()
            assert len(active) == len(pins)
        assert api.generation() == 1
