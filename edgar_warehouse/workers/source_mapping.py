"""Project one raw record with immutable configured reading.

No provider or MDM policy lives here. Callers choose a declared column so
unrelated projections cannot change their failure order.
"""
from __future__ import annotations

import json
from functools import lru_cache

from edgar_warehouse.rules.source_engine import SourceEngine, SourceRejected


@lru_cache(maxsize=128)
def _engine(body: str) -> SourceEngine:
    return SourceEngine(json.loads(body))


def project_record(row: dict, reading: dict, *, column: str) -> dict:
    # Serialize a fresh subset: mutable Rules bodies never become cache keys.
    body = json.loads(json.dumps(reading, ensure_ascii=False, allow_nan=False))
    tables = body.get("read", {}).get("tables", {})
    if set(tables) != {"mapped"} or column not in tables["mapped"].get("columns", {}):
        raise SourceRejected("contract", "record mapping requires one mapped table and the declared column")
    tables["mapped"]["columns"] = {column: tables["mapped"]["columns"][column]}
    key = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False)
    result = _engine(key).read(json.dumps(row, ensure_ascii=False, allow_nan=False).encode())
    rows = result.tables.get("mapped", [])
    if result.deferred or len(rows) != 1 or set(rows[0]) != {column} or not isinstance(rows[0][column], dict):
        raise SourceRejected("mapping_shape", "record projection must return one object without deferrals")
    return rows[0][column]
