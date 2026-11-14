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


def work_unit_reference(run_id: str, step: str, key: str) -> str:
    """Opaque stable identity; work keys may themselves contain provider data.

    The reference names the work unit, never an attempt: a unit re-executed
    after a lost report keeps one receipt, one observation time and one
    correlation, so a resumed load's evidence is the same evidence.
    """
    binding = json.dumps([run_id, step, key], separators=(",", ":")).encode()
    return hashlib.sha256(binding).hexdigest()[:24]


def _aggregate_silver(bookkeeping, run_id: str) -> dict:
    """Return per-unit silver results plus a load summary; incomplete evidence is unknown."""
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
        reference = work_unit_reference(run_id, step, unit_key)
        if item is None or item["state"] != "verified" or not item.get("receipt"):
            unknown_units.append({"step": step, "work_unit_ref": reference})
            continue
        candidate = {"uri": item["receipt"]["uri"], "sha256": item["receipt"]["sha256"]}
        raw = bookkeeping.artifacts.verified(candidate)
        try:
            receipt = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise Blocked("Admitted silver quality receipt is not valid JSON") from exc
        quality = receipt.get("quality") if isinstance(receipt, dict) and receipt.get("version") == 2 else None
        if not isinstance(quality, dict):
            unknown_units.append({"step": step, "work_unit_ref": reference})
            continue
        attempt = str(item["attempt"])
        expected_identity = (run_id, step, reference)
        actual_identity = (quality.get("run_id"), quality.get("step"), quality.get("work_unit_ref"))
        if actual_identity != expected_identity:
            raise Blocked("Admitted silver quality receipt has a different run, step or unit")
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


def _aggregate_mdm(bookkeeping, run_id: str, run: dict, steps: dict, expected_items: list) -> dict:
    expected = {(item["step"], item["key"]) for item in expected_items if item["step"] in steps}
    work = storage.work(bookkeeping.engine, run_id, ordered=True)
    by_identity = {(item["step"], item["unit_key"]): item for item in work if item["step"] in steps}
    complete_run = run.get("state") == "complete"
    unknown_units, results, totals = [], [], {}
    for step, key in sorted(expected):
        item = by_identity.get((step, key))
        reference = work_unit_reference(run_id, step, key)
        if item is None or item["state"] != "verified" or not item.get("receipt"):
            unknown_units.append({"step": step, "work_unit_ref": reference})
            continue
        raw = bookkeeping.artifacts.verified({"uri": item["receipt"]["uri"], "sha256": item["receipt"]["sha256"]})
        try:
            receipt = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise Blocked("Admitted MDM quality receipt is not valid JSON") from exc
        quality = receipt.get("quality") if isinstance(receipt, dict) else None
        if (not isinstance(quality, dict) or quality.get("version") != 1
                or (quality.get("run_id"), quality.get("step"), quality.get("work_unit_ref")) !=
                   (run_id, step, reference) or not isinstance(quality.get("observed_at"), str)):
            unknown_units.append({"step": step, "work_unit_ref": reference})
            continue
        for source in quality.get("sources") or []:
            if not isinstance(source, dict) or not isinstance(source.get("checks"), dict):
                raise Blocked("Admitted MDM quality receipt has malformed source checks")
            table, rule_version = source.get("table"), source.get("rule_version")
            if not isinstance(table, str) or not table or not isinstance(rule_version, str) or not rule_version:
                raise Blocked("Admitted MDM quality receipt lacks source or rule identity")
            for check, outcome in (source.get("checks") or {}).items():
                if (not isinstance(check, str) or not check or not isinstance(outcome, dict)
                        or outcome.get("failure_action") not in ("flag", "withhold", "exception")
                        or not isinstance(outcome.get("kind"), str)
                        or any(type(outcome.get(field)) is not int or not 0 <= outcome[field] <= MAX_COUNT
                               for field in ("rows_checked", "rows_failed", "rows_expected", "rows_unknown"))
                        or outcome["rows_failed"] > outcome["rows_checked"]
                        or outcome["rows_checked"] + outcome["rows_unknown"] != outcome["rows_expected"]):
                    raise Blocked("Admitted MDM quality receipt has malformed check counts")
                result = {"run_id": run_id, "step": step, "work_unit_ref": reference,
                          "attempt": str(item["attempt"]), "table": table, "check": check,
                          "rule_version": rule_version, "kind": outcome["kind"],
                          "failure_action": outcome["failure_action"], "observed_at": quality["observed_at"],
                          "rows_checked": outcome["rows_checked"], "rows_failed": outcome["rows_failed"],
                          "rows_unknown": outcome["rows_unknown"],
                          "status": "unknown" if outcome["rows_unknown"] or not complete_run else
                                    ("failed" if outcome["rows_failed"] else "passed")}
                results.append(result)
                agg_key = (step, table, check)
                total = totals.setdefault(agg_key, {"step": step, "table": table, "check": check,
                    "rule_version": rule_version, "kind": outcome["kind"],
                    "failure_action": outcome["failure_action"], "units": 0,
                    "rows_checked": 0, "rows_failed": 0, "rows_unknown": 0})
                for field in ("rows_checked", "rows_failed", "rows_unknown"):
                    if total[field] > MAX_COUNT - result[field]:
                        raise Blocked("Aggregated MDM quality counts exceed signed 64-bit storage")
                    total[field] += result[field]
                total["units"] += 1
                if total["units"] > MAX_COUNT:
                    raise Blocked("Aggregated MDM quality unit count exceeds signed 64-bit storage")
    incomplete = bool(unknown_units) or not complete_run
    checks = []
    for total in totals.values():
        total["status"] = "unknown" if incomplete or total["rows_unknown"] else (
            "failed" if total["rows_failed"] else "passed")
        checks.append(total)
    status = "unknown" if incomplete or not checks or any(item["status"] == "unknown" for item in checks) else (
        "failed" if any(item["rows_failed"] for item in checks) else "passed")
    return {"quality_type": "mdm", "status": status, "run_id": run_id,
            "run_complete": complete_run, "units_expected": len(expected),
            "units_verified": len(expected) - len(unknown_units), "units_unknown": len(unknown_units),
            "unknown_units": unknown_units, "results": results, "checks": checks}


def aggregate(bookkeeping, run_id: str) -> dict:
    """Combine every configured quality adapter into one admitted run summary."""
    run, config, _, expected_items = bookkeeping._frozen(run_id)
    silver_configured = any(step["operation"] == "silver.land" and QUALITY_CHECK in step["checks"]
                            for step in config["steps"])
    mdm_steps = {step["name"]: step for step in config["steps"]
                 if step["operation"] == "mastering.merge" and "mdm.quality.evidence.v1" in step["checks"]}
    summaries = []
    if silver_configured:
        summaries.append(_aggregate_silver(bookkeeping, run_id))
    if mdm_steps:
        summaries.append(_aggregate_mdm(bookkeeping, run_id, run, mdm_steps, expected_items))
    if not summaries:
        return {"status": "unknown", "reason": "No step requested a supported quality receipt",
                "run_id": run_id, "units_expected": 0, "units_verified": 0,
                "units_unknown": 0, "results": [], "checks": []}
    if len(summaries) == 1:
        return summaries[0]
    unknown = [unit for summary in summaries for unit in summary.get("unknown_units", [])]
    checks = [check for summary in summaries for check in summary.get("checks", [])]
    results = [result for summary in summaries for result in summary.get("results", [])]
    statuses = [summary["status"] for summary in summaries]
    status = "unknown" if "unknown" in statuses else ("failed" if "failed" in statuses else "passed")
    expected = sum(summary.get("units_expected", 0) for summary in summaries)
    verified = sum(summary.get("units_verified", 0) for summary in summaries)
    return {"status": status, "run_id": run_id, "run_complete": run.get("state") == "complete",
            "units_expected": expected, "units_verified": verified, "units_unknown": len(unknown),
            "unknown_units": unknown, "results": results, "checks": checks}


def catalog_results(summary: dict) -> dict:
    """Map admitted per-unit checks to the existing catalog case names."""
    if summary.get("status") not in ("passed", "failed", "unknown"):
        raise Blocked("OpenMetadata publication requires an admitted quality summary")
    grouped = {}
    for item in summary.get("results") or []:
        identity_fields = ("run_id", "step", "work_unit_ref", "attempt", "table", "check", "observed_at")
        if any(not isinstance(item.get(field), str) or not item[field] for field in identity_fields):
            raise Blocked("Verified quality result lacks its stable load identity")
        checked, failed = item.get("rows_checked"), item.get("rows_failed")
        action = item.get("failure_action")
        if (type(checked) is not int or type(failed) is not int or action not in ("flag", "withhold", "exception")
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
                            "status": ("unknown" if summary.get("status") == "unknown" else
                                       item.get("status", "failed" if item["rows_failed"] else "passed")),
                            "rule_version": item.get("rule_version"),
                            "rows_unknown": item.get("rows_unknown", 0),
                            "units_unknown": summary.get("units_unknown", 0),
                            "correlation": (f"Bookkeeping run {item['run_id']}, step {item['step']}, "
                                            f"unit {item['work_unit_ref']}, attempt {item['attempt']}; "
                                            f"observed at {item['observed_at']}")})
        results[name] = entries
    return results
