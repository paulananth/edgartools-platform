"""Mongo Decision Projection publisher (ADR 0009).

Writes READY Snowflake Decision Contract facts as documents a v2 agent
can read. This is not a ServingTarget (those write gold Parquet for
Snowflake native pull) and not a second Agent System of Engagement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol, Sequence

from edgar_warehouse.serving.decision_contract import (
    DECISION_CONTRACT_VERSION,
    AgentGradeResult,
    evaluate_agent_grade,
)

PUBLICATION_READY = "ready"
DATABASE_NAME = "edgartools_decision"
COLLECTION_ISSUER_BUNDLE = "issuer_subject_bundle"
COLLECTION_FEATURE_SCREEN = "subject_feature_screen"
READINESS_AGENT_READY = "agent_ready"
READINESS_NOT_READY = "not_ready"
PROJECTED_FROM = "snowflake_decision_contract"


@dataclass(frozen=True)
class MongoPublishResult:
    documents_written: int
    documents_hidden: int = 0
    skip_reason: str | None = None


class MongoDecisionStore(Protocol):
    def replace_document(
        self, database: str, collection: str, document: Mapping[str, Any]
    ) -> None:
        """Upsert one document. Identity is ``document['_id']`` (int CIK)."""

    def list_documents(
        self, database: str, collection: str
    ) -> Sequence[Mapping[str, Any]]:
        """Return current documents in one collection (no deletes)."""


def bronze_content_digest(hashes: Sequence[str]) -> str:
    """Digest of ordered unique Bronze content hashes (CONTEXT Decision Watermark)."""
    seen: list[str] = []
    for raw in hashes:
        item = str(raw)
        if item not in seen:
            seen.append(item)
    return hashlib.sha256("\n".join(seen).encode("utf-8")).hexdigest()


def publish_ready_issuer_documents(
    store: MongoDecisionStore,
    *,
    publication_status: str,
    watermark_components: Mapping[str, Any],
    issuers: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
) -> MongoPublishResult:
    """Project READY issuer bundles and Feature Screen rows.

    Writes nothing when ``publication_status`` is not READY or the watermark
    is not agent-grade. ``issuers`` entries have ``subject_cik``, ``bundle``,
    and ``feature_screen_row``.
    """
    if publication_status != PUBLICATION_READY:
        return MongoPublishResult(
            documents_written=0, skip_reason="publication_not_ready"
        )
    grade = evaluate_agent_grade(watermark_components)
    if not grade.agent_grade:
        return MongoPublishResult(documents_written=0, skip_reason="not_agent_grade")

    current_generation = str(
        (grade.watermark.graph_generation_id if grade.watermark else "")
    )
    hidden = _hide_retired_generation(store, current_generation)

    clock = now if now is not None else datetime.now(UTC)
    shared = _shared_identity(watermark_components, grade, clock)
    written = 0
    for issuer in issuers:
        cik = int(issuer["subject_cik"])
        bundle_doc = dict(issuer["bundle"])
        bundle_doc.update(shared)
        bundle_doc["_id"] = cik
        bundle_doc["bundle_subject_cik"] = cik
        store.replace_document(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE, bundle_doc)
        written += 1

        screen_doc = dict(issuer["feature_screen_row"])
        screen_doc.pop("rows", None)
        screen_doc.pop("universe_size", None)
        screen_doc.update(shared)
        screen_doc["_id"] = cik
        screen_doc["cik"] = cik
        store.replace_document(DATABASE_NAME, COLLECTION_FEATURE_SCREEN, screen_doc)
        written += 1

    return MongoPublishResult(
        documents_written=written, documents_hidden=hidden, skip_reason=None
    )


def _hide_retired_generation(store: MongoDecisionStore, current_generation: str) -> int:
    """Stamp prior generations not_ready in place. Never deletes."""
    hidden = 0
    for collection in (COLLECTION_ISSUER_BUNDLE, COLLECTION_FEATURE_SCREEN):
        for doc in store.list_documents(DATABASE_NAME, collection):
            wm = doc.get("decision_watermark") or {}
            if str(wm.get("graph_generation_id") or "") == current_generation:
                continue
            if doc.get("readiness_state") != READINESS_AGENT_READY:
                continue
            updated = dict(doc)
            updated["agent_grade"] = False
            updated["readiness_state"] = READINESS_NOT_READY
            store.replace_document(DATABASE_NAME, collection, updated)
            hidden += 1
    return hidden


def _shared_identity(
    components: Mapping[str, Any],
    grade: AgentGradeResult,
    clock: datetime,
) -> dict[str, Any]:
    wm = grade.watermark
    if wm is None:
        raise RuntimeError("agent-grade result missing watermark")
    hashes = list(components.get("bronze_content_hashes") or ())
    digest = bronze_content_digest(hashes) if hashes else None
    return {
        "decision_contract_version": grade.decision_contract_version
        or DECISION_CONTRACT_VERSION,
        "agent_grade": True,
        "readiness_state": READINESS_AGENT_READY,
        "decision_watermark": {
            "business_date": wm.business_date,
            "gold_run_id": wm.gold_run_id,
            "graph_generation_id": wm.graph_generation_id,
            "decision_contract_version": wm.decision_contract_version,
            "bronze_content_digest": digest,
            "silver_completeness_ok": wm.silver_completeness_ok,
            "graph_parity_ok": wm.graph_parity_ok,
        },
        "projected_from": PROJECTED_FROM,
        "projected_at": clock.astimezone(UTC).isoformat(),
    }
