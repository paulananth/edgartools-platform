"""A Dataset Contract's reading for a test contract (Issue 20 L7).

A contract states a record's fields and matching values in its reading; a test
names each value by its path (or an address's parts by theirs) and this writes
the reading: blank text is no value, address parts are trimmed, and
`text=True` refuses a value that is not text.
"""

from __future__ import annotations


def _value(path: str, text: bool, trim: bool = False) -> dict:
    spec = {"path": path, "path_mode": "literal", "null_if_blank": True}
    if text:
        spec["type"] = "text"
    if trim:
        spec["trim"] = True
    return {"value": spec}


def _expression(spec, text: bool) -> dict:
    if isinstance(spec, str):
        return _value(spec, text)
    return {"object": {"fields": {part: _value(path, text, trim=True) for part, path in spec.items()},
                       "omit_nulls": True, "null_if_empty": True}}


def reading(fields: dict | None = None, matching: dict | None = None, *, text: bool = False) -> dict:
    """fields / matching: name -> a path, or an address's {part: path}."""
    def column(values):
        return {"object": {"fields": {name: _expression(spec, text) for name, spec in (values or {}).items()}}}

    return {"read": {"format": "json", "limits": {"max_bytes": 33554432, "max_records": 1},
                     "tables": {"mapped": {"each": ".", "columns": {"fields": column(fields),
                                                                    "matching": column(matching)}}}}}
