"""Priority Merge engine.

Reads candidate values from mdm_entity_attribute_stage, applies the per-field
rule from mdm_field_survivorship, marks the winning row was_selected=TRUE, and
writes the winning value to the domain golden record table.

Survivorship rule types:
  source_priority      — winner = highest-ranked active source (preferred_source_order first)
  most_recent          — winner = row with largest effective_date (ties broken by priority)
  immutable            — winner = first value ever written from the declared source; never overridden
  highest_source_rank  — winner = row from lowest-numbered (i.e. highest-authority) source
  custom               — reserved for future; treated as source_priority today
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmEntityAttributeStage
from edgar_warehouse.mdm.rules import FieldRule, MDMRuleEngine


@dataclass(frozen=True)
class Candidate:
    """One candidate value contributed by one source row."""

    stage_id: str
    source_system: str
    source_id: str
    field_value: Optional[str]
    global_priority: int
    effective_date: Optional[date]


@dataclass(frozen=True)
class MergeResult:
    entity_id: str
    field_name: str
    winning_value: Optional[str]
    winning_stage_id: Optional[str]
    winning_source: Optional[str]
    rule_applied: str


def _preferred_rank(cand: Candidate, preferred_order: list[str]) -> tuple[int, int]:
    """Return (index_in_preferred_order, global_priority) for sort key.

    Sources listed in preferred_order come first; anything else falls back to
    its global priority rank.
    """
    try:
        idx = preferred_order.index(cand.source_system)
    except ValueError:
        idx = len(preferred_order) + cand.global_priority
    return (idx, cand.global_priority)


def _pick_by_rule(
    rule: FieldRule,
    candidates: list[Candidate],
    existing_value: Optional[str],
) -> Optional[Candidate]:
    if not candidates:
        return None

    non_null = [c for c in candidates if c.field_value not in (None, "")]
    pool = non_null or candidates

    if rule.rule_type == "immutable":
        if existing_value not in (None, ""):
            return None
        if rule.source_system:
            pool = [c for c in pool if c.source_system == rule.source_system]
        if not pool:
            return None
        return sorted(pool, key=lambda c: c.global_priority)[0]

    if rule.rule_type == "most_recent":
        if rule.source_system:
            pool = [c for c in pool if c.source_system == rule.source_system]
        if not pool:
            return None
        return sorted(
            pool,
            key=lambda c: (
                -(c.effective_date.toordinal() if c.effective_date else 0),
                c.global_priority,
            ),
        )[0]

    if rule.rule_type == "highest_source_rank":
        return sorted(pool, key=lambda c: c.global_priority)[0]

    # source_priority (default) + custom fallback
    if rule.preferred_source_order:
        ordered = sorted(pool, key=lambda c: _preferred_rank(c, rule.preferred_source_order))
        return ordered[0]
    return sorted(pool, key=lambda c: c.global_priority)[0]


def merge_field(
    session: Session,
    engine: MDMRuleEngine,
    entity_type: str,
    entity_id: str,
    field_name: str,
    candidates: Iterable[Candidate],
    existing_value: Optional[str] = None,
) -> MergeResult:
    rule = engine.get_field_rule(entity_type, field_name)
    if rule is None:
        # Default: source_priority with global ranking (preferred_source_order=None)
        rule = FieldRule(
            entity_type=entity_type,
            field_name=field_name,
            rule_type="source_priority",
            source_system=None,
            preferred_source_order=None,
        )

    cand_list = list(candidates)
    winner = _pick_by_rule(rule, cand_list, existing_value)

    if winner is not None:
        session.execute(
            update(MdmEntityAttributeStage)
            .where(MdmEntityAttributeStage.stage_id == winner.stage_id)
            .values(was_selected=True)
        )

    return MergeResult(
        entity_id=entity_id,
        field_name=field_name,
        winning_value=winner.field_value if winner else None,
        winning_stage_id=winner.stage_id if winner else None,
        winning_source=winner.source_system if winner else None,
        rule_applied=rule.rule_type,
    )


def stage_candidate(
    session: Session,
    engine: MDMRuleEngine,
    entity_type: str,
    entity_id: str,
    source_system: str,
    source_id: str,
    field_name: str,
    field_value: Optional[Any],
    effective_date: Optional[date] = None,
) -> MdmEntityAttributeStage:
    """Insert a single source value into the staging table before survivorship runs."""
    priority = engine.get_source_priority(entity_type, source_system)
    row = MdmEntityAttributeStage(
        entity_id=entity_id,
        source_system=source_system,
        source_id=source_id,
        field_name=field_name,
        field_value=None if field_value is None else str(field_value),
        global_priority=priority,
        effective_date=effective_date,
    )
    session.add(row)
    return row


def run_survivorship_for_entity(
    session: Session,
    engine: MDMRuleEngine,
    entity_type: str,
    entity_id: str,
    fields: list[str],
    existing_values: Optional[dict[str, Any]] = None,
) -> dict[str, MergeResult]:
    """Run Priority Merge for every named field on one entity.

    Reads pending rows from mdm_entity_attribute_stage, picks winners, updates
    was_selected=TRUE. Caller is responsible for writing winning_value back to
    the domain golden record table.
    """
    existing = existing_values or {}
    results: dict[str, MergeResult] = {}
    for fname in fields:
        rows = session.scalars(
            select(MdmEntityAttributeStage).where(
                (MdmEntityAttributeStage.entity_id == entity_id)
                & (MdmEntityAttributeStage.field_name == fname)
            )
        ).all()
        cands = [
            Candidate(
                stage_id=r.stage_id,
                source_system=r.source_system,
                source_id=r.source_id,
                field_value=r.field_value,
                global_priority=r.global_priority,
                effective_date=r.effective_date,
            )
            for r in rows
        ]
        results[fname] = merge_field(
            session,
            engine,
            entity_type,
            entity_id,
            fname,
            cands,
            existing_value=existing.get(fname),
        )
    return results
