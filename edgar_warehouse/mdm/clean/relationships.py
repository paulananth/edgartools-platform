"""Typed relationship projection from immutable source endpoints."""

from __future__ import annotations

from .evidence import instant
from edgar_warehouse.rules.source_engine import prepare_relationship_periods, prepare_relationships



def types_of(policy: dict) -> dict:
    """The relationship types a policy masters: the RDM code set it pins under
    `relationships` (ticket 132), read and checked by the Rust engine. A policy
    pinning none is refused."""
    from edgar_warehouse.rules import files
    from edgar_warehouse.rules.source_engine import prepare_relationship_types
    from .evidence import KINDS
    from .store import Conflict

    section = policy.get("relationships")
    if not isinstance(section, dict) or set(section) != {"pin"}:
        raise Conflict("The policy pins no relationship types")
    pin = (policy.get("reference_pins") or {}).get(section["pin"])
    if not isinstance(pin, dict):
        raise Conflict(f"The policy pins no reference data named {section['pin']}")
    try:
        return prepare_relationship_types(files.published_reference(pin), sorted(KINDS))
    except (ValueError, files.RulesFileError) as error:
        raise Conflict(str(error)) from None


def check_types(types: dict) -> None:
    """Refuse types the Rust engine could not run exactly as written."""
    from edgar_warehouse.rules.source_engine import check_relationship_types
    from .evidence import KINDS
    from .store import Conflict

    try:
        check_relationship_types(types, sorted(KINDS))
    except ValueError as error:
        raise Conflict(str(error)) from None


# Waiting for another record does not require a steward decision.
WAITING = {"unresolved_endpoint", "unresolved_endpoint_identity"}


def fold_sightings(sightings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Preserve the caller interface while Rust prepares relationship periods."""
    return prepare_relationship_periods(sightings)


def project(
    claims: dict, state, entities: dict, as_of: str, types: dict,
    *, stored: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """One Rust relationship calculation for every selected database."""
    return prepare_relationships({
        "claims": claims,
        "bindings": state.bindings,
        "canonical": state.canonical,
        "records": entities,
        "types": types,
        "stored": stored or {},
        "as_of": as_of,
        "clock": instant(as_of).isoformat(),
    })
