"""Verified silver quality outcomes admitted to a Bookkeeping run.

This module reads only completed Bookkeeping work and its immutable candidate
receipts. It never reads the silver writer's mutable latest-results file and
never writes to OpenMetadata.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from . import storage
from .config import Blocked

QUALITY_CHECK = "silver.quality.evidence.v2"
MAX_COUNT = 2**63 - 1


def work_unit_reference(run_id: str, step: str, key: str, attempt: str) -> str:
    """Opaque stable identity; work keys may themselves contain provider data."""
    binding = json.dumps([run_id, step, key, attempt], separators=(",", ":")).encode()
    return hashlib.sha256(binding).hexdigest()[:24]


def aggregate(bookkeeping, run_id: str) -> dict:
    """Return per-unit results plus a load summary; incomplete evidence is unknown."""
    run, config, _, expected_items = bookkeeping._frozen(run_id)
    steps = {step["name"]: step for step in config["steps"]
             if step["operation"] == "silver.land" and QUALITY_CHECK in step["checks"]}
    if not steps:
        return {"status": "unknown", "reason": "No silver step requested version-2 quality evidence",
                "run_id": run_id, "units_expected": 0, "units_verified": 0,
                "units_unknown": 0, "results": [], "checks": []}

    expected = {(item["step"], item["key"]) for item in expected_items if item["step"] in steps}
    work = storage.work(bookkeeping.engine, run_id, ordered=True)
    by_identity = {(item["step"], item["unit_key"]): item for item in work if item["step"] in steps}
    complete_run = run.get("state") == "complete"

    unknown_units = []
    results = []
    totals = {}
    for step, unit_key in sorted(expected):
        item = by_identity.get((step, unit_key))
        if item is None or item["state"] != "verified" or not item.get("receipt"):
            attempt = str(item["attempt"]) if item and item.get("attempt") else ""
            unknown_units.append({"step": step, "work_unit_ref": work_unit_reference(run_id, step, unit_key, attempt)})
            continue
        candidate = {"uri": item["receipt"]["uri"], "sha256": item["receipt"]["sha256"]}
        raw = bookkeeping.artifacts.verified(candidate)
        try:
            receipt = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise Blocked("Admitted silver quality receipt is not valid JSON") from exc
        quality = receipt.get("quality") if isinstance(receipt, dict) and receipt.get("version") == 2 else None
        if not isinstance(quality, dict):
            unknown_units.append({"step": step, "work_unit_ref": work_unit_reference(
                run_id, step, unit_key, str(item["attempt"]))})
            continue
        attempt = str(item["attempt"])
        expected_identity = (run_id, step, work_unit_reference(run_id, step, unit_key, attempt), attempt)
        actual_identity = (quality.get("run_id"), quality.get("step"), quality.get("work_unit_ref"),
                           quality.get("attempt"))
        if actual_identity != expected_identity:
            raise Blocked("Admitted silver quality receipt has a different run, step, unit or attempt")
        outcomes = quality.get("checks")
        if not isinstance(outcomes, dict) or not outcomes:
            unknown_units.append({"step": step, "work_unit_ref": expected_identity[2]})
            continue
        for check, outcome in sorted(outcomes.items()):
            if (not isinstance(outcome, dict) or outcome.get("failure_action") not in ("flag", "exception")
                    or not isinstance(outcome.get("kind"), str) or not outcome["kind"]
                    or type(outcome.get("rows_checked")) is not int or type(outcome.get("rows_failed")) is not int
                    or not 0 <= outcome["rows_failed"] <= outcome["rows_checked"] <= MAX_COUNT):
                raise Blocked("Admitted silver quality receipt has malformed check counts")
            result = {"run_id": run_id, "step": step, "work_unit_ref": expected_identity[2],
                      "attempt": attempt, "table": quality.get("table"), "check": check,
                      "kind": outcome.get("kind"), "failure_action": outcome["failure_action"],
                      "observed_at": quality.get("observed_at"), "rows_checked": outcome["rows_checked"],
                      "rows_failed": outcome["rows_failed"],
                      "status": "failed" if outcome["rows_failed"] else "passed"}
            results.append(result)
            key = (step, result["table"], check)
            total = totals.setdefault(key, {"step": step, "table": result["table"], "check": check,
                                             "kind": result["kind"], "failure_action": result["failure_action"],
                                             "units": 0, "rows_checked": 0, "rows_failed": 0})
            if total["units"] >= MAX_COUNT:
                raise Blocked("Aggregated silver quality unit count exceeds signed 64-bit storage")
            total["units"] += 1
            if total["rows_checked"] > MAX_COUNT - result["rows_checked"] or total["rows_failed"] > MAX_COUNT - result["rows_failed"]:
                raise Blocked("Aggregated silver quality counts exceed signed 64-bit storage")
            total["rows_checked"] += result["rows_checked"]
            total["rows_failed"] += result["rows_failed"]

    check_totals = []
    for total in totals.values():
        total["status"] = "unknown" if unknown_units or not complete_run else (
            "failed" if total["rows_failed"] else "passed")
        check_totals.append(total)
    status = "unknown" if unknown_units or not complete_run or not check_totals else (
        "failed" if any(item["rows_failed"] for item in check_totals) else "passed")
    return {"status": status, "run_id": run_id, "run_complete": complete_run,
            "reason": "Bookkeeping run is not complete" if not complete_run else None,
            "units_expected": len(expected),
            "units_verified": len(expected) - len(unknown_units), "units_unknown": len(unknown_units),
            "unknown_units": unknown_units, "results": results, "checks": check_totals}


def catalog_results(summary: dict) -> dict:
    """Map admitted per-unit checks to the existing catalog case names."""
    if summary.get("status") == "unknown" or summary.get("units_unknown"):
        raise Blocked("OpenMetadata publication requires complete, admitted quality evidence")
    if summary.get("status") not in ("passed", "failed"):
        raise Blocked("OpenMetadata publication requires a verified quality summary")
    grouped = {}
    for item in summary.get("results") or []:
        identity_fields = ("run_id", "step", "work_unit_ref", "attempt", "table", "check", "observed_at")
        if any(not isinstance(item.get(field), str) or not item[field] for field in identity_fields):
            raise Blocked("Verified quality result lacks its stable load identity")
        checked, failed = item.get("rows_checked"), item.get("rows_failed")
        action = item.get("failure_action")
        if (type(checked) is not int or type(failed) is not int or action not in ("flag", "exception")
                or not 0 <= failed <= checked <= MAX_COUNT):
            raise Blocked("Verified quality result has invalid counts or failure action")
        try:
            observed = datetime.fromisoformat(item["observed_at"])
        except ValueError as exc:
            raise Blocked("Verified quality result has an invalid observation time") from exc
        if observed.tzinfo is None:
            raise Blocked("Verified quality result observation time must include a timezone")
        case_name = f"{item['table']}.{item['check']}"
        grouped.setdefault(case_name, []).append({**item, "_timestamp": observed.astimezone(timezone.utc)})
    results = {}
    for name, items in grouped.items():
        items.sort(key=lambda row: (row["_timestamp"], row["step"], row["work_unit_ref"], row["attempt"]))
        entries = []
        previous = None
        for item in items:
            timestamp = int(item["_timestamp"].timestamp() * 1000)
            timestamp = max(timestamp, previous + 1 if previous is not None else timestamp)
            previous = timestamp
            at = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")
            entries.append({"table": item["table"], "check": item["check"],
                            "on_fail": item["failure_action"], "at": at,
                            "rows_checked": item["rows_checked"], "rows_failed": item["rows_failed"],
                            "correlation": (f"Bookkeeping run {item['run_id']}, step {item['step']}, "
                                            f"unit {item['work_unit_ref']}, attempt {item['attempt']}; "
                                            f"observed at {item['observed_at']}")})
        results[name] = entries
    return results
