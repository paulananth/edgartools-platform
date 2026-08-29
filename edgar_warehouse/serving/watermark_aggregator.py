"""Cross-stage Decision Watermark aggregator (change-propagation Ticket 41).

Observe-only: reads each stage's existing completion signal, writes one
alignment row per ``cause_reference``, rolls those rows up to
``business_date``, and calls ``evaluate_agent_grade``. Never drives or
repairs a stage — a stuck cause is repaired through that stage's own
mechanism, then this module picks up the new state on the next pass.

Stage readers are injected so tests do not open Snowflake. Ticket 09:
aggregator, not orchestrator; scheduled, not event-driven.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edgar_warehouse.mdm.publication import HARD_ALERT_AGE_SECONDS, WARNING_AGE_SECONDS
from edgar_warehouse.serving.decision_contract import AgentGradeResult, evaluate_agent_grade

STAGE_ORDER = ("silver", "mdm", "gold", "graph")


@dataclass(frozen=True)
class StageObservation:
    """One stage's completion signal for a single cause_reference."""

    complete: bool
    identity: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CauseAlignment:
    cause_reference: str
    business_date: str
    silver_complete: bool
    mdm_complete: bool
    gold_complete: bool
    graph_parity_ok: bool
    gold_run_id: str
    graph_generation_id: str
    aligned: bool
    stuck_stage: str | None
    first_seen_at: datetime
    aligned_at: datetime | None


@dataclass(frozen=True)
class AlignmentFreshness:
    """5-minute warning / 15-minute hard-alert, same thresholds as publication.py."""

    status: str
    oldest_unaligned_age_seconds: float | None
    oldest_unaligned_cause_reference: str | None
    stuck_stage: str | None


StageReader = Callable[[str], StageObservation]


class MemoryAlignmentStore:
    """In-process alignment rows. Durable SQLAlchemy store can implement the same methods."""

    def __init__(self) -> None:
        self._rows: dict[str, CauseAlignment] = {}

    def upsert(self, row: CauseAlignment) -> CauseAlignment:
        existing = self._rows.get(row.cause_reference)
        if existing is not None:
            row = CauseAlignment(
                cause_reference=row.cause_reference,
                business_date=row.business_date,
                silver_complete=row.silver_complete,
                mdm_complete=row.mdm_complete,
                gold_complete=row.gold_complete,
                graph_parity_ok=row.graph_parity_ok,
                gold_run_id=row.gold_run_id,
                graph_generation_id=row.graph_generation_id,
                aligned=row.aligned,
                stuck_stage=row.stuck_stage,
                first_seen_at=existing.first_seen_at,
                aligned_at=row.aligned_at,
            )
        self._rows[row.cause_reference] = row
        return row

    def get(self, cause_reference: str) -> CauseAlignment | None:
        return self._rows.get(cause_reference)

    def list_for_date(self, business_date: str) -> tuple[CauseAlignment, ...]:
        return tuple(
            row for row in self._rows.values() if row.business_date == business_date
        )

    def list_unaligned(self) -> tuple[CauseAlignment, ...]:
        return tuple(row for row in self._rows.values() if not row.aligned)


def _row_from_dict(payload: Mapping[str, object]) -> CauseAlignment:
    aligned_at = payload.get("aligned_at")
    return CauseAlignment(
        cause_reference=str(payload["cause_reference"]),
        business_date=str(payload["business_date"]),
        silver_complete=bool(payload["silver_complete"]),
        mdm_complete=bool(payload["mdm_complete"]),
        gold_complete=bool(payload["gold_complete"]),
        graph_parity_ok=bool(payload["graph_parity_ok"]),
        gold_run_id=str(payload.get("gold_run_id") or ""),
        graph_generation_id=str(payload.get("graph_generation_id") or ""),
        aligned=bool(payload["aligned"]),
        stuck_stage=(
            str(payload["stuck_stage"]) if payload.get("stuck_stage") else None
        ),
        first_seen_at=datetime.fromisoformat(str(payload["first_seen_at"])),
        aligned_at=(
            datetime.fromisoformat(str(aligned_at)) if aligned_at else None
        ),
    )


def _row_to_dict(row: CauseAlignment) -> dict[str, object]:
    return {
        "cause_reference": row.cause_reference,
        "business_date": row.business_date,
        "silver_complete": row.silver_complete,
        "mdm_complete": row.mdm_complete,
        "gold_complete": row.gold_complete,
        "graph_parity_ok": row.graph_parity_ok,
        "gold_run_id": row.gold_run_id,
        "graph_generation_id": row.graph_generation_id,
        "aligned": row.aligned,
        "stuck_stage": row.stuck_stage,
        "first_seen_at": row.first_seen_at.isoformat(),
        "aligned_at": row.aligned_at.isoformat() if row.aligned_at else None,
    }


class JsonAlignmentStore(MemoryAlignmentStore):
    """Durable alignment rows for a scheduled pass (Ticket 41 composite table)."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            for item in raw:
                row = _row_from_dict(item)
                self._rows[row.cause_reference] = row

    def upsert(self, row: CauseAlignment) -> CauseAlignment:
        stored = super().upsert(row)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [_row_to_dict(item) for item in self._rows.values()]
        self._path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return stored


def _stuck_stage(observations: Mapping[str, StageObservation]) -> str | None:
    for stage in STAGE_ORDER:
        if not observations[stage].complete:
            return stage
    return None


def reconcile_cause_reference(
    cause_reference: str,
    *,
    business_date: str,
    silver: StageReader,
    mdm: StageReader,
    gold: StageReader,
    graph: StageReader,
    store: MemoryAlignmentStore,
    now: datetime | None = None,
) -> CauseAlignment:
    """Watch four stages and persist one composite alignment row."""

    clock = now or datetime.now(UTC)
    observations = {
        "silver": silver(cause_reference),
        "mdm": mdm(cause_reference),
        "gold": gold(cause_reference),
        "graph": graph(cause_reference),
    }
    stuck = _stuck_stage(observations)
    aligned = stuck is None
    gold_id = observations["gold"].identity or ""
    graph_id = observations["graph"].identity or ""
    existing = store.get(cause_reference)
    first_seen = existing.first_seen_at if existing is not None else clock
    aligned_at: datetime | None
    if aligned:
        aligned_at = existing.aligned_at if existing is not None and existing.aligned else clock
    else:
        aligned_at = None
    return store.upsert(
        CauseAlignment(
            cause_reference=cause_reference,
            business_date=business_date,
            silver_complete=observations["silver"].complete,
            mdm_complete=observations["mdm"].complete,
            gold_complete=observations["gold"].complete,
            graph_parity_ok=observations["graph"].complete,
            gold_run_id=gold_id,
            graph_generation_id=graph_id,
            aligned=aligned,
            stuck_stage=stuck,
            first_seen_at=first_seen,
            aligned_at=aligned_at,
        )
    )


def compute_alignment_freshness(
    store: MemoryAlignmentStore, *, now: datetime | None = None
) -> AlignmentFreshness:
    clock = now or datetime.now(UTC)
    unaligned = sorted(store.list_unaligned(), key=lambda row: row.first_seen_at)
    if not unaligned:
        return AlignmentFreshness(
            status="normal",
            oldest_unaligned_age_seconds=None,
            oldest_unaligned_cause_reference=None,
            stuck_stage=None,
        )
    oldest = unaligned[0]
    age = (clock - oldest.first_seen_at).total_seconds()
    if age >= HARD_ALERT_AGE_SECONDS:
        status = "hard_alert"
    elif age >= WARNING_AGE_SECONDS:
        status = "warning"
    else:
        status = "normal"
    return AlignmentFreshness(
        status=status,
        oldest_unaligned_age_seconds=age,
        oldest_unaligned_cause_reference=oldest.cause_reference,
        stuck_stage=oldest.stuck_stage,
    )


def rollup_business_date(
    store: MemoryAlignmentStore,
    business_date: str,
) -> AgentGradeResult:
    """Fail-closed daily watermark from every cause_reference on that date."""

    rows = store.list_for_date(business_date)
    if not rows:
        return evaluate_agent_grade(
            {
                "business_date": business_date,
                "gold_run_id": "",
                "graph_generation_id": "",
                "silver_completeness_ok": False,
                "graph_parity_ok": False,
            }
        )
    all_aligned = all(row.aligned for row in rows)
    gold_ids = {row.gold_run_id for row in rows if row.gold_run_id}
    graph_ids = {row.graph_generation_id for row in rows if row.graph_generation_id}
    gold_run_id = next(iter(gold_ids)) if len(gold_ids) == 1 and all_aligned else ""
    graph_generation_id = (
        next(iter(graph_ids)) if len(graph_ids) == 1 and all_aligned else ""
    )
    return evaluate_agent_grade(
        {
            "business_date": business_date,
            "gold_run_id": gold_run_id,
            "graph_generation_id": graph_generation_id,
            "silver_completeness_ok": all_aligned,
            "graph_parity_ok": all_aligned and all(row.graph_parity_ok for row in rows),
        }
    )
