"""Change-propagation Ticket 50: run_reconciliation_backstop()'s lease
gating -- the required "a second overlapping mdm run is rejected" test, at
the level a real backstop invocation actually runs through.
"""
from __future__ import annotations

from unittest.mock import patch

from edgar_warehouse.mdm.lease import acquire_mdm_pipeline_lease, get_mdm_pipeline_lease
from edgar_warehouse.mdm.reconciliation_backstop import run_reconciliation_backstop

from tests.mdm.test_run_all_step_concurrency import _seed_fundamentals_relationship_types
from tests.mdm.test_run_companies_concurrency import StubSilver, _StubBookkeeping, _seeded_sqlite_session


def test_backstop_runs_and_releases_the_lease_when_free():
    session = _seeded_sqlite_session(static_pool=True)
    _seed_fundamentals_relationship_types(session)
    silver = StubSilver({})

    result = run_reconciliation_backstop(
        session, silver, bookkeeping=_StubBookkeeping(), run_id="backstop-1"
    )

    assert result.ran is True
    assert result.stats is not None
    row = get_mdm_pipeline_lease(session)
    assert row.status == "idle"


def test_backstop_defers_when_an_ordinary_run_holds_the_lease():
    session = _seeded_sqlite_session(static_pool=True)
    silver = StubSilver({})
    acquire_mdm_pipeline_lease(
        session, mode="ordinary", run_id="daily-run-1", stale_after_seconds=3600
    )

    with patch("edgar_warehouse.mdm.reconciliation_backstop.MDMPipeline") as mock_pipeline_cls:
        result = run_reconciliation_backstop(
            session, silver, bookkeeping=_StubBookkeeping(), run_id="backstop-1"
        )

    assert result.ran is False
    assert result.held_by_run_id == "daily-run-1"
    mock_pipeline_cls.assert_not_called()

    row = get_mdm_pipeline_lease(session)
    assert row.status == "held"
    assert row.run_id == "daily-run-1"


def test_backstop_releases_the_lease_even_if_run_all_raises():
    session = _seeded_sqlite_session(static_pool=True)
    silver = StubSilver({})

    with patch(
        "edgar_warehouse.mdm.reconciliation_backstop.MDMPipeline"
    ) as mock_pipeline_cls:
        mock_pipeline_cls.return_value.run_all.side_effect = RuntimeError("boom")
        try:
            run_reconciliation_backstop(
                session, silver, bookkeeping=_StubBookkeeping(), run_id="backstop-1"
            )
        except RuntimeError:
            pass

    row = get_mdm_pipeline_lease(session)
    assert row.status == "idle"
