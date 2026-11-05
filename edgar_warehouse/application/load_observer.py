"""Publish read-only Bookkeeping observations through OpenMetadata's native API.

This application owns the connection. Neither controller nor workers depend on
OpenMetadata. A failed report can be retried without repeating a load.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote


class ObservationError(ValueError):
    """An operator-safe cause owned by this reporter, never a raw driver error."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def milliseconds(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)  # MySQL stores UTC without an offset.
    delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def counter(value):
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ObservationError("invalid_counter", "A counter is not an exact integer")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ObservationError("invalid_counter", "A counter is not finite")
    if value < 0 or value != int(value):
        raise ObservationError("invalid_counter", "A counter is not an exact nonnegative integer")
    return str(int(value))


def payload(observation, observed_at):
    """Metadata counters are decimal strings to survive arbitrary JSON readers."""
    o = observation
    if o["compacted"]:
        raise ObservationError("compacted_evidence", "Compacted run evidence is unavailable")
    states = {"running": "Pending", "waiting": "Pending", "blocked": "Failed", "complete": "Successful"}
    if o["state"] not in states:
        raise ObservationError("unknown_state", "Unknown Bookkeeping state")
    if o["state"] == "complete" and (o["pending_deliveries"] or any(
            row["unit_state"] != "verified" for row in o["steps"]) or
            sum(row["units"] for row in o["steps"]) != o["expected_units"] or
            any(value is not True for value in o["checks"].values())):
        raise ObservationError("inconsistent_completion", "Completion evidence is inconsistent")
    steps = sorted(o["steps"], key=lambda row: (row["step"], row["unit_state"]))
    names = sorted(set(o.get("declared_steps") or []) | {row["step"] for row in steps})
    task_status = []
    for name in names:
        groups = [row for row in steps if row["step"] == name]
        if not groups:
            state = "Skipped" if o["state"] == "complete" else "Pending"
        else:
            state = "Successful" if all(row["unit_state"] == "verified" for row in groups) else "Pending"
        task_status.append({"name": name, "executionStatus": state})
    metadata = {"state": o["state"], "observedAt": observed_at,
                "createdAt": o["created_at"].isoformat() if isinstance(o["created_at"], datetime) else o["created_at"],
                "source": {"kind": o["kind"], "name": o["name"], "target": o["target"]},
                "expectedUnits": counter(o["expected_units"]),
                "pendingDeliveries": counter(o["pending_deliveries"]), "checks": o["checks"],
                "integerEncoding": "decimal-string", "countUnit": "work-items",
                "outputRowCounts": "not_reported", "qualityResults": "not_reported",
                "declaredSteps": names,
                "steps": [{**row, **{key: counter(row[key]) for key in ("units", "attempts", "errors")}}
                          for row in steps],
                "nextAction": "Load complete" if o["state"] == "complete" else
                              "Inspect this run in Bookkeeping for remaining work and checks"}
    result = {"executionId": o["run_id"], "timestamp": milliseconds(o["created_at"]),
              "executionStatus": states[o["state"]],
              "taskStatus": task_status,
              "parameters": {"bookkeeping": metadata}}
    if o["completed_at"] is not None:
        result["endTime"] = milliseconds(o["completed_at"])
    return result


def matches(expected, actual):
    """Native readback may add default fields; every supplied value must survive."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and matches(value, actual[key])
                                                for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            matches(left, right) for left, right in zip(expected, actual))
    return type(expected) is type(actual) and expected == actual


def publish(observation, call, *, service, observed_at, dry_run=False):
    from edgar_warehouse.rules.catalog import fqn as catalog_fqn

    body = payload(observation, observed_at)
    name = f"{observation['kind']}:{observation['name']}:{observation['target']}"
    fqn = catalog_fqn(service, name)
    if not call("GET", "/pipelines/name/" + quote(fqn, safe="")):
        raise ObservationError("missing_pipeline", "Catalog pipeline is missing; publish the Rules catalog first")
    path = "/pipelines/" + quote(fqn, safe="") + "/status"
    # Native timestamps are connector-defined history keys, not wall clocks.
    # Reserve a free millisecond within this creation second's window and reuse
    # the execution ID's existing key. Actual creation time remains in parameters.
    base = body["timestamp"]
    params = {"startTs": base, "endTs": base + 999, "limit": 1000}
    previous = (call("GET", path, params=params) or {}).get("data") or []
    previous = [record for record in previous if base <= record.get("timestamp", -1) <= base + 999]
    own = [record for record in previous if record.get("executionId") == body["executionId"]]
    if len(own) > 1:
        raise ObservationError("duplicate_execution", "Multiple native records already identify this load")
    if own:
        body["timestamp"] = own[0]["timestamp"]
    else:
        occupied = {record["timestamp"] for record in previous}
        available = next((key for key in range(base, base + 1000) if key not in occupied), None)
        if available is None:
            raise ObservationError("timestamp_capacity", "Native timestamp window is full; no load was overwritten")
        body["timestamp"] = available
    for record in own:
        last = ((record.get("parameters") or {}).get("bookkeeping") or {}).get("observedAt", 0)
        if last > observed_at:
            raise ObservationError("stale_observation", "A newer observation already exists")
    if dry_run:
        return "pending"
    call("PUT", path, body)
    records = (call("GET", path, params=params) or {}).get("data") or []
    if not any(matches(body, record) for record in records):
        raise ObservationError("readback_mismatch", "OpenMetadata readback differs from the observation")
    return "confirmed"


def discover(book, run_ids, page_size):
    if run_ids:
        yield from dict.fromkeys(run_ids)
        return
    before, seen = None, set()
    while True:
        page = book.runs(limit=page_size, before=before)
        for run in page:
            identity = str(run["run_id"])
            if identity in seen:
                raise ValueError("Run discovery repeated a cursor")
            seen.add(identity)
            yield identity
        if len(page) < page_size:
            return
        before = str(page[-1]["run_id"])


def sweep(book, call, *, run_ids=(), page_size=100, service="edgartools-rules-pipelines", dry_run=False):
    result = {"discovered": 0, "confirmed": 0, "pending": 0, "failed": 0, "errors": {}, "failed_runs": []}
    try:
        for identity in discover(book, run_ids, page_size):
            result["discovered"] += 1
            try:
                observation = book.observation(identity)
                state = publish(observation, call, service=service,
                                observed_at=time.time_ns() // 1_000_000, dry_run=dry_run)
                result[state] += 1
            except Exception as error:
                # Driver/HTTP errors may contain credentials or record contents.
                # Emit only the exception class; keep authoritative load errors in Bookkeeping.
                result["failed"] += 1
                http = re.search(r"\bHTTP (\d{3})\b", str(error))
                kind = (error.code if isinstance(error, ObservationError) else
                        "HTTP_" + http.group(1) if http else type(error).__name__)
                result["errors"][kind] = result["errors"].get(kind, 0) + 1
                result["failed_runs"].append({"run_id": identity, "cause": kind})
    except Exception as error:
        result["failed"] += 1
        kind = type(error).__name__
        result["errors"][kind] = result["errors"].get(kind, 0) + 1
        result["discovery_complete"] = False
    else:
        result["discovery_complete"] = True
    result["status"] = "partial" if result["failed"] else ("pending" if dry_run else "confirmed")
    return result


def _observe(args):
    from edgar_warehouse.bookkeeping.clean.cli import configured_bookkeeping
    from edgar_warehouse.rules.catalog import connect

    if not 1 <= args.page_size <= 1000 or args.interval < 1 or args.duration < 0:
        print(json.dumps({"status": "failed", "cause": "Invalid observation bounds"}))
        return 2
    url, token = os.environ.get("OPENMETADATA_URL"), os.environ.get("OPENMETADATA_TOKEN")
    if not url or not token:
        print(json.dumps({"status": "failed", "cause": "Set OPENMETADATA_URL and OPENMETADATA_TOKEN"}))
        return 2
    deadline, failed = time.monotonic() + args.duration, False
    try:
        book = configured_bookkeeping()
        try:
            call = connect(url, token)
            while True:
                result = sweep(book, call, run_ids=args.run, page_size=args.page_size,
                               service=args.service, dry_run=args.dry_run)
                print(json.dumps(result, sort_keys=True), flush=True)
                failed |= bool(result["failed"])
                remaining = deadline - time.monotonic()
                if not args.duration or remaining <= 0:
                    break
                time.sleep(min(args.interval, remaining))
                if time.monotonic() >= deadline:
                    break
        finally:
            book.close()
    except Exception as error:
        print(json.dumps({"status": "failed", "cause": type(error).__name__}))
        return 1
    return 1 if failed else 0


def _handle(args):
    """One reporter process per host; multi-host operation needs one owner."""
    import fcntl

    path = args.lock_file or Path.home() / ".cache/edgartools/openmetadata-observer.lock"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print(json.dumps({"status": "failed", "cause": "reporter_already_running"}))
                return 1
            return _observe(args)
    except OSError as error:
        print(json.dumps({"status": "failed", "cause": type(error).__name__}))
        return 1


def register(subparsers):
    parser = subparsers.add_parser("observe", help="Report actual Bookkeeping loads to OpenMetadata")
    commands = parser.add_subparsers(dest="observe_command", required=True)
    loads = commands.add_parser("loads", help="Publish and verify load observations; never execute loads")
    selection = loads.add_mutually_exclusive_group(required=True)
    selection.add_argument("--run", action="append", help="Observe this run; repeat for multiple runs")
    selection.add_argument("--all", action="store_true", help="Discover every retained run, page by page")
    loads.add_argument("--page-size", type=int, default=100)
    loads.add_argument("--service", default="edgartools-rules-pipelines")
    loads.add_argument("--dry-run", action="store_true", help="Read both systems without writing status")
    loads.add_argument("--interval", type=int, default=60)
    loads.add_argument("--duration", type=int, default=0, help="Repeat for this many seconds; default is one sweep")
    loads.add_argument("--lock-file", type=Path, help="Reporter lock; default is in the operator's private cache")
    loads.set_defaults(handler=_handle)
