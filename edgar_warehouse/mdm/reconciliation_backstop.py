"""The MDM Reconciliation Backstop (change-propagation Ticket 50): the
periodic full-universe match/survivorship/relationship re-derivation pass
Ticket 38 designed. Existing MDMPipeline.run_all() with skip-if-unchanged
off and no --limit, gated by the shared mdm_resolution lease (lease.py) so
it never overlaps ordinary `mdm mastering` resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from edgar_warehouse.mdm.lease import (
    BACKSTOP_STALE_AFTER_SECONDS,
    acquire_mdm_pipeline_lease,
    get_mdm_pipeline_lease,
    release_mdm_pipeline_lease,
)
from edgar_warehouse.mdm.observability import emit_mdm_event
from edgar_warehouse.mdm.pipeline import MDMPipeline, PipelineStats
from edgar_warehouse.mdm.resolvers.base import SilverReader

if TYPE_CHECKING:
    from edgar_warehouse.bookkeeping.store import BookkeepingStore


@dataclass
class ReconciliationBackstopResult:
    ran: bool
    stats: Optional[PipelineStats] = None
    held_by_run_id: Optional[str] = None


def run_reconciliation_backstop(
    session: Session,
    silver: SilverReader,
    *,
    bookkeeping: "BookkeepingStore",
    run_id: str,
) -> ReconciliationBackstopResult:
    """Run the full-universe backstop pass, or defer cleanly if ordinary
    `mdm mastering` resolution (or another backstop attempt) currently holds
    the shared lease.

    The backstop is the side that defers here, not ordinary `mdm mastering`
    -- see lease.py's module docstring for why the two callers are
    deliberately asymmetric. Deferring is a normal, expected outcome (the
    monthly EventBridge schedule is this pass's own "next slot"), not an
    error -- callers should not treat ``ran=False`` as a failure.
    """
    acquired = acquire_mdm_pipeline_lease(
        session,
        mode="backstop",
        run_id=run_id,
        stale_after_seconds=BACKSTOP_STALE_AFTER_SECONDS,
    )
    if not acquired:
        held = get_mdm_pipeline_lease(session)
        emit_mdm_event(
            "mdm_reconciliation_backstop_deferred",
            run_id=run_id,
            held_by_run_id=held.run_id if held else None,
            held_mode=held.mode if held else None,
        )
        return ReconciliationBackstopResult(
            ran=False, held_by_run_id=held.run_id if held else None
        )

    emit_mdm_event("mdm_reconciliation_backstop_started", run_id=run_id)
    try:
        pipeline = MDMPipeline(session=session, silver=silver, run_id=run_id)
        stats = pipeline.run_all(
            limit=None,
            run_id=run_id,
            bookkeeping=bookkeeping,
            reconciliation_pass=True,
        )
    except Exception as exc:
        emit_mdm_event(
            "mdm_reconciliation_backstop_failed", run_id=run_id, error=exc.__class__.__name__
        )
        raise
    finally:
        release_mdm_pipeline_lease(
            session, run_id=run_id, released_at=datetime.now(timezone.utc)
        )
    emit_mdm_event("mdm_reconciliation_backstop_completed", run_id=run_id, **stats.__dict__)
    return ReconciliationBackstopResult(ran=True, stats=stats)
