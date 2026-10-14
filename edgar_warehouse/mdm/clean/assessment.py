"""Durable advisory identity proposals; no master-writing capability here."""

from __future__ import annotations

from sqlalchemy import text

from .store import Conflict, canonical


class StaleAssessment(Conflict):
    """Reassess against current evidence; never copy cached winners forward."""


def record(store, body: dict, run_id: str) -> dict:
    with store.engine.begin() as conn:
        store._authorize(conn)
        key = record_in(conn, body, run_id)
    return {"assessment_id": key, **body}


def record_in(conn, body: dict, run_id: str) -> str:
    """Record a proposal in the caller's transaction; its key."""
    return conn.scalar(
        text("SELECT mdm.record_match_proposal(:body,CAST(:run AS uuid))"),
        {"body": canonical(body), "run": run_id},
    )


def load(conn, key: str) -> dict:
    body = conn.scalar(
        text("SELECT body FROM mdm.match_proposal WHERE assessment_id=:key"),
        {"key": key},
    )
    if body is None:
        raise Conflict("Unknown identity assessment")
    return body


def stale(exc) -> bool:
    """Whether the save refused a proposal because it no longer holds: the
    batch computed now writes other than its effects, or it was applied or
    superseded meanwhile (`save_batch`)."""
    text_ = str(getattr(exc, "orig", exc))
    return "differs from assessed effects" in text_ or "requires a ready assessment" in text_


def supersede(store, key: str, run_id: str) -> None:
    # Outside the rolled-back master transaction. A concurrent successful
    # application wins; the SQL capability never supersedes an applied proposal.
    with store.engine.begin() as conn:
        store._authorize(conn)
        conn.execute(
            text("SELECT mdm.supersede_match_proposal(:key,CAST(:run AS uuid))"),
            {"key": key, "run": run_id},
        )
