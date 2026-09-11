"""mdm-run-throughput Ticket 05: collapse already-accumulated
``mdm_entity_attribute_stage`` rows now that ``stage_candidate()``'s
write-time guard (``survivorship.py``) stops new ones for grouped
resolvers (run_securities/run_persons).

Scope: for each (entity_id, source_system, field_name, field_value,
global_priority) group with more than one row, collapse down to one
retained row and delete the rest. The retention rule is NOT a single
Pareto sort (an earlier design was; caught wrong by the mandatory
Standards/Spec code-review pass before this shipped) -- ``_pick_by_rule``
(survivorship.py) needs two independent maxima per group, not one: only
the ``most_recent`` rule type looks at ``effective_date`` at all;
``immutable``/``highest_source_rank``/``source_priority`` sort purely on
``(priority, loaded_at)`` and never touch it. A naive
"max effective_date, then max loaded_at as tiebreak" sort can silently
discard the group's true max-``loaded_at`` row if it doesn't also carry
the max ``effective_date`` -- flipping the winner for those 3 rule types.
Fixed by keeping the group's most-recently-loaded row as the survivor and
topping up its ``effective_date`` to the group's true max (from whichever
row held it) before deleting the rest -- mirrors exactly what
``stage_candidate()``'s own write-time fold already does incrementally,
just applied once over a static, already-accumulated row set. If any
deleted row had ``was_selected = True``, that flag migrates onto the
retained representative so the stewardship dashboard's "what was
selected" signal survives the collapse.

Does not touch groups with only one row (nothing to collapse) or groups
whose >1 rows genuinely differ in value (real correction/restatement
history -- kept as-is, not this ticket's concern).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmEntityAttributeStage

_MIN_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class AttributeStageBackfillSummary:
    entities_examined: int = 0
    groups_collapsed: int = 0
    rows_deleted: int = 0

    def add(self, other: "AttributeStageBackfillSummary") -> None:
        self.entities_examined += other.entities_examined
        self.groups_collapsed += other.groups_collapsed
        self.rows_deleted += other.rows_deleted


def find_collapsible_entity_ids(
    session: Session,
    *,
    limit: Optional[int] = None,
    after: Optional[str] = None,
) -> list[str]:
    """Entity_ids with at least one (source_system, field_name, field_value,
    global_priority) group holding more than one row, ordered for
    keyset pagination on entity_id."""
    grouped = (
        select(MdmEntityAttributeStage.entity_id)
        .group_by(
            MdmEntityAttributeStage.entity_id,
            MdmEntityAttributeStage.source_system,
            MdmEntityAttributeStage.field_name,
            MdmEntityAttributeStage.field_value,
            MdmEntityAttributeStage.global_priority,
        )
        .having(func.count() > 1)
    )
    if after is not None:
        grouped = grouped.where(MdmEntityAttributeStage.entity_id > after)
    subq = grouped.subquery()
    stmt = select(subq.c.entity_id).distinct().order_by(subq.c.entity_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.execute(stmt).scalars().all())


def collapse_entity(
    session: Session,
    entity_id: str,
    *,
    dry_run: bool = False,
) -> AttributeStageBackfillSummary:
    """Collapse every redundant group for one entity in one pass."""
    summary = AttributeStageBackfillSummary(entities_examined=1)
    rows = list(
        session.execute(
            select(MdmEntityAttributeStage).where(
                MdmEntityAttributeStage.entity_id == entity_id
            )
        ).scalars().all()
    )

    groups: dict[tuple, list[MdmEntityAttributeStage]] = defaultdict(list)
    for row in rows:
        key = (row.source_system, row.field_name, row.field_value, row.global_priority)
        groups[key].append(row)

    for group_rows in groups.values():
        if len(group_rows) <= 1:
            continue

        def _loaded_key(r: MdmEntityAttributeStage) -> tuple:
            loaded = r.loaded_at
            return (loaded is not None, loaded or _MIN_DATETIME)

        representative = max(group_rows, key=_loaded_key)
        redundant = [r for r in group_rows if r is not representative]

        true_max_effective_date = max(
            (r.effective_date for r in group_rows if r.effective_date is not None),
            default=None,
        )

        summary.groups_collapsed += 1
        summary.rows_deleted += len(redundant)

        if dry_run:
            continue

        if true_max_effective_date is not None and (
            representative.effective_date is None
            or true_max_effective_date > representative.effective_date
        ):
            representative.effective_date = true_max_effective_date

        if any(r.was_selected for r in redundant) and not representative.was_selected:
            representative.was_selected = True

        redundant_ids = [r.stage_id for r in redundant]
        session.execute(
            delete(MdmEntityAttributeStage).where(
                MdmEntityAttributeStage.stage_id.in_(redundant_ids)
            )
        )

    return summary


def run_backfill(
    session: Session,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> AttributeStageBackfillSummary:
    """Drain every entity with a collapsible group, committing per batch.

    Dry-run fetches the full candidate entity_id list once up front
    (bounded by the live collapsible count, not an arbitrary batch size)
    since nothing mutates to advance a batched cursor -- mirrors
    ``relationship_quarantine_backfill.run_backfill``'s identical dry-run
    shape.
    """
    total = AttributeStageBackfillSummary()

    if dry_run:
        for entity_id in find_collapsible_entity_ids(session):
            total.add(collapse_entity(session, entity_id, dry_run=True))
        return total

    after: Optional[str] = None
    while True:
        entity_ids = find_collapsible_entity_ids(session, limit=batch_size, after=after)
        if not entity_ids:
            break
        for entity_id in entity_ids:
            total.add(collapse_entity(session, entity_id, dry_run=False))
        after = entity_ids[-1]
        session.commit()
        print(json.dumps({
            "event": "mdm_attribute_stage_backfill_batch",
            "entities_examined": total.entities_examined,
            "groups_collapsed": total.groups_collapsed,
            "rows_deleted": total.rows_deleted,
            "ts": datetime.now(timezone.utc).isoformat(),
        }), file=sys.stderr, flush=True)

    return total
