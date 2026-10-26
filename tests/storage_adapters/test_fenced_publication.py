"""Publication order and worker authority through destination capabilities."""
from dataclasses import replace
import os

import pytest

from tests.storage_adapters.test_destination_authority import proof
from tests.storage_adapters.test_prepared_effects import batch


@pytest.mark.parametrize("case", ["authority", "order", "release", "expired_ack"])
def test_fenced_publication(case, adapters, storage_api):
    owner, runtime, role = adapters
    if os.environ.get("SKILL_ADAPTER_TEST_ENGINE") == "mssql":
        pytest.skip("Full SQL Server workflow remains deferred")
    storage_api.migrate(owner.engine, runtime_role=role, prefix=owner.prefix, protocol=6)
    api = storage_api.Adapter(runtime.engine, prefix=runtime.prefix, protocol=6)
    first = batch(storage_api, governed=True, workflow=True, objects=(storage_api.Effect("invented", "one", {}),))
    with owner.engine.begin() as conn:
        for name, value in first.pins.items():
            api.admit_pin(conn, name, value)
    lease = api.claim(first.scope, "invented-worker")
    api.apply(first, lease, proposal_body={"command":"invented","outcome":"ready"})
    consumer = first.consumers[0]
    if case == "authority":
        with pytest.raises(storage_api.AdapterError, match="expired_destination_authority"):
            api.claim_outbox(first.batch, consumer, "worker", authority=proof(api, micros=-1000000))
    held = api.claim_outbox(first.batch, consumer, "worker", authority=proof(api))
    assert held["payload"] == first.payload and held["fence"] == 1
    if case == "order":
        second = replace(first, batch="invented-next", expected_generation=1,
                         expected_checkpoint=1, checkpoint=2,
                         objects=(storage_api.Effect("invented", "one", {"changed":True}, expected_version=1),))
        api.apply(second, lease, proposal_body={"command":"invented-next","outcome":"ready"})
        with pytest.raises(storage_api.AdapterError, match="earlier_publication_pending"):
            api.claim_outbox(second.batch, consumer, "worker", authority=proof(api))
        api.ack_outbox(first.batch, consumer, "worker", held["fence"], held["payload_hash"], authority=proof(api))
        assert api.claim_outbox(second.batch, consumer, "worker", authority=proof(api)) is not None
        return
    if case == "release":
        api.release_outbox(first.batch, consumer, "worker", held["fence"], authority=proof(api))
        next_claim = api.claim_outbox(first.batch, consumer, "another-worker", authority=proof(api))
        assert next_claim["fence"] == 2 and next_claim["payload"] == held["payload"]
        with pytest.raises(storage_api.AdapterError, match="stale_or_invalid_publication_receipt"):
            api.ack_outbox(first.batch, consumer, "worker", held["fence"], held["payload_hash"], authority=proof(api))
        return
    if case == "expired_ack":
        with pytest.raises(storage_api.AdapterError, match="expired_destination_authority"):
            api.ack_outbox(first.batch, consumer, "worker", held["fence"], held["payload_hash"],
                           authority=proof(api, micros=-1000000))
    api.ack_outbox(first.batch, consumer, "worker", held["fence"], held["payload_hash"], authority=proof(api))
    assert api.claim_outbox(first.batch, consumer, "worker", authority=proof(api)) is None
    with pytest.raises(storage_api.AdapterError, match="expired_destination_authority"):
        api.claim_outbox(first.batch, consumer, "worker", authority=proof(api, micros=-1000000))
