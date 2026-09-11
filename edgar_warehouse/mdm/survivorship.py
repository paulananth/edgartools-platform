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
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from edgar_warehouse.mdm.database import MdmEntityAttributeStage
from edgar_warehouse.mdm.rules import FieldRule, MDMRuleEngine

_MIN_DATETIME = datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Candidate:
    """One candidate value contributed by one source row."""

    stage_id: str
    source_system: str
    source_id: str
    field_value: Optional[str]
    global_priority: int
    effective_date: Optional[date]
    loaded_at: Optional[datetime] = None


def _recency_key(loaded_at: Optional[datetime]) -> float:
    """Tie-break key: more recently staged sorts first (ascending sort, so
    more recent => more negative). Single-path-per-layer map, Ticket 03
    surfaced this gap while adding skip-if-unchanged: every tie-break sort
    below picked the *first-ever* staged candidate on a priority tie, with
    no recency signal at all, so a genuinely newer value from a later
    ``mdm mastering`` could permanently lose to a stale one -- ``loaded_at``
    already existed on ``mdm_entity_attribute_stage`` (server-defaulted
    NOW() on insert) but was never read. Missing ``loaded_at`` sorts last
    (least preferred), so an unpopulated timestamp can never win a tie it
    shouldn't.
    """
    if loaded_at is None:
        return float("inf")
    try:
        return -loaded_at.timestamp()
    except AttributeError:
        return float("inf")


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
        return sorted(pool, key=lambda c: (c.global_priority, _recency_key(c.loaded_at)))[0]

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
                _recency_key(c.loaded_at),
            ),
        )[0]

    if rule.rule_type == "highest_source_rank":
        return sorted(pool, key=lambda c: (c.global_priority, _recency_key(c.loaded_at)))[0]

    # source_priority (default) + custom fallback
    if rule.preferred_source_order:
        ordered = sorted(
            pool,
            key=lambda c: (*_preferred_rank(c, rule.preferred_source_order), _recency_key(c.loaded_at)),
        )
        return ordered[0]
    return sorted(pool, key=lambda c: (c.global_priority, _recency_key(c.loaded_at)))[0]


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
    representative_cache: Optional[dict[tuple, MdmEntityAttributeStage]] = None,
) -> MdmEntityAttributeStage:
    """Upsert a single source value into the staging table before survivorship
    runs, keyed on the natural key (entity_id, source_system, source_id,
    field_name) -- mirrors _register_source's MdmSourceRef upsert for the
    same (entity_id, source_system, source_id) grouping (base.py), which
    already has this natural key as its primary key.

    Without this, restaging the exact same source row (a resolver restart
    before its skip-if-unchanged check exists, or any future resolver that
    lacks one) inserted a fresh duplicate every time -- mdm_entity_
    attribute_stage has no pruning anywhere in this codebase, so the
    duplicates were permanent and every future run_survivorship_for_entity()
    call for that entity had to read the whole bloated history. Confirmed
    live in production: one heavily-refiled security's stage history
    reached 10,713-14,785+ rows from ~6 restarts before the skip-if-
    unchanged fix (mdm-resolver-skip-unchanged map) existed. That fix stops
    new duplicates for the resolvers it covers; this closes the same gap
    structurally, for every caller, including future ones.

    mdm-run-throughput Ticket 05: a distinct-but-related growth source --
    genuinely distinct ``source_id``s (real, separate transactions) that
    all confirm the exact same ``field_value``. Migration 012's natural key
    never collapses these (each has its own real source_id), so a heavily-
    refiled security's title gets re-staged as a brand-new row on every one
    of its thousands of ownership-transaction filings, even though the
    value never changes. Confirmed live: one entity had 5,048 rows, ALL
    identical value, ALL one source_system.

    ``_pick_by_rule`` (this module) needs, per (entity_id, field_name,
    source_system, global_priority, field_value) group, the row holding
    the group's true max effective_date AND the row holding the group's
    true max loaded_at -- NOT the same sort key for every rule type
    (caught by the mandatory Standards/Spec code-review pass, not the
    original design): only ``most_recent`` looks at effective_date at
    all; ``immutable``/``highest_source_rank``/``source_priority`` sort
    purely on ``(priority, loaded_at)`` and never touch it. Since priority
    is held fixed within a group, this reduces to two independent maxima,
    not one combined sort. Rather than retain two physical rows, both
    branches below fold both maxima onto ONE retained row -- forward-
    advance ``effective_date`` only when strictly greater (never
    regresses the group's true max), always refresh ``loaded_at`` to the
    latest confirmation (trivially always the group's max, since it's
    always "now") -- so the single row always holds both true maxima
    simultaneously, correct for every rule type without needing two rows.

    When ``representative_cache`` is provided (keyed by
    ``(entity_id, source_system, field_name, value_str, global_priority)``),
    a cache hit mutates the already-tracked ORM row in place with zero
    Postgres round trips -- built for ``MDMPipeline._run_grouped_concurrent``,
    where one group's rows share one session and process strictly
    sequentially, so holding a live ORM object across calls within the
    group is safe (no cross-session/cross-thread sharing, unlike
    ``ResolverContext.prefetched_source_refs``, which is read-only and
    shared read-only across worker threads). A cache miss falls back to one
    Postgres lookup (still far cheaper than the thousands of inserts it
    replaces) and populates the cache for the rest of the group.
    ``representative_cache=None`` (the default) preserves the exact
    pre-Ticket-05 behavior -- always insert a fresh row when no exact
    source_id match exists -- for any caller that hasn't opted in (e.g.
    run_companies' per-row, non-grouped path), deliberately avoiding a
    second Postgres round trip on every call for callers this fix's own
    `/gof-refactor-reviewer` pass flagged as not worth that cost without
    the cache.
    """
    priority = engine.get_source_priority(entity_type, source_system)
    value_str = None if field_value is None else str(field_value)
    now = datetime.now(timezone.utc)
    existing = session.execute(
        select(MdmEntityAttributeStage).where(
            MdmEntityAttributeStage.entity_id == entity_id,
            MdmEntityAttributeStage.source_system == source_system,
            MdmEntityAttributeStage.source_id == source_id,
            MdmEntityAttributeStage.field_name == field_name,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if representative_cache is not None:
            # This restage may change field_value out from under a
            # representative_cache entry keyed on the row's OLD value --
            # confirmed by the mandatory Standards code-review pass, not
            # caught by the original test suite. Without this pop, a later
            # brand-new source_id confirming that OLD value would hit the
            # stale cache entry and get merged into THIS row, which no
            # longer actually represents that value -- corrupting the row
            # (evidence pointer advanced to a source_id that never
            # confirmed the value now sitting in it). Only reachable when
            # the identical source_id is restaged mid-group with a changed
            # value (e.g. under reconciliation_pass, which bypasses
            # _skip_if_unchanged and can reprocess a row already seen
            # earlier in the same group) -- narrow, but real.
            stale_key = (entity_id, source_system, field_name, existing.field_value, existing.global_priority)
            if representative_cache.get(stale_key) is existing:
                del representative_cache[stale_key]
        existing.field_value = value_str
        existing.global_priority = priority
        existing.effective_date = effective_date
        existing.loaded_at = now
        existing.was_selected = False
        return existing

    rep_key: Optional[tuple] = None
    if representative_cache is not None:
        rep_key = (entity_id, source_system, field_name, value_str, priority)
        representative = representative_cache.get(rep_key)
        if representative is None:
            # mandatory Standards/Spec code-review pass, not the original
            # design: _pick_by_rule's 4 rule types do NOT share one sort
            # key. Only most_recent uses effective_date at all; immutable/
            # highest_source_rank/source_priority sort purely on
            # (priority, loaded_at) and never look at effective_date. A
            # naive ORDER BY effective_date DESC, loaded_at DESC LIMIT 1
            # can pick a row with a high effective_date but a STALE
            # loaded_at, silently discarding the group's true max-loaded_at
            # row (the one those 3 rule types actually need) if a legacy,
            # not-yet-backfilled group holds it on a different physical
            # row. Fetch every candidate (bounded, rare -- only reachable
            # once per distinct value per group per run, since a hit here
            # populates the cache for every subsequent call) and fold both
            # maxima onto the most-recently-loaded row, mirroring exactly
            # what the cache-hit branch below already does incrementally.
            candidates = list(session.execute(
                select(MdmEntityAttributeStage).where(
                    MdmEntityAttributeStage.entity_id == entity_id,
                    MdmEntityAttributeStage.source_system == source_system,
                    MdmEntityAttributeStage.field_name == field_name,
                    MdmEntityAttributeStage.field_value == value_str,
                    MdmEntityAttributeStage.global_priority == priority,
                )
            ).scalars().all())
            if candidates:
                representative = max(
                    candidates,
                    key=lambda r: (r.loaded_at is not None, r.loaded_at or _MIN_DATETIME),
                )
                true_max_effective_date = max(
                    (r.effective_date for r in candidates if r.effective_date is not None),
                    default=None,
                )
                if true_max_effective_date is not None and (
                    representative.effective_date is None
                    or true_max_effective_date > representative.effective_date
                ):
                    representative.effective_date = true_max_effective_date
        if representative is not None:
            if effective_date is not None and (
                representative.effective_date is None
                or effective_date > representative.effective_date
            ):
                representative.effective_date = effective_date
            representative.source_id = source_id
            representative.loaded_at = now
            representative.was_selected = False
            representative_cache[rep_key] = representative
            return representative

    row = MdmEntityAttributeStage(
        entity_id=entity_id,
        source_system=source_system,
        source_id=source_id,
        field_name=field_name,
        field_value=value_str,
        global_priority=priority,
        effective_date=effective_date,
    )
    session.add(row)
    if rep_key is not None:
        representative_cache[rep_key] = row
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
                loaded_at=r.loaded_at,
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
