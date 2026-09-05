"""Change-propagation Ticket 50: the ordinary `mdm mastering` side of the
mdm_resolution lease. Deliberately asymmetric with the backstop (see
lease.py's module docstring) -- ordinary resolution always proceeds, even
when it cannot acquire the lease, since it has no "next slot" the way the
monthly backstop does.
"""
from __future__ import annotations

from edgar_warehouse.mdm.cli import _run_all_with_ordinary_lease
from edgar_warehouse.mdm.lease import acquire_mdm_pipeline_lease, get_mdm_pipeline_lease


class _StubPipeline:
    def __init__(self):
        self.calls = 0

    def run_all(self, **kwargs):
        self.calls += 1
        return {"kwargs": kwargs}


def test_proceeds_and_acquires_the_lease_when_free(db_session):
    pipeline = _StubPipeline()

    result = _run_all_with_ordinary_lease(pipeline, db_session, run_id="run-1", limit=None)

    assert pipeline.calls == 1
    assert result == {"kwargs": {"run_id": "run-1", "limit": None}}
    row = get_mdm_pipeline_lease(db_session)
    assert row.status == "idle"


def test_proceeds_even_when_a_backstop_pass_holds_the_lease(db_session):
    acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="backstop-1", stale_after_seconds=3600
    )
    pipeline = _StubPipeline()

    result = _run_all_with_ordinary_lease(pipeline, db_session, run_id="run-1", limit=None)

    assert pipeline.calls == 1, "ordinary mdm mastering must never skip resolution over a lease conflict"
    assert result == {"kwargs": {"run_id": "run-1", "limit": None}}
    row = get_mdm_pipeline_lease(db_session)
    assert row.mode == "backstop"
    assert row.run_id == "backstop-1"
