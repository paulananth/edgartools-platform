"""Optional operator smoke for Atlas M0 (ticket 04). No CI secrets."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from edgar_warehouse.serving.mongo_decision_projection import (
    COLLECTION_ISSUER_BUNDLE,
    DATABASE_NAME,
    READINESS_AGENT_READY,
    MongoDecisionStore,
)
from edgar_warehouse.serving.mongo_ready_path import run_ready_mongo_projection
from edgar_warehouse.serving.watermark_aggregator import MemoryAlignmentStore, StageReader


@dataclass(frozen=True)
class MongoSmokeResult:
    documents_written: int
    agent_found_agent_grade: bool
    agent_write_rejected: bool
    found_cik: int | None = None


def run_mongo_decision_smoke(
    publisher: MongoDecisionStore,
    agent: MongoDecisionStore,
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
) -> MongoSmokeResult:
    """Publish as write user, find as read-only user, prove the agent cannot write."""

    _grade, published = run_ready_mongo_projection(
        publisher,
        alignment_store=alignment_store,
        business_date=business_date,
        cause_references=cause_references,
        silver=silver,
        mdm=mdm,
        gold=gold,
        graph=graph,
        issuers=issuers,
        now=now,
    )
    expected_cik = int(issuers[0]["subject_cik"]) if issuers else None
    found = _find_issuer(agent, expected_cik)
    agent_grade = bool(
        found
        and found.get("agent_grade") is True
        and found.get("readiness_state") == READINESS_AGENT_READY
    )
    found_cik = int(found["_id"]) if found and agent_grade else None
    probe = dict(found) if found else {"_id": expected_cik or 0, "agent_grade": False}
    write_rejected = False
    try:
        agent.replace_document(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE, probe)
    except Exception as exc:
        if _is_unauthorized(exc):
            write_rejected = True
        else:
            raise
    return MongoSmokeResult(
        documents_written=published.documents_written,
        agent_found_agent_grade=agent_grade,
        agent_write_rejected=write_rejected,
        found_cik=found_cik,
    )


def _find_issuer(agent: MongoDecisionStore, cik: int | None) -> Mapping[str, Any] | None:
    if cik is None:
        return None
    finder = getattr(agent, "find_document", None)
    if callable(finder):
        found = finder(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE, cik)
        return dict(found) if found else None
    for doc in agent.list_documents(DATABASE_NAME, COLLECTION_ISSUER_BUNDLE):
        if doc.get("_id") == cik:
            return dict(doc)
    return None


def _is_unauthorized(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    code = getattr(exc, "code", None)
    if code == 13:
        return True
    text = str(exc).lower()
    return "not authorized" in text or "unauthorized" in text
