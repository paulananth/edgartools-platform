"""Durable advisory identity proposals; no master-writing capability here."""

from __future__ import annotations


from .store import Conflict


class StaleAssessment(Conflict):
    """Reassess against current evidence; never copy cached winners forward."""


def record(store, body: dict, run_id: str, *, intent=None) -> dict:
    from .prepared import record as retain

    return retain(store, body, run_id, intent=intent)


def load(conn, key: str) -> dict:
    import json
    from .prepared_registry import require_installed

    held = require_installed(conn).read_proposal(key, connection=conn)
    if held is None:
        raise Conflict("Unknown identity assessment")
    return json.loads(bytes(held["body"]))


def stale(exc) -> bool:
    """Whether the save refused a proposal because it no longer holds: the
    batch computed now writes other than its effects, or it was applied or
    superseded meanwhile at the destination."""
    text_ = str(getattr(exc, "orig", exc))
    return "differs from assessed effects" in text_ or "requires a ready assessment" in text_


def supersede(store, key: str, run_id: str) -> None:
    from .store import storage_adapter
    from .prepared import authority, _refusals

    api = storage_adapter().Adapter(store.engine, prefix="mdm_store", protocol=store.protocol)
    _refusals(lambda: api.supersede_proposal(key, run_id, authority=authority(store)))
    return
