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


def _loaded_key(r: MdmEntityAttributeStage) -> tuple:
    loaded = r.loaded_at
    return (loaded is not None, loaded or _MIN_DATETIME)


def collapse_entities_batch(
    session: Session,
    entity_ids: list[str],
    *,
    dry_run: bool = False,
) -> AttributeStageBackfillSummary:
    """Collapse every redundant group across a whole batch of entities in
    one pass -- one SELECT and (for a real run) one bulk DELETE for the
    entire batch, instead of one round trip per entity/group. Live-measured
    2026-09-11: the original per-entity/per-group shape cost ~4.8 DELETE
    round trips per entity on top of its own SELECT (671,075 collapsed
    groups / 139,349 entities from the completed dry run), each a flat
    ~57ms cross-region Postgres round trip -- projecting the real run to
    ~14h. This collects every group's redundant rows across the whole
    batch first and issues one DELETE per batch instead of one per group.
    """
    summary = AttributeStageBackfillSummary(entities_examined=len(entity_ids))
    if not entity_ids:
        return summary

    rows = list(
        session.execute(
            select(MdmEntityAttributeStage).where(
                MdmEntityAttributeStage.entity_id.in_(entity_ids)
            )
        ).scalars().all()
    )

    groups: dict[tuple, list[MdmEntityAttributeStage]] = defaultdict(list)
    for row in rows:
        key = (
            row.entity_id,
            row.source_system,
            row.field_name,
            row.field_value,
            row.global_priority,
        )
        groups[key].append(row)

    batch_redundant_ids: list = []

    for group_rows in groups.values():
        if len(group_rows) <= 1:
            continue

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

        batch_redundant_ids.extend(r.stage_id for r in redundant)

    if batch_redundant_ids:
        session.execute(
            delete(MdmEntityAttributeStage).where(
                MdmEntityAttributeStage.stage_id.in_(batch_redundant_ids)
            )
        )

    return summary


def collapse_entity(
    session: Session,
    entity_id: str,
    *,
    dry_run: bool = False,
) -> AttributeStageBackfillSummary:
    """Collapse every redundant group for one entity in one pass.

    Thin single-entity wrapper over collapse_entities_batch, kept for
    readability and as the direct target of the per-entity grouping/
    retention-rule unit tests -- a batch of one is a strict subset of the
    batch function's own behavior (same grouping key, entity_id just
    doesn't vary), not a second implementation to keep in sync.
    """
    return collapse_entities_batch(session, [entity_id], dry_run=dry_run)


def run_backfill(
    session: Session,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> AttributeStageBackfillSummary:
    """Drain every entity with a collapsible group, committing per batch.

    Both branches page through ``find_collapsible_entity_ids`` at the same
    ``batch_size`` boundary and call ``collapse_entities_batch`` once per
    page -- one SELECT and (for a real run) one bulk DELETE per batch,
    instead of one round trip per entity/group. Dry-run pages the same way
    as the real run (rather than fetching the full candidate list unbounded
    up front, as an earlier version of this function did) purely to bound
    its own per-batch SELECT size; unlike the real branch it never commits
    or advances any durable state, so paging here is a read-side cost
    control, not a resumability mechanism.

    ``limit`` caps the total number of entities examined across every page
    (``None``, the default, is unbounded -- the original full-backfill
    contract). Use it for a fast correctness check against real data
    (``dry_run=True, limit=50``) instead of walking the whole live
    candidate set just to prove the logic works -- see the AGENTS.md/
    CLAUDE.md note this closes the loop on.
    """
    total = AttributeStageBackfillSummary()

    after: Optional[str] = None
    while True:
        page_size = batch_size
        if limit is not None:
            remaining = limit - total.entities_examined
            if remaining <= 0:
                break
            page_size = min(batch_size, remaining)
        entity_ids = find_collapsible_entity_ids(session, limit=page_size, after=after)
        if not entity_ids:
            break
        total.add(collapse_entities_batch(session, entity_ids, dry_run=dry_run))
        after = entity_ids[-1]
        if dry_run:
            continue
        session.commit()
        print(json.dumps({
            "event": "mdm_attribute_stage_backfill_batch",
            "entities_examined": total.entities_examined,
            "groups_collapsed": total.groups_collapsed,
            "rows_deleted": total.rows_deleted,
            "ts": datetime.now(timezone.utc).isoformat(),
        }), file=sys.stderr, flush=True)

    return total
