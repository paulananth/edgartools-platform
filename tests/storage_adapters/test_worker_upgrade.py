"""Populated owner upgrade preserves original data and closes interrupted writes."""
from dataclasses import replace
import os
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from edgar_warehouse.mdm.clean import catalog, prepared_registry
from edgar_warehouse.mdm.clean.prepared_runs import waiting
from edgar_warehouse.mdm.clean.store import digest, migrate
from tests.storage_adapters.test_governed_mdm_storage import seed
from tests.storage_adapters.test_prepared_effects import batch


@pytest.mark.parametrize("interrupt", [False,True])
def test_populated_worker_upgrade(interrupt,database_factory,storage_api):
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    with database_factory() as (owner,runtime,role):
        # Historical owner installation, without the index introduced in 6.
        with patch.object(prepared_registry,"PROTOCOL",5), patch.object(prepared_registry,"finish_indexes"):
            migrate(owner,application_role=role,prepared=True)
        _,pin,_,_ = seed(owner)
        five = storage_api.Adapter(runtime,prefix="mdm_store",protocol=5)
        request = batch(storage_api,governed=True,indexes=(),
            pins={"catalog":digest(catalog.CATALOG),"policy":pin},
            objects=tuple(storage_api.Effect("review","invented-waiting-"+str(n),{"waiting_for_end":True})
                          for n in range(201)))
        lease = five.claim(request.scope,"invented-worker")
        five.apply(request,lease,proposal_body={"command":"invented-previous"})
        def frame():
            with owner.connect() as conn:
                return {name:list(conn.execute(select(five.tables[name]).order_by(*five.tables[name].primary_key)))
                        for name in ("current","history","batch","evidence","outbox","checkpoint")}
        before = frame()
        if interrupt:
            def fail(conn,cursor,statement,params,context,many):
                if statement.lstrip().upper().startswith("CREATE") and "_retain_metadata" in statement:
                    raise RuntimeError("invented worker upgrade interruption")
            event.listen(owner,"before_cursor_execute",fail)
            try:
                with pytest.raises(RuntimeError,match="invented worker upgrade interruption"):
                    migrate(owner,application_role=role,prepared=True)
            finally:
                event.remove(owner,"before_cursor_execute",fail)
            with pytest.raises(storage_api.AdapterError):
                five.replay(request.batch,lease,observer="invented-interrupted")
            assert frame() == before
        migrate(owner,application_role=role,prepared=True)
        six = storage_api.Adapter(runtime,prefix="mdm_store",protocol=6)
        assert six.generation() == 1 and frame() == before
        with runtime.connect() as conn:
            count, rows = waiting(six,conn)
            assert count == 201 and len(rows) == 100
        assert six.replay(request.batch,lease,observer="invented-after-upgrade")["duplicate"]
        assert frame() == before
        stale = replace(request,batch="invented-old-writer",expected_generation=1,
                        expected_checkpoint=1,checkpoint=2,objects=())
        with pytest.raises(storage_api.AdapterError,match="unsupported_request_version"):
            five.apply(stale,lease,proposal_body={"command":"invented-old-writer"})
        assert frame() == before
        migrate(owner,application_role=role,prepared=True)
        assert frame() == before
