"""manages-fund-duplicate-rows map, Ticket 03: live-monitoring check for a
new MANAGES_FUND duplicate active-row group.

Ticket 01 found 140,907 relationship_ids with 2+ currently-active,
non-quarantined, non-superseded rows sharing byte-identical
``properties``/``valid_from_date``/``valid_to_date`` -- a one-time
historical event, not an ongoing bug: every affected row was written in
one Postgres transaction on 2026-08-19, and zero new duplicate rows have
appeared in the 3+ weeks (4,116 new MANAGES_FUND rows) since the
2026-08-21 CRD-batching refactor (``869003da``) that replaced the old,
now-dead code path. The exact mechanism inside that old code was never
conclusively pinned down (see Ticket 01's own Answer) -- this check exists
as insurance against that gap, not because a live bug is still suspected.

Deliberately stateless: rather than persisting a baseline snapshot to
diff against (new storage, new failure modes), this compares each
duplicate group's newest row's ``created_at`` against a fixed cutoff --
the CRD-batching refactor's own deploy time, plus a one-day safety margin.
Every row in the known 140,907-group backlog was written before this
cutoff (Ticket 01's own finding: all share one 2026-08-19 timestamp); any
group whose newest row was created after it is a genuine new occurrence,
not the known backlog. Once Ticket 04's backlog cleanup runs, the known
backlog stops satisfying the ``>= 2`` count at all and this cutoff becomes
a redundant safety margin rather than a load-bearing distinction -- safe
either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

# One day after the 2026-08-21 CRD-batching refactor (commit 869003da) that
# replaced the old, now-dead MANAGES_FUND code path Ticket 01 found responsible
# for the entire known backlog -- every backlog row's created_at is 2026-08-19,
# well before this. The one-day margin absorbs any deploy-timing slack without
# needing the refactor's exact commit timestamp.
KNOWN_BACKLOG_CUTOFF = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)

REL_TYPE_NAME = "MANAGES_FUND"


@dataclass(frozen=True)
class DuplicateGroup:
    """``relationship_id`` has ``active_count`` currently-active,
    non-quarantined, non-superseded rows sharing identical properties and
    validity window, with the newest one created at ``latest_created_at``
    -- after ``KNOWN_BACKLOG_CUTOFF``, so not part of the known backlog."""

    relationship_id: str
    active_count: int
    latest_created_at: datetime


@dataclass(frozen=True)
class DuplicateCheckResult:
    new_duplicate_groups: tuple[DuplicateGroup, ...]

    @property
    def is_clean(self) -> bool:
        return not self.new_duplicate_groups


def _find_new_duplicate_groups(conn, cutoff: datetime) -> list[DuplicateGroup]:
    rows = conn.execute(
        text(
            """
            SELECT ri.relationship_id AS relationship_id,
                   count(*) AS active_count,
                   max(ri.created_at) AS latest_created_at
            FROM mdm_relationship_instance ri
            JOIN mdm_relationship_type rt ON rt.rel_type_id = ri.rel_type_id
            WHERE rt.rel_type_name = :rel_type_name
              AND ri.is_active = TRUE
              AND ri.quarantined = FALSE
              AND ri.superseded_by_version_id IS NULL
            GROUP BY ri.relationship_id, ri.properties, ri.valid_from_date, ri.valid_to_date
            HAVING count(*) >= 2 AND max(ri.created_at) > :cutoff
            """
        ),
        {"rel_type_name": REL_TYPE_NAME, "cutoff": cutoff},
    ).fetchall()
    return [
        DuplicateGroup(
            relationship_id=str(row.relationship_id),
            active_count=row.active_count,
            latest_created_at=row.latest_created_at,
        )
        for row in rows
    ]


def check_manages_fund_duplicates(
    engine: Engine, *, cutoff: datetime = KNOWN_BACKLOG_CUTOFF
) -> DuplicateCheckResult:
    """Alert-worthy only when a MANAGES_FUND relationship_id gets a *new*
    duplicate active-row group -- one whose newest row was created after
    ``cutoff``. The known 140,907-group historical backlog (Ticket 01) is
    deliberately excluded, not treated as a standing failure."""
    with engine.connect() as conn:
        new_duplicate_groups = _find_new_duplicate_groups(conn, cutoff)
    return DuplicateCheckResult(new_duplicate_groups=tuple(new_duplicate_groups))
