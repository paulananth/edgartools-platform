"""Durable advisory identity proposals; no master-writing capability here."""

from __future__ import annotations

from sqlalchemy import text

from .store import Conflict, canonical


class StaleAssessment(Conflict):
    """Reassess against current evidence; never copy cached winners forward."""


def record(store, body: dict, run_id: str, *, intent=None) -> dict:
    if getattr(store, "prepared", False):
        from .prepared import record as retain
        return retain(store, body, run_id, intent=intent)
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
    from .store import storage_adapter
    api = storage_adapter()
    if api.storage_version(conn) >= 5:
        import json
        held = api.Adapter(conn.engine, prefix="mdm_store", protocol=api.storage_version(conn)).read_proposal(key, connection=conn)
        if held is None:
            raise Conflict("Unknown identity assessment")
        return json.loads(bytes(held["body"]))
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
    if getattr(store, "prepared", False):
        from .store import storage_adapter
        storage_adapter().Adapter(store.engine, prefix="mdm_store", protocol=store.protocol).supersede_proposal(key, run_id)
        return
    # Outside the rolled-back master transaction. A concurrent successful
    # application wins; the SQL capability never supersedes an applied proposal.
    with store.engine.begin() as conn:
        store._authorize(conn)
        conn.execute(
            text("SELECT mdm.supersede_match_proposal(:key,CAST(:run AS uuid))"),
            {"key": key, "run": run_id},
        )
