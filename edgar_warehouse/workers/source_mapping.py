"""Project one raw record with immutable configured reading.

No provider or MDM policy lives here. Callers choose a declared column so
unrelated projections cannot change their failure order.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


@lru_cache(maxsize=128)
def _engine(body: str) -> SourceEngine:
    return SourceEngine(json.loads(body))


def _require_json_value(value):
    """Reject Python-only shapes that json.dumps would silently convert."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("configured record dictionary keys must be strings")
        for item in value.values():
            _require_json_value(item)
    elif type(value) is list:
        for item in value:
            _require_json_value(item)
    elif value is not None and type(value) not in (str, bool, int, float):
        raise TypeError("configured record values must belong to the JSON domain")


def read_record(row: dict, reading: dict):
    """Evaluate a JSON record through cached immutable Rules, without callbacks."""
    _require_json_value(row)
    key = json.dumps(reading, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return _engine(key).read(json.dumps(row, ensure_ascii=False, allow_nan=False).encode())


def project_record(row: dict, reading: dict, *, column: str) -> dict:
    # Serialize a fresh subset: mutable Rules bodies never become cache keys.
    body = json.loads(json.dumps(reading, ensure_ascii=False, allow_nan=False))
    tables = body.get("read", {}).get("tables", {})
    if set(tables) != {"mapped"} or column not in tables["mapped"].get("columns", {}):
        raise SourceRejected("contract", "record mapping requires one mapped table and the declared column")
    # Validate every declared expression, even in columns not evaluated now.
    # Full compilation is cached by immutable content; runtime remains selective.
    _engine(json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False))
    tables["mapped"]["columns"] = {column: tables["mapped"]["columns"][column]}
    inputs = body.get("input_fields")
    if "input_fields" in body:
        if (not isinstance(inputs, list) or not 1 <= len(inputs) <= 128
                or any(not isinstance(name, str) or len(name) > 128
                       or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in inputs)
                or len(set(inputs)) != len(inputs)):
            raise SourceRejected("contract", "input_fields requires 1..128 distinct root identifiers")
        # Declare the JSON projection boundary: foreign metadata outside this
        # list never becomes parsed content. Selected values are never coerced.
        row = {name: row[name] for name in inputs if name in row}
    result = read_record(row, body)
    rows = result.tables.get("mapped", [])
    if result.deferred or len(rows) != 1 or set(rows[0]) != {column} or not isinstance(rows[0][column], dict):
        raise SourceRejected("mapping_shape", "record projection must return one object without deferrals")
    return rows[0][column]
