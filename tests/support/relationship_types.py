"""A test policy's relationship types: the RDM code set the repo policy pins
(ticket 132). A policy without them is refused when it masters."""

from edgar_warehouse.rules import files


def with_relationship_types(body: dict) -> dict:
    """The policy body with the repo's pinned relationship types."""
    return {**body, "relationships": {"pin": "mdm-relationship-types"},
            "reference_pins": {**body.get("reference_pins", {}),
                               "mdm-relationship-types": files.reference_pin("mdm-relationship-types")}}
