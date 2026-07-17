"""Decision Watermark + Agent-Grade gate (ticket 09 / ADR 0001).

Pure validation of a composite Decision Watermark. Callers publish component
values from silver completeness claims, gold run_id, graph generation, and
reconcile disposition; this module fail-closes when anything required is missing
or misaligned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

DECISION_CONTRACT_VERSION = "1"

# Required watermark components for agent-grade issuer reads
REQUIRED_COMPONENTS = (
    "business_date",
    "gold_run_id",
    "graph_generation_id",
    "silver_completeness_ok",
    "graph_parity_ok",
)


@dataclass(frozen=True)
class DecisionWatermark:
    """Composite identity for an Agent-Grade Read."""

    business_date: str
    gold_run_id: str
    graph_generation_id: str
    silver_completeness_ok: bool
    graph_parity_ok: bool
    decision_contract_version: str = DECISION_CONTRACT_VERSION
    # Optional / conditional
    bronze_content_hashes: tuple[str, ...] = ()
    bronze_persist_used: bool = False
    high_severity_reconcile_open: bool = False
    reconcile_waived: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentGradeResult:
    """Outcome of validating a watermark for agent use."""

    agent_grade: bool
    decision_contract_version: str
    watermark: DecisionWatermark | None
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_grade": self.agent_grade,
            "decision_contract_version": self.decision_contract_version,
            "watermark": self.watermark.to_dict() if self.watermark else None,
            "reasons": list(self.reasons),
        }


def build_decision_watermark(components: Mapping[str, Any]) -> DecisionWatermark:
    """Build a watermark from a published component map (missing keys → empty/false)."""
    hashes = components.get("bronze_content_hashes") or ()
    if isinstance(hashes, list):
        hashes = tuple(str(h) for h in hashes)
    notes = components.get("notes") or ()
    if isinstance(notes, list):
        notes = tuple(str(n) for n in notes)
    return DecisionWatermark(
        business_date=str(components.get("business_date") or "").strip(),
        gold_run_id=str(components.get("gold_run_id") or "").strip(),
        graph_generation_id=str(components.get("graph_generation_id") or "").strip(),
        silver_completeness_ok=bool(components.get("silver_completeness_ok")),
        graph_parity_ok=bool(components.get("graph_parity_ok")),
        decision_contract_version=str(
            components.get("decision_contract_version") or DECISION_CONTRACT_VERSION
        ),
        bronze_content_hashes=tuple(hashes),
        bronze_persist_used=bool(components.get("bronze_persist_used")),
        high_severity_reconcile_open=bool(components.get("high_severity_reconcile_open")),
        reconcile_waived=bool(components.get("reconcile_waived")),
        notes=tuple(notes),
    )


def evaluate_agent_grade(components: Mapping[str, Any]) -> AgentGradeResult:
    """Fail-closed Agent-Grade evaluation.

    Rules:
    - All identity fields non-empty
    - silver_completeness_ok and graph_parity_ok must be True
    - high_severity reconcile findings block unless reconcile_waived
    - bronze hashes required only when bronze_persist_used
    """
    wm = build_decision_watermark(components)
    reasons: list[str] = []

    if not wm.business_date:
        reasons.append("missing business_date")
    if not wm.gold_run_id:
        reasons.append("missing gold_run_id")
    if not wm.graph_generation_id:
        reasons.append("missing graph_generation_id")
    if not wm.silver_completeness_ok:
        reasons.append("silver_completeness_ok is false")
    if not wm.graph_parity_ok:
        reasons.append("graph_parity_ok is false (verify-graph / parity required)")
    if wm.high_severity_reconcile_open and not wm.reconcile_waived:
        reasons.append("open high-severity reconcile findings (not waived)")
    if wm.bronze_persist_used and not wm.bronze_content_hashes:
        reasons.append("bronze_persist_used but bronze_content_hashes empty")
    if not wm.bronze_persist_used and wm.bronze_content_hashes:
        reasons.append("bronze_content_hashes present without bronze_persist_used")

    agent_grade = len(reasons) == 0
    return AgentGradeResult(
        agent_grade=agent_grade,
        decision_contract_version=wm.decision_contract_version,
        watermark=wm if agent_grade or True else wm,  # always attach watermark for audit
        reasons=tuple(reasons),
    )
