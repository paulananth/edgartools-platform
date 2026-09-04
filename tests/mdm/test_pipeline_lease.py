"""Change-propagation Ticket 50: the shared MDM pipeline lease."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from edgar_warehouse.mdm.lease import (
    acquire_mdm_pipeline_lease,
    get_mdm_pipeline_lease,
    release_mdm_pipeline_lease,
)


def test_acquire_when_idle_succeeds(db_session):
    acquired = acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="run-1", stale_after_seconds=3600
    )
    assert acquired is True
    row = get_mdm_pipeline_lease(db_session)
    assert row is not None
    assert row.status == "held"
    assert row.run_id == "run-1"
    assert row.mode == "backstop"


def test_acquire_when_held_and_fresh_is_rejected(db_session):
    assert acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="run-1", stale_after_seconds=3600
    )

    rejected = acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="run-2", stale_after_seconds=3600
    )

    assert rejected is False
    row = get_mdm_pipeline_lease(db_session)
    assert row.run_id == "run-1"


def test_acquire_when_held_but_stale_overrides(db_session):
    stale_acquired_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert acquire_mdm_pipeline_lease(
        db_session,
        mode="backstop",
        run_id="run-1",
        stale_after_seconds=3600,
        acquired_at=stale_acquired_at,
    )

    acquired = acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="run-2", stale_after_seconds=3600
    )

    assert acquired is True
    row = get_mdm_pipeline_lease(db_session)
    assert row.run_id == "run-2"


def test_release_then_reacquire_by_a_different_run_succeeds(db_session):
    assert acquire_mdm_pipeline_lease(
        db_session, mode="ordinary", run_id="run-1", stale_after_seconds=3600
    )
    release_mdm_pipeline_lease(db_session, run_id="run-1")

    acquired = acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="run-2", stale_after_seconds=3600
    )

    assert acquired is True
    row = get_mdm_pipeline_lease(db_session)
    assert row.status == "held"
    assert row.run_id == "run-2"


def test_release_by_the_wrong_run_id_is_a_no_op(db_session):
    assert acquire_mdm_pipeline_lease(
        db_session, mode="ordinary", run_id="run-1", stale_after_seconds=3600
    )

    release_mdm_pipeline_lease(db_session, run_id="run-2")

    row = get_mdm_pipeline_lease(db_session)
    assert row.status == "held"
    assert row.run_id == "run-1"


def test_a_second_overlapping_backstop_attempt_is_rejected(db_session):
    """Ticket 50's own required test: an ordinary mdm run holding the lease
    means a concurrently-attempted backstop pass is rejected (deferred to
    the next monthly slot), not run concurrently against live MDM state.
    """
    assert acquire_mdm_pipeline_lease(
        db_session, mode="ordinary", run_id="daily-run-1", stale_after_seconds=3600
    )

    backstop_acquired = acquire_mdm_pipeline_lease(
        db_session, mode="backstop", run_id="backstop-run-1", stale_after_seconds=3600
    )

    assert backstop_acquired is False
    row = get_mdm_pipeline_lease(db_session)
    assert row.mode == "ordinary"
    assert row.run_id == "daily-run-1"
