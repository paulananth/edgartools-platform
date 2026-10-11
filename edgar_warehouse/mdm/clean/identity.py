"""Replay accepted identity decisions, never infer a merge from a field winner."""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence import instant
from .store import Conflict


@dataclass
class IdentityState:
    canonical: dict[str, str]
    bindings: dict[str, str]
    exclusions: list[tuple[str, str]]
    overrides: list[dict]
    retired_sources: set[str]
    # A record the rules could not decide (ticket 13): subject -> the Company
    # it was linked to, which readers see flagged. Left out of matching.
    quarantined: dict[str, str] = field(default_factory=dict)


def replay(identities: list[dict], decisions: list[dict], as_of: str) -> IdentityState:
    """Replay accepted commands in Rust; Python retains payloads and time semantics."""
    from edgar_warehouse.rules.source_engine import replay_identity

    clock = _micros(as_of)
    native_ids = [{"id": str(i["entity_id"]), "kind": i["kind"],
                   "published": _micros(str(i["published_at"]))} for i in identities]
    times = [_micros(d["at"]) for d in decisions]
    revoked = {d.get("target") for d, at in zip(decisions, times, strict=True)
               if at <= clock and d["operation"] in {"reverse", "revoke"}
               and isinstance(d.get("target"), str)}
    native_decisions = []
    for d, at in zip(decisions, times, strict=True):
        op = d["operation"]
        native_decisions.append({
            "id": d["decision_id"], "at": at, "op": op,
            "target": d.get("target"), "subject": d.get("subject"),
            "entity": str(d["entity_id"]) if "entity_id" in d else None,
            "entity_present": bool(d.get("entity_id")),
            "left": str(d["left"]) if "left" in d else None,
            "right": str(d["right"]) if "right" in d else None,
            "survivor": (d.get("survivor") or None) if op == "merge" else None,
            "source": d.get("source_code") if op == "retire_source" else None,
            # Future/withdrawn decisions and non-overrides do not interpret expiry.
            "expires": (_micros(d["expires_at"]) if op == "override" and at <= clock
                        and d["decision_id"] not in revoked and d.get("evidence")
                        and d.get("expires_at") else None),
            "evidence": bool(d.get("evidence")), "depends": d.get("depends_on", []) if op == "merge" else [],
        })
    try:
        state = replay_identity(native_ids, native_decisions, clock)
    except ValueError as error:
        raise Conflict(str(error)) from None
    return IdentityState(
        state["canonical"], state["bindings"], [tuple(pair) for pair in state["exclusions"]],
        [decisions[i] for i in state["overrides"]], set(state["retired"]), state["quarantined"],
    )


def _micros(value: str) -> int:
    # Integer datetime arithmetic preserves subsecond ordering even at year 9999.
    # Floats here would change reversal ordering for close, distant instants.
    from datetime import UTC, datetime

    delta = instant(value) - datetime(1970, 1, 1, tzinfo=UTC)
    return ((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
