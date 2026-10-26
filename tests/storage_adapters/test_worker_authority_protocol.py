"""New authority parameters fail closed on older storage capabilities."""
import pytest


@pytest.mark.parametrize("operation",["claim_outbox","ack_outbox","record_proposal","supersede_proposal"])
def test_older_protocol_refuses_new_authority(operation,storage_api):
    api = object.__new__(storage_api.Adapter)
    api.protocol = 5
    # No engine is supplied: unsupported authority must refuse before any RPC.
    authority = [{"resource":"invented","token":1,
        "run_id":"00000000-0000-0000-0000-000000000001",
        "attempt":"00000000-0000-0000-0000-000000000002",
        "expires_at":"2099-01-01T00:00:00+00:00"}]
    with pytest.raises(storage_api.AdapterError,match="authority"):
        if operation == "claim_outbox":
            api.claim_outbox("invented","invented","invented",authority=authority)
        elif operation == "ack_outbox":
            api.ack_outbox("invented","invented","invented",1,"1"*64,authority=authority)
        elif operation == "record_proposal":
            api.record_proposal("invented",{},"invented",outcome="rejected",expected_generation=0,authority=authority)
        else:
            api.supersede_proposal("1"*64,"invented",authority=authority)
