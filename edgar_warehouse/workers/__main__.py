"""Run a worker for one profile against one Bookkeeping run.

    python -m edgar_warehouse.workers work <profile> <run_id> --reports <URI> [--limit N]

A worker does a unit's work, checks its own result once and reports both; the
report completes the unit.

`edgar-warehouse workers …` takes the same arguments (`cli.py`).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import signal
import sys
import threading
import time
from pathlib import Path

from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts

from . import control, profile as load_profile


def runtime(module) -> str:
    """The digest a run pins for this profile: its code and the protocol client."""
    here = Path(__file__).parent
    extra = module.runtime_files() if hasattr(module, "runtime_files") else []
    files = sorted({Path(module.__file__), here / "control.py", here / "__main__.py", *extra})
    return hashlib.sha256(b"".join(path.read_bytes() for path in files)).hexdigest()


class Renewal:
    """Keep the lease alive while the work runs; stop before reporting.

    A renewal that cannot reach Bookkeeping is tried again at each heartbeat:
    the lease outlasts several. A renewal Bookkeeping refuses ends the work.

    The renewed proof is also written into the envelope the work holds
    (`claim.proof`), so a destination that fences its own transaction with it
    (MDM, `bookkeeping_guard`) always checks the current lease.
    """

    def __init__(self, envelope: dict):
        self.envelope, self.error, self.live = envelope, None, envelope
        self.renewed, self.last, self.lost = 0, time.monotonic(), False
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop.wait(self.envelope["heartbeat_seconds"]):
            try:
                self.envelope = control.renew(self.envelope)
                self.live["claim"] = {**self.live["claim"], "proof": self.envelope["claim"]["proof"]}
                self.renewed, self.last = self.renewed + 1, time.monotonic()
                self.error = None
            except Exception as exc:
                self.error = exc
                if "Stale lease" in str(exc):  # Bookkeeping's own refusal: no report of this work can be taken
                    self.lost = True
                    # A real signal, so the work stops now (a sleep or a wait wakes), not after hours nobody can use.
                    os.kill(os.getpid(), signal.SIGINT)
                    return
                # Anything else (a dropped connection, a timeout) is tried again at the next heartbeat.

    def state(self) -> str:
        """What a refused lease needs to be told apart: did renewal fail, or did the work meet a stale lease."""
        age = round(time.monotonic() - self.last)
        return (f"renewal failed {age}s after its last success ({self.renewed} renewals)" if self.error is not None
                else f"renewal ok: {self.renewed} renewals, last {age}s ago")

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()


def one_at_a_time(fetch, limit: int):
    """Take units one at a time, up to `limit`: a unit is claimed only when its
    work starts, so no claimed unit waits while its lease runs out. The caller
    stops at its first failure: the failed unit waits again at once, and asking
    for the next would claim it again and leave it held."""
    for _ in range(limit):
        found = fetch(1)
        if not found:
            return
        yield found[0]


def work(name: str, run_id: str, reports: str, limit: int) -> int:
    module, artifacts, failed = load_profile(name), Artifacts(), 0
    digest = runtime(module)
    for envelope in one_at_a_time(lambda n: control.claim(run_id, name, n), limit):
        renewal = None
        try:
            with Renewal(envelope) as renewal:
                candidate = module.execute(envelope, artifacts)
                candidate = {"uri": candidate["uri"], "sha256": candidate["sha256"]}
                # The step's own check of what it wrote, once.
                checks, proofs = module.check({**envelope, "candidate": candidate}, artifacts)
            if renewal.error is not None:
                raise renewal.error  # the lease lapsed while the work ran
            if any(value is not True for value in checks.values()):
                raise ValueError("A check failed")
            evidence = artifacts.put(reports, control.report_document(envelope, candidate, checks, proofs, digest))
            control.report(renewal.envelope, candidate, evidence)
        except (Exception, KeyboardInterrupt) as exc:
            if isinstance(exc, KeyboardInterrupt):
                if renewal is None or not renewal.lost:
                    raise  # the operator's own interrupt
                exc = renewal.error
            failed += 1
            state = renewal.state() if renewal is not None else "claimed, not started"
            print(f"{envelope['claim']['step']}/{envelope['claim']['key']}: {exc} [{state}]", file=sys.stderr)
            try:
                control.fail(envelope, type(exc).__name__)
            except control.ControlError:
                pass  # a stale attempt cannot change the current one
            break  # see one_at_a_time
    return 1 if failed else 0


def main(argv=None) -> int:
    from .cli import arguments

    args = arguments(argparse.ArgumentParser(prog="python -m edgar_warehouse.workers")).parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
