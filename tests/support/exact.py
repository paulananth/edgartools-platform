"""Exact JSON equality for engine tables: Python's `==` takes True for 1 and 0 for 0.0."""

from edgar_warehouse.control_contract import digest


def require_tables(actual, expected):
    if digest(actual) != digest(expected):
        raise ValueError('Company main tables differ in values or JSON scalar types')
