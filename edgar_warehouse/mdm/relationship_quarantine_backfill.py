"""mdm-relationship-versioning-gap Ticket 05: backfill already-quarantined
``mdm_relationship_instance`` rows now that Tickets 01-03 fixed the
write-time logic that would have prevented them.

Scope: this corrects rows quarantined by ``ensure_relationship``'s
same-source, no-configured-priority conflict path (``graph.py``'s
``resolve_source_priority`` returning ``"none"`` for two rows sharing a
``source_system``) -- the exact "predecessor version never closed" shape
Tickets 01-03 fixed going forward. It deliberately does NOT resolve
quarantined rows whose conflict was against a *different* source_system
with no configured priority (a genuine cross-source data disagreement
needing a ``mdm_relationship_source_priority`` rule or manual review, not
an automated "newer wins" override), nor rows where a priority rule now
exists that didn't exist when the row was originally quarantined (a
different resolution axis -- authority-based supersession, not
versioning -- that this ticket's fix was never designed to apply
automatically). Both are left untouched and counted separately.

Does NOT touch the Snowflake graph. Ticket 04 (mdm-relationship-
versioning-gap map) found the graph materialization filters only
``IS_ACTIVE = TRUE``, never ``QUARANTINED = FALSE`` -- so a quarantined row
already leaked into the graph as a duplicate edge before this backfill
ever un-quarantines it. Running this backfill corrects Postgres; a fresh
``sync-graph`` generation rebuild (or the separate, not-yet-implemented
query-filter fix) is still needed to clear the graph-side duplicates --
``run_backfill`` prints a reminder of this at the end of a real run.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmRelationshipInstance
from edgar_warehouse.mdm.graph import (
    close_relationship_version,
    confirmed_chronologically_after,
    relationships_conflict,
    resolve_source_priority,
)

_BACKFILL_SOURCE_SYSTEM = "relationship_quarantine_backfill"


@dataclass
class RelationshipQuarantineBackfillSummary:
    relationship_ids_examined: int = 0
    reopened: int = 0
    closed: int = 0
    skipped_cross_source: int = 0
    skipped_priority_now_configured: int = 0
    skipped_ambiguous_order: int = 0
    skipped_ambiguous_date: int = 0
    skipped_multiple_conflicts: int = 0

    def add(self, other: "RelationshipQuarantineBackfillSummary") -> None:
        self.relationship_ids_examined += other.relationship_ids_examined
        self.reopened += other.reopened
        self.closed += other.closed
        self.skipped_cross_source += other.skipped_cross_source
        self.skipped_priority_now_configured += other.skipped_priority_now_configured
        self.skipped_ambiguous_order += other.skipped_ambiguous_order
        self.skipped_ambiguous_date += other.skipped_ambiguous_date
        self.skipped_multiple_conflicts += other.skipped_multiple_conflicts


def find_quarantined_relationship_ids(
    session: Session, *, limit: Optional[int] = None, after: Optional[str] = None
) -> list[str]:
    """Distinct relationship_ids with at least one currently-quarantined row.

    ``after`` does keyset pagination on ``relationship_id`` itself, not on
    "still quarantined" -- some rows are deliberately left quarantined by
    ``backfill_relationship_id`` (cross-source conflicts, ambiguous dates),
    so a batch loop that re-queries "still has a quarantined row" without
    this would loop forever on exactly those rows instead of advancing.
    """
    stmt = select(MdmRelationshipInstance.relationship_id).where(
        MdmRelationshipInstance.quarantined.is_(True)
    ).distinct().order_by(MdmRelationshipInstance.relationship_id)
    if after is not None:
        stmt = stmt.where(MdmRelationshipInstance.relationship_id > after)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def _effective_from_of(row: MdmRelationshipInstance):
    """The value ``ensure_relationship``'s own chronological guard compares
    (``effective_from``, falling back to ``valid_from_date`` only if a
    caller never set one) -- matches ``_deactivate_if_properties_changed``'s
    own ``effective_from`` parameter, which every deriver passes the same
    value it also passes to ``ensure_relationship``'s own ``effective_from``
    argument (confirmed by reading each ``_derive_*`` call site)."""
    return row.effective_from if row.effective_from is not None else row.valid_from_date


def _record_backfill_evidence(row: MdmRelationshipInstance, note: str) -> None:
    """Append a trace of this correction to the row's own ``source_evidence``.

    ``mdm_change_log`` is NOT the right audit mechanism here -- it never
    tracked relationships at all (see ``_derive_employed_by``'s own
    docstring in ``pipeline.py``, and the "mdm_change_log had no write-side
    diff" CLAUDE.md entry). ``source_evidence`` is the mechanism this table
    already uses to record provenance (``_evidence_entry``/
    ``_merge_source_evidence`` in ``graph.py``), so a correction is recorded
    there instead of introducing a new, unproven audit path.
    """
    evidence = list(row.source_evidence or [])
    evidence.append({
        "source_system": _BACKFILL_SOURCE_SYSTEM,
        "source_accession": None,
        "note": note,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    row.source_evidence = evidence


def backfill_relationship_id(
    session: Session, relationship_id: str, *, dry_run: bool = False
) -> RelationshipQuarantineBackfillSummary:
    """Correct every quarantined row sharing ``relationship_id``.

    Reuses the exact discriminator/overlap/chronological-guard/priority
    semantics ``ensure_relationship``/``_deactivate_if_properties_changed``
    already use (via the shared ``relationships_conflict``/
    ``confirmed_chronologically_after``/``resolve_source_priority``
    functions in ``graph.py``), applied retroactively against existing rows
    instead of at insert time -- so a row that would still legitimately
    conflict under the fixed logic (e.g. a genuine cross-source
    disagreement, or a date that can't be positively confirmed to come
    after the row it conflicts with) is left exactly as it is, not
    force-resolved.
    """
    summary = RelationshipQuarantineBackfillSummary(relationship_ids_examined=1)

    rows = list(session.scalars(
        select(MdmRelationshipInstance)
        .where(MdmRelationshipInstance.relationship_id == relationship_id)
        .where(MdmRelationshipInstance.is_active.is_(True))
        .where(MdmRelationshipInstance.superseded_by_version_id.is_(None))
    ))

    quarantined = [r for r in rows if r.quarantined]
    current_candidates = [r for r in rows if not r.quarantined]

    dated_quarantined = []
    for row in quarantined:
        if _effective_from_of(row) is None:
            summary.skipped_ambiguous_date += 1
            continue
        dated_quarantined.append(row)
    dated_quarantined.sort(key=_effective_from_of)

    for q in dated_quarantined:
        q_effective_from = _effective_from_of(q)
        conflicts = [
            c for c in current_candidates
            if relationships_conflict(
                c.valid_from_date, c.valid_to_date, c.properties,
                q.valid_from_date, q.valid_to_date, q.properties,
            )
        ]
        if len(conflicts) > 1:
            summary.skipped_multiple_conflicts += 1
            continue
        if not conflicts:
            # No currently-active conflict remains for this row -- whatever
            # it originally conflicted with has since been closed/superseded
            # by some other process. Nothing to close; just reopen.
            if not dry_run:
                q.quarantined = False
                q.quarantine_reason = None
                _record_backfill_evidence(q, "reopened: no active conflict remained")
            summary.reopened += 1
            current_candidates.append(q)
            continue

        conflict = conflicts[0]
        priority_winner = resolve_source_priority(
            session, q.rel_type_id, conflict.source_system, q.source_system
        )
        if priority_winner != "none":
            # A mdm_relationship_source_priority rule now resolves this
            # pair by configured authority -- a different resolution axis
            # (supersession, not versioning) that this backfill was never
            # designed to apply automatically. Flag for a separate decision.
            summary.skipped_priority_now_configured += 1
            continue
        if conflict.source_system != q.source_system:
            summary.skipped_cross_source += 1
            continue
        if not confirmed_chronologically_after(q_effective_from, conflict.valid_from_date):
            summary.skipped_ambiguous_order += 1
            continue

        if not dry_run:
            close_relationship_version(session, conflict.instance_id, q_effective_from)
            _record_backfill_evidence(conflict, f"closed: superseded by {q.instance_id}")
            q.quarantined = False
            q.quarantine_reason = None
            _record_backfill_evidence(q, f"reopened: superseded {conflict.instance_id}")
        summary.closed += 1
        summary.reopened += 1
        current_candidates.remove(conflict)
        current_candidates.append(q)

    return summary


def run_backfill(
    session: Session, *, batch_size: int = 500, dry_run: bool = False
) -> RelationshipQuarantineBackfillSummary:
    """Drain every relationship_id with a quarantined row, committing per batch.

    Dry-run doesn't mutate anything, so a batched query would keep
    returning the same relationship_ids forever -- fetch the full
    candidate list once up front instead (bounded by the live quarantined
    count, not an arbitrary batch size) and report on all of it in one
    pass.
    """
    total = RelationshipQuarantineBackfillSummary()
    if dry_run:
        for relationship_id in find_quarantined_relationship_ids(session):
            total.add(backfill_relationship_id(session, relationship_id, dry_run=True))
        return total

    after: Optional[str] = None
    while True:
        relationship_ids = find_quarantined_relationship_ids(
            session, limit=batch_size, after=after
        )
        if not relationship_ids:
            break
        for relationship_id in relationship_ids:
            total.add(backfill_relationship_id(session, relationship_id, dry_run=False))
        after = relationship_ids[-1]
        session.commit()
        print(json.dumps({
            "event": "mdm_relationship_quarantine_backfill_batch",
            "relationship_ids_examined": total.relationship_ids_examined,
            "reopened": total.reopened,
            "closed": total.closed,
            "ts": datetime.now(timezone.utc).isoformat(),
        }), file=sys.stderr, flush=True)

    if total.reopened > 0:
        print(json.dumps({
            "event": "mdm_relationship_quarantine_backfill_complete",
            "reopened": total.reopened,
            "reminder": (
                "Postgres corrected; the Snowflake graph still shows the "
                "old duplicate edges for these rows until a fresh sync-graph "
                "generation rebuild runs (mdm-relationship-versioning-gap "
                "Ticket 04)."
            ),
            "ts": datetime.now(timezone.utc).isoformat(),
        }), file=sys.stderr, flush=True)
    return total
