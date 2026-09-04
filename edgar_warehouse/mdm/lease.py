"""MDM pipeline lease: exclusivity between ordinary `mdm mastering`
resolution and the monthly MDM Reconciliation Backstop (change-propagation
Ticket 50).

Mirrors edgar_warehouse.bookkeeping.store's acquire_pipeline_run_lease /
release_pipeline_run_lease conditional-upsert shape exactly, against a new
table in MDM's own Postgres store instead -- the warehouse's Bookkeeping
Postgres store (where PipelineRunLease lives) is a *different* Postgres
instance (see CLAUDE.md's "MDM database" note), unreachable from here.

Deliberately asymmetric between the two callers (see Ticket 50's own
"Overlap" decision plus the Identity Refresh Slot precedent this mirrors,
edgar_warehouse/application/warehouse_orchestrator.py's
acquire-identity-refresh-lease/acquire-sec-fetch-lease handlers): the
backstop has a real "next slot" (next month's schedule) to retry on, so it
defers cleanly when it can't acquire. Ordinary `mdm mastering` runs inside a
bounded daily/incremental execution with no such slot -- failing it closed
over a rare, off-by-default monthly backstop would burn a production
pipeline's retry budget for no data-quality benefit, so it always proceeds
with resolution regardless of whether it wins the lease. See
reconciliation_backstop.py and cli.py's ordinary-mastering call site for how
each caller uses the return value differently.

Disclosed residual gap (code review, Ticket 50): this makes "cannot overlap"
one-directional, not the fully bidirectional guarantee Ticket 50's checklist
literally states. The lease reliably stops a backstop pass from *starting*
while ordinary resolution is active. It does NOT stop an ordinary run from
*starting* while a backstop pass is already mid-flight -- ordinary always
proceeds in that case (see above), so the two can genuinely run concurrently
against the same MDM Postgres state for the remainder of the backstop's
run. This is an accepted, deliberate tradeoff rather than an oversight:
symmetric fail-closed behavior was considered and rejected (it would fail
production `mdm mastering` runs over a rare, off-by-default monthly job),
and the emitted `mdm_resolution_lease_conflict` event makes every occurrence
observable for an operator to act on. The residual correctness risk this
accepts -- a concurrent write racing the backstop's own merge/review
disposition mid-pass -- is bounded by the backstop's off-by-default, monthly
cadence, not eliminated. A future revisit could have the backstop checkpoint
and re-acquire the lease between entity types, so a conflicting ordinary run
can interrupt it early instead of racing it for hours; not built here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmPipelineLease

MDM_RESOLUTION_LEASE_NAME = "mdm_resolution"

# Ticket 50's own text: "First measured run sets the duration bound; do not
# copy Identity Backstop Sweep's 18h SLO." These are conservative,
# unvalidated placeholders pending that first measured run, not tuned SLOs.
BACKSTOP_STALE_AFTER_SECONDS = 24 * 3600
ORDINARY_STALE_AFTER_SECONDS = 8 * 3600


def _insert_factory(session: Session):
    dialect_name = session.get_bind().dialect.name
    return sqlite_insert if dialect_name == "sqlite" else postgresql_insert


def acquire_mdm_pipeline_lease(
    session: Session,
    *,
    mode: str,
    run_id: str,
    stale_after_seconds: int,
    lease_name: str = MDM_RESOLUTION_LEASE_NAME,
    acquired_at: Optional[datetime] = None,
) -> bool:
    """Atomically claim the shared MDM resolution lease for `mode`.

    Wins the lease when it is currently idle, or held but stale beyond
    `stale_after_seconds`. Returns whether *this* call acquired it -- a
    caller must check the return value, not assume success.
    """
    now = acquired_at or datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(seconds=stale_after_seconds)
    insert_factory = _insert_factory(session)
    stmt = insert_factory(MdmPipelineLease).values(
        lease_name=lease_name,
        status="held",
        run_id=run_id,
        mode=mode,
        acquired_at=now,
        released_at=None,
        updated_at=now,
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[MdmPipelineLease.lease_name],
        set_={
            "status": "held",
            "run_id": excluded.run_id,
            "mode": excluded.mode,
            "acquired_at": excluded.acquired_at,
            "released_at": None,
            "updated_at": excluded.updated_at,
        },
        where=(
            (MdmPipelineLease.status != "held")
            | (MdmPipelineLease.acquired_at < stale_cutoff)
        ),
    )
    session.execute(stmt)
    session.commit()
    row = get_mdm_pipeline_lease(session, lease_name)
    return bool(row and row.run_id == run_id and row.status == "held")


def release_mdm_pipeline_lease(
    session: Session,
    *,
    run_id: str,
    released_at: Optional[datetime] = None,
    lease_name: str = MDM_RESOLUTION_LEASE_NAME,
) -> None:
    from sqlalchemy import update

    now = released_at or datetime.now(timezone.utc)
    session.execute(
        update(MdmPipelineLease)
        .where(
            MdmPipelineLease.lease_name == lease_name,
            MdmPipelineLease.run_id == run_id,
            MdmPipelineLease.status == "held",
        )
        .values(status="idle", released_at=now, updated_at=now)
    )
    session.commit()


def get_mdm_pipeline_lease(
    session: Session, lease_name: str = MDM_RESOLUTION_LEASE_NAME
) -> Optional[MdmPipelineLease]:
    return session.get(MdmPipelineLease, lease_name)
