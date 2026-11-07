"""silver.land: one reading's table into a silver table (ticket 169).

The unit's input is a `source.read` output (normally `from` the run's read
step). Its keys say what to take from it:

- `table`: the reading's table whose rows land;
- `silver`: the registered silver table they land in.

The worker calls the existing silver writer (`land`) once for each artifact
of the reading, so a table with `append` load mode lands each filer's rows
exactly once, and a retry lands the same rows again with no change. SILVER_DATABASE_URL
is the silver login; MDM_DATABASE_URL, when set,
finds each linked master's id. Its output is a receipt naming what the
reading held: rows, distinct keys and a digest of the keys. The verifier reads
the reading again, rebuilds the receipt, and reads silver with its own login to
confirm the table holds at least that many distinct keys.
"""
from __future__ import annotations

import hashlib
import json
import os

from edgar_warehouse.workers import source_readings

CHECK = "silver.landed"
KEYS = {"table", "silver"}
INPUT_BYTES = 16 * 1024**3
INPUT_ROWS = 100_000_000


def _artifacts(envelope: dict, artifacts):
    """Each piece of the unit's reading, in order; the byte and row budgets are spent across all of them."""
    consumed = rows = 0
    for artifact, used in source_readings.iter_pieces(
            envelope["input"], artifacts, max_bytes=INPUT_BYTES - consumed, max_rows=INPUT_ROWS - rows,
            allow_lookup_receipts=True):
        rows += sum(len(t) for t in artifact["tables"].values() if isinstance(t, list))
        if rows > INPUT_ROWS:
            raise ValueError("silver.land readings exceed their row budget")
        consumed = used
        yield artifact


def _rows(artifact: dict, keys: dict) -> list[dict]:
    found = artifact["tables"].get(keys["table"])
    if found is None:
        raise ValueError(f"The reading has no table {keys['table']}")
    if not isinstance(found, list) or any(not isinstance(row, dict) for row in found):
        raise ValueError("silver.land table rows must be objects")
    return found


def _keys(envelope: dict) -> dict:
    keys = envelope["keys"]
    if not KEYS <= set(keys):
        raise ValueError(f"silver.land needs the unit keys {sorted(KEYS)}")
    return keys


def _tuple(row: dict, spec: dict) -> tuple:
    return tuple(str(row.get(name)) for name in spec["key"])


def _receipt(count: int, seen: set) -> bytes:
    """What the reading held for the table: rows, distinct keys and a digest of them."""
    digest = hashlib.sha256(json.dumps(sorted(seen), separators=(",", ":")).encode()).hexdigest()
    return json.dumps({"version": 1, "rows": count, "distinct_keys": len(seen), "keys_sha256": digest},
                      sort_keys=True, separators=(",", ":")).encode()


def engines():
    from edgar_warehouse.database_connections import engine_from_env

    silver = engine_from_env("SILVER_DATABASE_URL")
    mdm = engine_from_env("MDM_DATABASE_URL") if os.environ.get("MDM_DATABASE_URL") else None
    return silver, mdm


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.silver_writer.relational import DatabaseSink
    from edgar_warehouse.silver_writer.writer import MdmIds, land

    if set(envelope["checks"]) != {CHECK}:
        raise ValueError(f"silver.land verifies {CHECK} only")
    keys = _keys(envelope)
    silver, mdm = engines()
    try:
        sink, ids = DatabaseSink(silver), MdmIds(mdm) if mdm is not None else None
        spec = sink.spec(keys["silver"])
        count, seen = 0, set()
        for artifact in _artifacts(envelope, artifacts):  # one pass: what lands is what the receipt counts
            rows = _rows(artifact, keys)
            land(sink, keys["silver"], rows, ids)
            count += len(rows)
            seen.update(_tuple(row, spec) for row in rows)
        return artifacts.put_bytes(envelope["output"], _receipt(count, seen))
    finally:
        silver.dispose()
        if mdm is not None:
            mdm.dispose()


def _missing(engine, spec: dict, wanted: set) -> int:
    """How many of the unit's own keys silver lacks. Silver is asked only for the rows of the unit's
    first-key values (a filer, say), in groups, so other units' rows cannot hide a missing one."""
    from sqlalchemy import text

    columns = ", ".join(f'"{name}"::text' for name in spec["key"])
    first = spec["key"][0]
    values = sorted({key[0] for key in wanted})
    held = set()
    with engine.connect() as conn:
        for start in range(0, len(values), 500):
            held.update(tuple(row) for row in conn.execute(
                text(f'select {columns} from silver."{spec["table"]}" where "{first}"::text = any(:values)'),
                {"values": values[start:start + 500]}))
    return len(wanted - held)


def verify(envelope: dict, artifacts) -> tuple[dict, list]:
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    keys = _keys(envelope)
    silver, _ = engines()
    try:
        spec = DatabaseSink(silver).spec(keys["silver"])
        count, seen = 0, set()
        for artifact in _artifacts(envelope, artifacts):
            rows = _rows(artifact, keys)
            count += len(rows)
            seen.update(_tuple(row, spec) for row in rows)
        if artifacts.verified(envelope["candidate"]) != _receipt(count, seen):
            raise ValueError("The receipt differs from the reading")
        if _missing(silver, spec, seen):
            raise ValueError("Silver lacks keys the reading holds")
    finally:
        silver.dispose()
    return {CHECK: True}, []
