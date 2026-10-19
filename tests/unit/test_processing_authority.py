"""Switching on the pipes is apart from switching on live acquisition (operator,
2026-10-19): a run over captured data needs the processing authority, a run
with a feed the acquisition authority too."""
import pytest

from edgar_warehouse.bookkeeping.clean.engine import _authority
from edgar_warehouse.control_contract import Blocked, digest
from edgar_warehouse.rules.acquisition_authority import registration_authority

FEED = {"family": "fixture", "datasets": ["fixture.v1"], "scope": ["fixture"],
        "capabilities": {"capture": "provider.capture", "fetch": "http.conditional"},
        "completeness": {"format": "json", "required": [], "allow_empty": True, "max_bytes": 1024},
        "required_producers": ["capture"], "url_prefixes": ["https://fixture.invalid/"]}
CONTRACT = {"family": "fixture"}


def export(proof=None, approved=True):
    body = {"source": "fixture", "acquisition": {"version": 1, "feeds": {"fixture": FEED}},
            "mdm": {"fixture.v1": {"contract": CONTRACT}}}
    content = digest(body)
    return {"kind": "source", "name": "fixture", "version": "1", "status": "active", "body": body,
            "digest": content, "proof": {"passed": True, "digest": content, **(proof or {})},
            "approval": {"digest": content, "by": "Operator", "at": "2026-10-19T12:00:00Z"} if approved else None}


def test_a_run_over_captured_data_needs_no_acquisition_proof():
    assert _authority(export(), {"source": "fixture"}, None)["digest"] == export()["digest"]


def test_a_run_with_a_feed_needs_the_acquisition_proof():
    with pytest.raises(Blocked, match="qualify every declared acquisition feed"):
        _authority(export(), {"source": "fixture", "feed": "fixture"}, None)
    proved = {"acquisition": {"fixture": {"manifest": {"uri": "file:///m.json", "sha256": "0" * 64},
                                          "counts": {"capture": {"expected": 1, "verified": 1}},
                                          "checks": {"complete": True}}}}
    assert _authority(export(proved), {"source": "fixture", "feed": "fixture"}, None)["feed"] == "fixture"


def test_a_dataset_registers_on_the_processing_authority():
    assert registration_authority(export(), "fixture.v1", CONTRACT)["rules"]["name"] == "fixture"


def test_neither_runs_without_the_operators_approval():
    with pytest.raises(Blocked, match="approval of the exact Rules version"):
        _authority(export(approved=False), {"source": "fixture"}, None)
