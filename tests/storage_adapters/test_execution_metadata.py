"""Opaque durable run metadata, independent of business projections."""
import os

import pytest

from tests.storage_adapters.test_destination_authority import proof


@pytest.mark.parametrize("case", ["immutable", "cas", "expired", "rights"])
def test_execution_metadata(case, adapters, storage_api):
    owner, runtime, role = adapters
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=6)
    runtime = storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=6)
    body = '{"invented":"雪","amount":' + str(10**80 + 1) + '}'
    if case == "expired":
        with pytest.raises(storage_api.AdapterError, match="expired_destination_authority"):
            runtime.retain_metadata("invented", "one", body, authority=proof(runtime, micros=-1000000))
        assert runtime.read([("invented", "one")], metadata=True) == {}
        return
    immutable = case == "immutable"
    assert runtime.retain_metadata("invented", "one", body, immutable=immutable) == 1
    assert runtime.retain_metadata("invented", "one", body, immutable=immutable) == 1
    held = runtime.read([("invented", "one")], metadata=True)["invented", "one"]
    assert held["body"] == body.encode() and held["version"] == 1
    if immutable:
        with pytest.raises(storage_api.AdapterError, match="immutable_metadata_changed"):
            runtime.retain_metadata("invented", "one", '{}', immutable=True, expected_version=1)
    elif case == "cas":
        with pytest.raises(storage_api.AdapterError, match="stale_metadata_version"):
            runtime.retain_metadata("invented", "one", '{}')
        assert runtime.retain_metadata("invented", "one", '{}', expected_version=1) == 2
    elif case == "rights":
        from sqlalchemy import insert
        from sqlalchemy.exc import DBAPIError
        with pytest.raises(DBAPIError), runtime.engine.begin() as conn:
            conn.execute(insert(runtime.tables["metadata"]).values(type_key="1"*64, id_key="2"*64,
                type_bytes=b"invented", id_bytes=b"invented", body=b"{}", body_hash="3"*64,
                version=1, immutable=0, recorded_at=1))
    assert runtime.generation() == 0
