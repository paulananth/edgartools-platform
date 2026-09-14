"""manages-fund-duplicate-rows map, Ticket 05: backfill the existing
~140,907-relationship_id MANAGES_FUND duplicate-active-row backlog.

Ticket 01 found every affected ``relationship_id`` has 2-4 currently-active,
non-quarantined, non-superseded rows sharing byte-identical ``properties``/
``valid_from_date``/``valid_to_date``/``source_system``/``source_accession``
-- a one-time historical write-time bug, already gone (see
``manages_fund_duplicate_monitor.py``'s own docstring). Ticket 04 verified
this live across the *entire* backlog (not a sample), including the 3,960
relationship_ids that also carry a quarantined row -- their active rows are
equally clean duplicates of each other, so this backfill only ever touches
active rows and never the quarantined ones.

Deliberately much smaller than ``relationship_quarantine_backfill.py`` (the
mdm-relationship-versioning-gap map's own backfill): that module resolves
*genuinely conflicting* evidence via a chronological walk, priority
resolution, and several skip dispositions. None of that applies here --
every row in a group is identical evidence, so there is nothing to resolve,
only one arbitrary-but-deterministic winner to keep. Per Ticket 04's
resolved design: the winner is the row with the lexicographically smallest
``instance_id`` (a random UUIDv4 with no temporal ordering -- and every row
in a group shares one identical ``created_at``, so there is no meaningful
"earliest" to prefer; this is a determinism choice, not a correctness one).
Every other row gets ``superseded_by_version_id`` set to the winner's
``instance_id`` via the existing ``supersede_relationship_version`` helper
(``graph.py``) -- ``close_relationship_version``/``valid_to_date`` are
deliberately never touched, since these rows never had a real "stopped
being true" moment.

Does not touch the Snowflake graph -- the next regularly-scheduled
``sync-graph``/``publish-relationships`` run is sufficient (Ticket 04's
own decision; no active workflow depends on immediate reflection).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmRelationshipInstance, MdmRelationshipType
from edgar_warehouse.mdm.graph import supersede_relationship_version

REL_TYPE_NAME = "MANAGES_FUND"


@dataclass
class ManagesFundDuplicateBackfillSummary:
    relationship_ids_examined: int = 0
    rows_superseded: int = 0

    def add(self, other: "ManagesFundDuplicateBackfillSummary") -> None:
        self.relationship_ids_examined += other.relationship_ids_examined
        self.rows_superseded += other.rows_superseded


def find_duplicate_relationship_ids(
    session: Session,
    *,
    limit: Optional[int] = None,
    after: Optional[str] = None,
) -> list[str]:
    """Distinct MANAGES_FUND relationship_ids with 2+ currently-active,
    non-quarantined, non-superseded rows -- the backlog this backfill
    exists to close.

    ``after`` does keyset pagination on ``relationship_id`` itself (mirrors
    ``relationship_quarantine_backfill.find_quarantined_relationship_ids``'s
    own reasoning) -- a real run's candidate set shrinks as groups get
    superseded, so pagination on "still has 2+ active rows" would skip
    already-corrected groups' successors unpredictably rather than
    advancing through a stable order.
    """
    stmt = (
        select(MdmRelationshipInstance.relationship_id)
        .join(
            MdmRelationshipType,
            MdmRelationshipType.rel_type_id == MdmRelationshipInstance.rel_type_id,
        )
        .where(
            MdmRelationshipType.rel_type_name == REL_TYPE_NAME,
            MdmRelationshipInstance.is_active.is_(True),
            MdmRelationshipInstance.quarantined.is_(False),
            MdmRelationshipInstance.superseded_by_version_id.is_(None),
        )
        .group_by(MdmRelationshipInstance.relationship_id)
        .having(func.count(MdmRelationshipInstance.instance_id) >= 2)
        .order_by(MdmRelationshipInstance.relationship_id)
    )
    if after is not None:
        stmt = stmt.where(MdmRelationshipInstance.relationship_id > after)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def backfill_relationship_id(
    session: Session,
    relationship_id: str,
    *,
    dry_run: bool = False,
) -> ManagesFundDuplicateBackfillSummary:
    """Supersede every currently-active MANAGES_FUND row on
    ``relationship_id`` except one deterministic keeper.

    All rows in the group are confirmed byte-identical evidence (Ticket 01/
    04) -- the keeper is simply the row with the lexicographically smallest
    ``instance_id``, chosen only so reruns are idempotent, not because it
    reflects any real precedence. Every other row's
    ``superseded_by_version_id`` is set to the keeper's ``instance_id`` via
    the existing ``supersede_relationship_version`` helper.
    """
    rows = list(
        session.scalars(
            select(MdmRelationshipInstance)
            .join(
                MdmRelationshipType,
                MdmRelationshipType.rel_type_id == MdmRelationshipInstance.rel_type_id,
            )
            .where(
                MdmRelationshipType.rel_type_name == REL_TYPE_NAME,
                MdmRelationshipInstance.relationship_id == relationship_id,
                MdmRelationshipInstance.is_active.is_(True),
                MdmRelationshipInstance.quarantined.is_(False),
                MdmRelationshipInstance.superseded_by_version_id.is_(None),
            )
        )
    )
    summary = ManagesFundDuplicateBackfillSummary(relationship_ids_examined=1)
    if len(rows) < 2:
        return summary

    keeper = min(rows, key=lambda row: row.instance_id)
    for row in rows:
        if row.instance_id == keeper.instance_id:
            continue
        if not dry_run:
            supersede_relationship_version(session, row.instance_id, keeper.instance_id)
        summary.rows_superseded += 1
    return summary


def run_backfill(
    session: Session,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> ManagesFundDuplicateBackfillSummary:
    """Drain the MANAGES_FUND duplicate-active-row backlog, committing per batch.

    ``limit`` bounds the total number of relationship_ids examined --
    intended for a first pass against real prod data before a full,
    unbounded run (Ticket 04's rollout decision), and mirrors this repo's
    own documented lesson that an unbounded ``--dry-run`` against a live
    table defeats its own purpose as a cheap correctness check.

    Dry-run doesn't mutate anything, so (mirroring
    ``relationship_quarantine_backfill.run_backfill``'s identical
    reasoning) a batched query would keep returning the same
    relationship_ids forever -- fetch the bounded candidate list once up
    front instead and report on all of it in one pass.
    """
    total = ManagesFundDuplicateBackfillSummary()
    if dry_run:
        for relationship_id in find_duplicate_relationship_ids(session, limit=limit):
            total.add(backfill_relationship_id(session, relationship_id, dry_run=True))
        return total

    after: Optional[str] = None
    examined = 0
    while limit is None or examined < limit:
        remaining = None if limit is None else limit - examined
        fetch_size = batch_size if remaining is None else min(batch_size, remaining)
        relationship_ids = find_duplicate_relationship_ids(
            session, limit=fetch_size, after=after
        )
        if not relationship_ids:
            break
        for relationship_id in relationship_ids:
            total.add(backfill_relationship_id(session, relationship_id, dry_run=False))
        after = relationship_ids[-1]
        examined += len(relationship_ids)
        session.commit()
        print(
            json.dumps(
                {
                    "event": "mdm_manages_fund_duplicate_backfill_batch",
                    "relationship_ids_examined": total.relationship_ids_examined,
                    "rows_superseded": total.rows_superseded,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            ),
            file=sys.stderr,
            flush=True,
        )

    return total
