"""Replay accepted identity decisions, never infer a merge from a field winner."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    """Carry retained commands to the common Rust decision replay."""
    from edgar_warehouse.rules.source_engine import replay_record_decisions

    try:
        state = replay_record_decisions({
            "identities": identities, "decisions": decisions, "as_of": as_of,
        })
    except ValueError as error:
        raise Conflict(str(error)) from None
    return IdentityState(
        state["canonical"], state["bindings"], [tuple(pair) for pair in state["exclusions"]],
        [decisions[i] for i in state["override_positions"]], set(state["retired"]), state["quarantined"],
    )
