"""Typed relationship projection from immutable source endpoints."""

from __future__ import annotations

from .evidence import instant
from edgar_warehouse.rules.source_engine import prepare_relationship_periods, prepare_relationships

from .catalog import CATALOG

# Compatibility for policies registered before relationship configuration.
TYPES_V0 = CATALOG["legacy_relationships"]
# The keys a type may carry, and the ultimate-parent algorithms this code runs.
_TYPE_KEYS = {"from", "to", "from_profile", "to_profile", "capacities", "hierarchy", "cycles", "one_parent",
              "ultimate_parent", "ultimate_type", "ends_parent_links", "keeps_start"}
# The type a derived ultimate parent is written as when its hierarchy names
# none: what every policy before profiling ticket 04b wrote.
CALCULATED_V0 = CATALOG["legacy_ultimate_type"]
# v1 walks the chain at the run date only; v2 keeps its history, a period for
# each stretch of time its chain held (profiling ticket 04b, part B).
ULTIMATE_PARENT_ALGORITHMS = {"accounting-chain-v1", "accounting-chain-v2"}
CYCLES = {"invalid", "review"}


def types_of(policy: dict) -> dict:
    """The relationship types a policy masters: its own, or the table every
    earlier policy used."""
    return policy["relationships"]["types"] if "relationships" in policy else TYPES_V0


def check_types(section: dict) -> None:
    """Refuse a relationship-types section that could not run exactly as written."""
    from .evidence import KINDS
    from .store import Conflict

    if not isinstance(section, dict) or set(section) != {"version", "types"} or not section.get("version"):
        raise Conflict("The relationships section holds a version and its types")
    if not isinstance(section["types"], dict) or not section["types"]:
        raise Conflict("The relationships section declares at least one type")
    for name, spec in section["types"].items():
        if not isinstance(name, str) or not name or not isinstance(spec, dict):
            raise Conflict(f"Relationship type {name!r} must be a name with its rules")
        if set(spec) - _TYPE_KEYS:
            raise Conflict(f"Relationship type {name} has an unknown key: {sorted(set(spec) - _TYPE_KEYS)}")
        for end in ("from", "to"):
            kinds = spec.get(end)
            if not isinstance(kinds, list) or not kinds:
                raise Conflict(f"Relationship type {name} names at least one kind at its {end} end")
            if set(kinds) - KINDS:
                raise Conflict(f"Relationship type {name} names an unknown kind: {sorted(set(kinds) - KINDS)}")
        if "capacities" in spec and (not isinstance(spec["capacities"], list) or not spec["capacities"]):
            raise Conflict(f"Relationship type {name}: capacities is a list of names")
        if spec.get("hierarchy"):
            if spec.get("cycles") not in CYCLES:
                raise Conflict(f"Relationship type {name}: a hierarchy says what its cycles do: invalid or review")
        elif {"cycles", "one_parent", "ultimate_parent"} & set(spec):
            raise Conflict(f"Relationship type {name}: cycles, one_parent and ultimate_parent go only on a hierarchy")
        if "ultimate_parent" in spec and spec["ultimate_parent"] not in ULTIMATE_PARENT_ALGORITHMS:
            raise Conflict(f"Relationship type {name}: unknown ultimate-parent algorithm {spec['ultimate_parent']}")
        if "ultimate_type" in spec and ("ultimate_parent" not in spec or spec["ultimate_type"] not in section["types"]):
            raise Conflict(f"Relationship type {name}: ultimate_type names a declared type, beside ultimate_parent")
        if "ends_parent_links" in spec and (spec["ends_parent_links"] is not True or spec.get("hierarchy")):
            raise Conflict(f"Relationship type {name}: ends_parent_links is true, on a link that is no parent")
        if "keeps_start" in spec and (spec["keeps_start"] is not True or spec.get("hierarchy")):
            raise Conflict(f"Relationship type {name}: keeps_start is true, on a link that is no parent")



# Waiting for another record does not require a steward decision.
WAITING = {"unresolved_endpoint", "unresolved_endpoint_identity"}


def fold_sightings(sightings: list[dict]) -> tuple[list[dict], list[dict]]:
    """Preserve the caller interface while Rust prepares relationship periods."""
    return prepare_relationship_periods(sightings)


def project(
    claims: dict, state, entities: dict, as_of: str, types: dict | None = None,
    *, stored: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """One Rust relationship calculation for every selected database."""
    return prepare_relationships({
        "claims": claims,
        "bindings": state.bindings,
        "canonical": state.canonical,
        "records": entities,
        "types": TYPES_V0 if types is None else types,
        "stored": stored or {},
        "as_of": as_of,
        "clock": instant(as_of).isoformat(),
        "default_ultimate_type": CALCULATED_V0,
    })
