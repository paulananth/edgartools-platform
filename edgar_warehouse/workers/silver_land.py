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
reading held: rows, distinct keys and a digest of the keys. The check reads
the reading again, rebuilds the receipt, and reads silver to
confirm the table holds at least that many distinct keys.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from edgar_warehouse.workers import source_readings

CHECK = "silver.landed"
QUALITY_CHECK = "silver.quality.evidence.v2"
QUALITY_V2_GATE = "SILVER_QUALITY_EVIDENCE_V2"
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


def _receipt(count: int, seen: set, quality: dict | None = None) -> bytes:
    """What the reading held for the table: rows, distinct keys and a digest of them."""
    digest = hashlib.sha256(json.dumps(sorted(seen), separators=(",", ":")).encode()).hexdigest()
    receipt = {"version": 2 if quality is not None else 1, "rows": count,
               "distinct_keys": len(seen), "keys_sha256": digest}
    if quality is not None:
        receipt["quality"] = quality
    return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()


def _quality_identity(envelope: dict, table: str, spec: dict) -> dict:
    """Stable, source-value-free identity for one work unit's executed checks."""
    claim = envelope.get("claim") or {}
    fields = ("run_id", "step", "key")
    if any(not isinstance(claim.get(field), str) or not claim[field] for field in fields):
        raise ValueError("Version-2 quality evidence requires the Bookkeeping run, step and unit")
    # Bookkeeping keys can contain provider record identifiers. Keep a stable,
    # opaque reference so a result can be correlated back to the unit without
    # copying any source key into the receipt or catalog.
    # The identity names the work unit, never the attempt: a unit re-executed
    # after a lost report writes the same receipt to the same immutable output,
    # so the observation time already written for it is reused.
    binding = json.dumps([claim[field] for field in fields], separators=(",", ":")).encode()
    unit_ref = hashlib.sha256(binding).hexdigest()[:24]
    return {"run_id": claim["run_id"], "step": claim["step"], "work_unit_ref": unit_ref, "table": table,
            "checks": [{"id": item["id"], "kind": item["check"], "failure_action": item["on_fail"]}
                       for item in spec.get("checks") or []]}


def _quality_observation(identity: dict, reports: list[dict], at: str) -> dict:
    """Deterministically combine per-artifact check counts for this work unit."""
    by_id = {item["id"]: {"kind": item["kind"], "failure_action": item["failure_action"],
                          "rows_checked": 0, "rows_failed": 0}
             for item in identity["checks"]}
    checked = flagged = refused = 0
    for report in reports:
        if not report:
            continue
        checked += report["rows_checked"]
        flagged += report["rows_flagged"]
        refused += report["rows_refused"]
        for check_id, outcome in report["checks"].items():
            if check_id not in by_id or outcome["on_fail"] != by_id[check_id]["failure_action"]:
                raise ValueError("Executed quality results differ from the registered silver checks")
            by_id[check_id]["rows_checked"] += report["rows_checked"]
            by_id[check_id]["rows_failed"] += outcome["rows_failed"]
    return {**identity, "observed_at": at,
            "rows_checked": checked, "rows_flagged": flagged, "rows_refused": refused,
            "checks": by_id}


def _retained_observation(envelope: dict, artifacts, identity: dict) -> str | None:
    """The observation time already written for this work unit, when an earlier
    attempt wrote its receipt and its report was lost. The receipt is immutable
    and names the work unit, so a re-execution reuses that time and writes the
    same bytes; a receipt of another unit is never reused."""
    try:
        retained = artifacts.read(envelope["output"])
    except ValueError:  # no receipt has been written for this unit yet
        return None
    try:
        receipt = json.loads(retained)
    except (TypeError, json.JSONDecodeError):
        return None
    quality = receipt.get("quality") if isinstance(receipt, dict) and receipt.get("version") == 2 else None
    if not isinstance(quality, dict):
        return None
    if (quality.get("run_id"), quality.get("step"), quality.get("work_unit_ref")) != (
            identity["run_id"], identity["step"], identity["work_unit_ref"]):
        return None
    observed_at = quality.get("observed_at")
    return observed_at if isinstance(observed_at, str) and observed_at else None


def _recomputed_quality(identity: dict, artifacts, envelope: dict, keys: dict, spec: dict, at: str) -> dict:
    """Recompute outcomes from original unit rows; never read the mutable latest-results file."""
    from edgar_warehouse.silver_writer.checks import run

    reports = []
    for artifact in _artifacts(envelope, artifacts):
        _, report = run(spec, _rows(artifact, keys))
        reports.append(report)
    return _quality_observation(identity, reports, at)


def engines():
    from edgar_warehouse.database_connections import engine_from_env

    silver = engine_from_env("SILVER_DATABASE_URL")
    mdm = engine_from_env("MDM_DATABASE_URL") if os.environ.get("MDM_DATABASE_URL") else None
    return silver, mdm


def execute(envelope: dict, artifacts) -> dict:
    from edgar_warehouse.silver_writer.relational import DatabaseSink
    from edgar_warehouse.silver_writer.writer import MdmIds, land

    requested = set(envelope["checks"])
    if requested not in ({CHECK}, {CHECK, QUALITY_CHECK}):
        raise ValueError(f"silver.land verifies {CHECK} only, with optional {QUALITY_CHECK}")
    quality_enabled = QUALITY_CHECK in requested
    if quality_enabled and os.environ.get(QUALITY_V2_GATE) != "enabled":
        raise ValueError(f"Version-2 quality evidence is disabled until recovery gates are met; "
                         f"set {QUALITY_V2_GATE}=enabled only after qualification")
    keys = _keys(envelope)
    silver, mdm = engines()
    try:
        sink, ids = DatabaseSink(silver), MdmIds(mdm) if mdm is not None else None
        spec = sink.spec(keys["silver"])
        count, seen = 0, set()
        quality_reports = []
        for artifact in _artifacts(envelope, artifacts):  # one pass: what lands is what the receipt counts
            rows = _rows(artifact, keys)
            # The mutable legacy results file is for direct silver runs only;
            # Bookkeeping has its own immutable, attempt-bound receipt.
            landed = land(sink, keys["silver"], rows, ids, record_quality_results=False)
            count += len(rows)
            seen.update(_tuple(row, spec) for row in rows)
            if landed.get("quality") is not None:
                quality_reports.append(landed["quality"])
        quality = None
        if quality_enabled:
            identity = _quality_identity(envelope, keys["silver"], spec)
            observed_at = (_retained_observation(envelope, artifacts, identity)
                           or datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
            quality = _quality_observation(identity, quality_reports, observed_at)
        return artifacts.put_bytes(envelope["output"], _receipt(count, seen, quality))
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


def check(envelope: dict, artifacts) -> tuple[dict, list]:
    from edgar_warehouse.silver_writer.relational import DatabaseSink

    if envelope["candidate"]["uri"] != envelope["output"]:
        raise ValueError("Candidate URI differs from the intended output")
    requested = set(envelope["checks"])
    if requested not in ({CHECK}, {CHECK, QUALITY_CHECK}):
        raise ValueError(f"silver.land verifies {CHECK} only, with optional {QUALITY_CHECK}")
    keys = _keys(envelope)
    silver, _ = engines()
    try:
        spec = DatabaseSink(silver).spec(keys["silver"])
        count, seen = 0, set()
        for artifact in _artifacts(envelope, artifacts):
            rows = _rows(artifact, keys)
            count += len(rows)
            seen.update(_tuple(row, spec) for row in rows)
        stored = artifacts.verified(envelope["candidate"])
        try:
            receipt = json.loads(stored)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("The silver receipt is not valid JSON") from exc
        if not isinstance(receipt, dict) or receipt.get("version") not in (1, 2):
            raise ValueError("The silver receipt version is unsupported")
        if receipt["version"] == 1:
            expected = _receipt(count, seen)
        else:
            quality = receipt.get("quality")
            if not isinstance(quality, dict) or not isinstance(quality.get("observed_at"), str):
                raise ValueError("Version-2 silver receipt lacks its quality observation time")
            try:
                observed_at = datetime.fromisoformat(quality["observed_at"])
            except ValueError as exc:
                raise ValueError("Version-2 silver receipt has an invalid observation time") from exc
            if observed_at.tzinfo is None:
                raise ValueError("Version-2 silver receipt observation time must include a timezone")
            identity = _quality_identity(envelope, keys["silver"], spec)
            actual = _recomputed_quality(identity, artifacts, envelope, keys, spec, quality["observed_at"])
            if quality != actual:
                raise ValueError("The receipt's quality outcomes differ from the original reading")
            expected = _receipt(count, seen, actual)
        if stored != expected:
            raise ValueError("The receipt differs from the reading")
        if _missing(silver, spec, seen):
            raise ValueError("Silver lacks keys the reading holds")
    finally:
        silver.dispose()
    completed = {CHECK: True}
    if receipt["version"] == 2:
        if QUALITY_CHECK not in requested:
            raise ValueError("A version-2 quality receipt requires the frozen quality evidence check")
        completed[QUALITY_CHECK] = True
    elif QUALITY_CHECK in requested:
        raise ValueError("The frozen quality evidence check requires a version-2 receipt")
    return completed, []
