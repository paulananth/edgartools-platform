"""Exact JSON comparison for engine output: Python's `==` takes True for 1 and 0 for 0.0,
and ignores key order."""

from edgar_warehouse.control_contract import digest


def require_tables(actual, expected):
    if digest(actual) != digest(expected):
        raise ValueError('Company main tables differ in values or JSON scalar types')


def ordered(value):
    """Type and captured key order, including objects nested in arrays."""
    if isinstance(value, dict):
        return ["object", [[key, ordered(item)] for key, item in value.items()]]
    if isinstance(value, list):
        return ["array", [ordered(item) for item in value]]
    return [type(value).__name__, value]
