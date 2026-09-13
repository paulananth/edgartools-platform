"""Warehouse READY path for the Mongo Decision Projection (ADR 0009).

Writes aggregator alignment, rolls up READY, then invokes the publisher.
``watermark_aggregator`` stays observe-only and must not import Mongo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from edgar_warehouse.serving.decision_contract import AgentGradeResult
from edgar_warehouse.serving.mongo_decision_projection import (
    PUBLICATION_READY,
    MongoDecisionStore,
    MongoPublishResult,
    publish_ready_issuer_documents,
)
from edgar_warehouse.serving.watermark_aggregator import (
    MemoryAlignmentStore,
    StageReader,
    reconcile_cause_reference,
    rollup_business_date,
)


def run_ready_mongo_projection(
    mongo_store: MongoDecisionStore,
    *,
    alignment_store: MemoryAlignmentStore,
    business_date: str,
    cause_references: Sequence[str],
    silver: StageReader,
    mdm: StageReader,
    gold: StageReader,
    graph: StageReader,
    issuers: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
) -> tuple[AgentGradeResult, MongoPublishResult]:
    """Reconcile causes, then project only if the rollup is READY."""

    for cause in cause_references:
        reconcile_cause_reference(
            cause,
            business_date=business_date,
            silver=silver,
            mdm=mdm,
            gold=gold,
            graph=graph,
            store=alignment_store,
            now=now,
        )
    grade = rollup_business_date(alignment_store, business_date)
    if not grade.agent_grade:
        return grade, MongoPublishResult(
            documents_written=0, documents_hidden=0, skip_reason="publication_not_ready"
        )
    wm = grade.watermark
    if wm is None:
        raise RuntimeError("agent-grade rollup missing watermark")
    result = publish_ready_issuer_documents(
        mongo_store,
        publication_status=PUBLICATION_READY,
        watermark_components=wm.to_dict(),
        issuers=issuers,
        now=now,
    )
    return grade, result
