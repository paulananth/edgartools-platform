"""Drive one Bookkeeping run to the end, with the platform's own commands (ticket 136).

Shared by `rules test` and `load`. Each command runs in its own process under its
duty's login (the stores' `worker.env`, `verifier.env`, `governance.env`). Steps go
in their declared order: several workers on a step, one verifier, until every unit
of the step is verified; then `bookkeeping finalize`.

A unit left waiting on busy prerequisites or leases is claimed again on the next
pass. A unit that failed its work or its checks stops the run, which stays
resumable: drive the same run again.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urlparse

from edgar_warehouse.bookkeeping.clean.engine import CONTENTION

DUTIES = ("worker", "verifier", "governance")
# Seconds to wait after a pass that moved nothing: the units left are under another attempt's lease.
PAUSE = 15


class RunStopped(ValueError):
    """A run that cannot start or did not complete, with the reason."""


def duties(stores: Path) -> dict[str, dict[str, str | None]]:
    """Each duty's connection settings, from the local stores' private env files, line by
    line: a key the file unsets is None, so no login leaks in from the caller's shell."""
    found = {}
    for duty in DUTIES:
        path = stores / f"{duty}.env"
        if not path.is_file():
            raise RunStopped(f"{path} is missing: start the stores with infra/scripts/local-test-stores.py up <name>")
        values = {}
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                parts = shlex.split(line)
                if parts and parts[0] == "unset":
                    values.update(dict.fromkeys(parts[1:]))
                elif parts and parts[0] == "export":
                    key, _, value = parts[1].partition("=")
                    values[key] = value
            except (ValueError, IndexError):
                raise RunStopped(f"{path} line {number} is not an export or unset line") from None
        found[duty] = values
    return found


def manifest_root(env: dict[str, dict[str, str | None]]) -> Path:
    """The local folder `BOOKKEEPING_MANIFEST_ROOT` names, a `file://` URI or a plain path."""
    value = env["worker"].get("BOOKKEEPING_MANIFEST_ROOT") or ""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme or not value:
        raise RunStopped("BOOKKEEPING_MANIFEST_ROOT must name a local folder (file:// or a path)")
    return Path(value)


class Commands:
    """The platform's own commands, each run as its duty's login in its own process."""

    def __init__(self, env: dict[str, dict[str, str | None]], reports: str, *, deadline: float, log: Path,
                 workers: int = 1):
        if workers < 1:
            raise RunStopped("At least one worker")
        self.env, self.reports, self.deadline, self.log, self.workers = env, reports, deadline, log, workers

    def __call__(self, duty: str, *args: str) -> str:
        environment = {**os.environ, **self.env[duty]}
        environment = {key: value for key, value in environment.items() if value is not None}
        # The platform's command in its own process, on this interpreter: the same code.
        command = [sys.executable, "-c", "from edgar_warehouse.cli import main; raise SystemExit(main())"]
        try:
            done = subprocess.run([*command, *args], env=environment, capture_output=True, text=True,
                                  timeout=max(1.0, self.deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise RunStopped(f"{' '.join(args[:3])} did not finish before the deadline") from None
        if done.returncode not in (0, 3):
            # Its message can hold a login or an address: it goes to a private file, never the screen.
            self.log.parent.mkdir(parents=True, exist_ok=True)
            with os.fdopen(os.open(self.log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as out:
                out.write(f"$ {' '.join(args)}\n{done.stderr}\n")
            raise RunStopped(f"{' '.join(args[:3])} failed with status {done.returncode}; its message is in {self.log}")
        return done.stdout

    def status(self, run_id: str, step: str | None = None) -> dict:
        named = ("--step", step) if step is not None else ()
        return json.loads(self("worker", "bookkeeping", "status", run_id, "--limit", "1000", *named))

    def drive(self, run_id: str, steps: list[dict]) -> dict:
        """Each step's workers, then its verifier, in step order, until nothing is left."""
        for step in steps:
            profile = step["operation"]
            # The step's own counts: exact however many units it has.
            found = self.status(run_id, step["name"])
            while time.monotonic() < self.deadline:
                if found["counts"] and set(found["counts"]) == {"verified"}:
                    break
                # No more workers than units left: a one-unit step (a merge) gets one.
                left = sum(n for state, n in found["counts"].items() if state != "verified")
                work = ("worker", "workers", "work", profile, run_id, "--limit", "100")
                with ThreadPoolExecutor(max(1, min(self.workers, left))) as pool:
                    list(pool.map(lambda _: self(*work), range(max(1, min(self.workers, left)))))
                self("verifier", "workers", "verify", profile, run_id, "--reports", self.reports, "--limit", "1000")
                before, found = found["counts"], self.status(run_id, step["name"])
                if found["counts"] == before:
                    time.sleep(PAUSE)
                failed = [i for i in found["items"] if i["state"] == "waiting" and i.get("error") != CONTENTION]
                if failed:
                    raise RunStopped(f"step {step['name']}: unit {failed[0]['unit_key']} failed "
                                     f"({failed[0].get('error')}); see bookkeeping status {run_id} --step "
                                     f"{step['name']}, fix it, then drive run {run_id} again")
            else:
                raise RunStopped(f"step {step['name']} did not finish before the deadline; drive run {run_id} again")
        return json.loads(self("worker", "bookkeeping", "finalize", run_id))
