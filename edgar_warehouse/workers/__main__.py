"""Run a worker or a verifier for one profile against one Bookkeeping run.

    python -m edgar_warehouse.workers work   <profile> <run_id> [--limit N]
    python -m edgar_warehouse.workers verify <profile> <run_id> --reports <URI> [--limit N]

`edgar-warehouse workers …` takes the same arguments (`cli.py`).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import threading
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

    The renewed proof is also written into the envelope the work holds
    (`claim.proof`), so a destination that fences its own transaction with it
    (MDM, `bookkeeping_guard`) always checks the current lease.
    """

    def __init__(self, envelope: dict):
        self.envelope, self.error, self.live = envelope, None, envelope
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self.stop.wait(self.envelope["heartbeat_seconds"]):
            try:
                self.envelope = control.renew(self.envelope)
                self.live["claim"] = {**self.live["claim"], "proof": self.envelope["claim"]["proof"]}
            except Exception as exc:  # the report then fails on the stale lease
                self.error = exc
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()


def work(name: str, run_id: str, limit: int) -> int:
    module, artifacts, failed = load_profile(name), Artifacts(), 0
    digest = runtime(module)
    for envelope in control.claim(run_id, name, limit):
        try:
            with Renewal(envelope) as renewal:
                candidate = module.execute(envelope, artifacts)
            if renewal.error is not None:
                raise renewal.error  # the lease lapsed while the work ran
            control.report(renewal.envelope, candidate, digest)
        except Exception as exc:
            failed += 1
            print(f"{envelope['claim']['step']}/{envelope['claim']['key']}: {exc}", file=sys.stderr)
            try:
                control.fail(envelope, type(exc).__name__)
            except control.ControlError:
                pass  # a stale attempt cannot change the current one
    return 1 if failed else 0


def verify(name: str, run_id: str, reports: str, limit: int) -> int:
    module, artifacts, failed = load_profile(name), Artifacts(), 0
    digest = runtime(module)
    for verification in control.verifications(run_id, name, limit):
        claim = verification["claim"]
        try:
            with Renewal(verification) as renewal:
                checks, proofs = module.verify(verification, artifacts)
            if renewal.error is not None:
                raise renewal.error
            if any(value is not True for value in checks.values()):
                raise ValueError("A check failed")
            control.admit({**renewal.envelope, "candidate": verification["candidate"]},
                          artifacts.put(reports, control.report_document(verification, checks, proofs, digest)))
        except Exception as exc:
            failed += 1
            print(f"{claim['step']}/{claim['key']}: {exc}", file=sys.stderr)
            try:
                control.fail(verification, type(exc).__name__)
            except control.ControlError:
                pass
    return 1 if failed else 0


def main(argv=None) -> int:
    from .cli import arguments

    args = arguments(argparse.ArgumentParser(prog="python -m edgar_warehouse.workers")).parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
