"""Run-scoped, private progress events for hosted-store clear monitoring."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _verify_backups(args) -> int:
    for unit, path in (("control", args.control_dump), ("rdm", args.rdm_dump)):
        set_step_state(args.run_id, "backups", "running", args.stores_folder)
        try:
            result = subprocess.run(
                ["pg_restore", "--list", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            record_unit(args.run_id, "backups", unit, "failed", args.stores_folder)
            return 1
        record_unit(args.run_id, "backups", unit,
                    "completed" if result.returncode == 0 else "failed", args.stores_folder)
        if result.returncode != 0:
            return 1
    return 0

def _verify_archive(args) -> int:
    if len(args.original) != 2 or len(args.archived) != 2:
        raise ProgressError("Provide exactly two original and two archived state-file paths.")
    set_step_state(args.run_id, "archive", "running", args.stores_folder)
    for index, (original, archived) in enumerate(zip(args.original, args.archived, strict=True), 1):
        unit = f"state-{index}"
        completed = not original.exists() and archived.is_file()
        record_unit(args.run_id, "archive", unit, "completed" if completed else "failed", args.stores_folder)
        if not completed:
            return 1
    return 0


def _start(args) -> int:
    published = Path(__file__).resolve().parents[1] / "rules" / "reference" / "published"
    rdm_total = sum(path.is_dir() for path in published.iterdir()) if published.is_dir() else 0
    totals = {"rdm": rdm_total} if rdm_total else None
    print(start_run(stores_folder=args.stores_folder, totals=totals))
    return 0


def _status(args) -> int:
    print(json.dumps(snapshot(args.run_id, args.stores_folder), sort_keys=True))
    return 0


def register(subparsers):
    parser = subparsers.add_parser(
        "hosted-store-clear-progress",
        help="Start or inspect a run-scoped hosted-store progress journal",
    )
    actions = parser.add_subparsers(dest="progress_action", required=True)
    start = actions.add_parser("start", help="Create a progress run without connecting to stores")
    start.add_argument("--stores-folder", type=Path)
    start.set_defaults(handler=_start)
    status = actions.add_parser("status", help="Read the latest progress snapshot")
    status.add_argument("--run-id", required=True)
    status.add_argument("--stores-folder", type=Path)
    status.set_defaults(handler=_status)
    backups = actions.add_parser("verify-backups", help="Verify the control and RDM dumps and record their progress")
    backups.add_argument("--run-id", required=True)
    backups.add_argument("--stores-folder", type=Path)
    backups.add_argument("--control-dump", type=Path, required=True)
    backups.add_argument("--rdm-dump", type=Path, required=True)
    backups.set_defaults(handler=_verify_backups)
    archive = actions.add_parser("verify-archive", help="Verify two state files were renamed, then record progress")
    archive.add_argument("--run-id", required=True)
    archive.add_argument("--stores-folder", type=Path)
    archive.add_argument("--original", type=Path, action="append", required=True)
    archive.add_argument("--archived", type=Path, action="append", required=True)
    archive.set_defaults(handler=_verify_archive)


STEPS = (
    {
        "id": "preflight", "title": "Preflight and drain",
        "description": "Confirm no active load or unresolved Bookkeeping run; inspect sessions, replication, instance and mirror state.",
        "total": 12, "unit": "checks",
    },
    {
        "id": "backups", "title": "Back up control and RDM",
        "description": "Verify readable backups of the control database and RDM schema before any reset.",
        "total": 2, "unit": "backups",
    },
    {
        "id": "reset", "title": "Reset five stores",
        "description": "Apply each reviewed table plan as one store transaction; preserve metadata and restore retention triggers.",
        "total": 5, "unit": "store transactions",
    },
    {
        "id": "rdm", "title": "Restore published RDM codes",
        "description": "Restore pinned code sets and verify each published version.",
        "total": 11, "unit": "code sets",
    },
    {
        "id": "archive", "title": "Set old run-state files aside",
        "description": "Rename prior-generation state files; never delete them.",
        "total": 2, "unit": "files archived",
    },
    {
        "id": "readiness", "title": "Verify final state and readiness",
        "description": "Check reset tables, preserved metadata, triggers and readiness.",
        "total": 12, "unit": "readiness checks",
    },
)
_STEP_BY_ID = {step["id"]: step for step in STEPS}
_UNIT_ID = re.compile(r"^[A-Za-z0-9._-]{1,96}$")
_UNIT_STORES = {"mdm", "rdm", "silver", "bookkeeping", "change_journal"}


class ProgressError(ValueError):
    """The run or progress event violates the progress contract."""


def progress_root(stores_folder: Path | None = None) -> Path:
    folder = stores_folder or Path(os.environ.get("STORES_FOLDER") or Path.home() / ".config/edgartools/hosted")
    return Path(folder) / "clear-runs"


def start_run(run_id: str | None = None, stores_folder: Path | None = None,
              totals: dict[str, int] | None = None) -> str:
    """Create a private progress ledger; does not connect to or change a store."""
    run_id = _valid_run_id(run_id or str(uuid.uuid4()))
    folder = progress_root(stores_folder) / run_id
    folder.mkdir(parents=True, mode=0o700)
    folder.chmod(0o700)
    selected_totals = {step["id"]: step["total"] for step in STEPS}
    for step_id, total in (totals or {}).items():
        if step_id not in _STEP_BY_ID or type(total) is not int or total < 1:
            raise ProgressError("Invalid run step total.")
        selected_totals[step_id] = total
    _append(run_id, {"type": "run.started", "totals": selected_totals}, stores_folder)
    return run_id
def set_step_total(run_id: str, step_id: str, total: int, stores_folder: Path | None = None) -> dict:
    """Set a measured step denominator before work units are reported."""
    run_id = _valid_run_id(run_id)
    if step_id not in _STEP_BY_ID or type(total) is not int or total < 1:
        raise ProgressError("Invalid progress step total.")
    current = snapshot(run_id, stores_folder)
    if total < current["steps"][step_id]["completed"]:
        raise ProgressError("The step total cannot be below completed work.")
    _append(run_id, {"type": "step.total", "step": step_id, "total": total}, stores_folder)
    return snapshot(run_id, stores_folder)
def set_step_state(run_id: str, step_id: str, state: str, stores_folder: Path | None = None) -> dict:
    """Record an observed running or failed state for one step."""
    run_id = _valid_run_id(run_id)
    if step_id not in _STEP_BY_ID or state not in {"running", "failed"}:
        raise ProgressError("Unknown step or invalid step state.")
    _append(run_id, {"type": "step.state", "step": step_id, "state": state}, stores_folder)
    return snapshot(run_id, stores_folder)


def record_unit(run_id: str, step_id: str, unit_id: str, state: str,
                stores_folder: Path | None = None) -> dict:
    """Record one observed unit transition; no work is performed by this function."""
    run_id = _valid_run_id(run_id)
    step = _STEP_BY_ID.get(step_id)
    if step is None or not isinstance(unit_id, str) or not _UNIT_ID.fullmatch(unit_id):
        raise ProgressError("Unknown progress step or unit.")
    if state not in {"running", "completed", "failed"}:
        raise ProgressError("Unit state must be running, completed or failed.")
    if step_id == "reset" and unit_id not in _UNIT_STORES:
        raise ProgressError("Unknown reset store.")
    current = snapshot(run_id, stores_folder)
    prior = current["steps"][step_id]["units"].get(unit_id)
    if prior == "completed" and state != "completed":
        raise ProgressError("A completed unit cannot move backward.")
    units = current["steps"][step_id]["units"]
    total = current["steps"][step_id]["total"]
    if unit_id not in units and len(units) >= total:
        raise ProgressError("The step already has its full number of units.")
    _append(run_id, {"type": "step.unit", "step": step_id, "unit": unit_id, "state": state}, stores_folder)
    return snapshot(run_id, stores_folder)


def snapshot(run_id: str, stores_folder: Path | None = None) -> dict:
    """Return a sanitized state snapshot suitable for the local UI."""
    run_id = _valid_run_id(run_id)
    path = progress_root(stores_folder) / run_id / "events.jsonl"
    if not path.is_file():
        raise FileNotFoundError("No hosted-store progress run has that ID.")
    units: dict[str, dict[str, str]] = {step["id"]: {} for step in STEPS}
    explicit: dict[str, str] = {}
    totals = {step["id"]: step["total"] for step in STEPS}
    updated_at = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "step.unit" and event.get("step") in units:
            units[event["step"]][event["unit"]] = event["state"]
            updated_at = event.get("at")
        elif event.get("type") == "step.state" and event.get("step") in units:
            explicit[event["step"]] = event["state"]
            updated_at = event.get("at")
        elif event.get("type") == "step.total" and event.get("step") in totals:
            total = event.get("total")
            if type(total) is int and total > 0:
                totals[event["step"]] = total
            updated_at = event.get("at")
        elif event.get("type") == "run.started":
            requested = event.get("totals", {})
            if isinstance(requested, dict):
                for step_id, total in requested.items():
                    if step_id in totals and type(total) is int and total > 0:
                        totals[step_id] = total
            updated_at = event.get("at")
    rendered = {}
    for spec in STEPS:
        step_id = spec["id"]
        values = units[step_id]
        total = totals[step_id]
        completed = sum(value == "completed" for value in values.values())
        failed = explicit.get(step_id) == "failed" or any(value == "failed" for value in values.values())
        running = explicit.get(step_id) == "running" or any(value == "running" for value in values.values())
        state = ("failed" if failed else "complete" if completed == total
                 else "running" if running or completed else "not_started")
        rendered[step_id] = {
            "title": spec["title"], "state": state, "completed": completed,
            "total": total, "unit": spec["unit"], "units": dict(values),
        }
    run_state = ("failed" if any(value["state"] == "failed" for value in rendered.values())
                 else "complete" if all(value["state"] == "complete" for value in rendered.values())
                 else "running" if any(value["state"] in {"running", "complete"} for value in rendered.values())
                 else "not_started")
    return {"run_id": run_id, "state": run_state, "updated_at": updated_at, "steps": rendered}


def _append(run_id: str, event: dict, stores_folder: Path | None) -> None:
    run_id = _valid_run_id(run_id)
    path = progress_root(stores_folder) / run_id / "events.jsonl"
    if not path.parent.is_dir():
        raise FileNotFoundError("No hosted-store progress run has that ID.")
    record = {"at": datetime.now(ZoneInfo("America/New_York")).isoformat(), "run_id": run_id, **event}
    data = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _valid_run_id(run_id: str) -> str:
    try:
        return str(uuid.UUID(run_id))
    except (AttributeError, TypeError, ValueError) as error:
        raise ProgressError("Run ID must be a UUID.") from error
