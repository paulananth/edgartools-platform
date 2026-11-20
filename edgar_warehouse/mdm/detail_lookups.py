"""A configured lookup from a detail row's key to every current master holding
it (ticket 138). The kind, detail list and keys are configuration
(`detail_lookups` in the engine catalog); lookup only, never matching."""


def configuration():
    from .catalog import CATALOG, assert_current
    assert_current()
    return CATALOG.get("detail_lookups")


def keys_of(body, spec):
    """Each configured key a master's detail rows state in full: [name, *values]."""
    found = set()
    for row in (body.get("details") or {}).get(spec["detail"], []):
        for name, fields in spec["keys"].items():
            values = [row.get(field) for field in fields]
            if all(isinstance(value, str) and value for value in values):
                found.add((name, *values))
    return sorted(list(key) for key in found)
