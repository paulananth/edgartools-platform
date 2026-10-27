"""A test policy's relationship types: the RDM code set the repo policy pins
(ticket 132). A policy without them is refused when it masters."""

from edgar_warehouse.rules import files


def with_relationship_types(body: dict) -> dict:
    """The policy body with the repo's pinned relationship types."""
    return {**body, "relationships": {"pin": "mdm-relationship-types"},
            "reference_pins": {**body.get("reference_pins", {}),
                               "mdm-relationship-types": files.reference_pin("mdm-relationship-types")}}


def codes_of(types: dict) -> list[dict]:
    """Relationship types written as the code set's rows: each type a code whose
    properties are its rules, each capacity a child code `TYPE:capacity`."""
    rows = []
    for name, spec in types.items():
        rows.append({"code": name, "parent_code": None, "status": "valid",
                     "properties": {k: v for k, v in spec.items() if k != "capacities"}})
        rows += [{"code": f"{name}:{c}", "parent_code": name, "status": "valid"} for c in spec.get("capacities", [])]
    return rows


def read_types(types: dict) -> dict:
    """The types as the Rust engine reads them from code rows; ValueError names a refusal."""
    from edgar_warehouse.mdm.clean.evidence import KINDS
    from edgar_warehouse.rules.source_engine import prepare_relationship_types

    return prepare_relationship_types(codes_of(types), sorted(KINDS))
