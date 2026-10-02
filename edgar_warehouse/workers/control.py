"""The workers' only way to reach Bookkeeping: its commands, in a subprocess."""
from __future__ import annotations

import json
import subprocess
import sys


class ControlError(RuntimeError):
    pass


def call(*arguments: str, document: dict | None = None):
    """Run one Bookkeeping command; a document goes in through stdin."""
    command = [sys.executable, "-m", "edgar_warehouse.bookkeeping", *arguments]
    # Bounded: a hung control call must not outlive the lease it serves.
    done = subprocess.run(command, input=None if document is None else json.dumps(document),
                          capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise ControlError(done.stderr.strip().splitlines()[-1] if done.stderr.strip() else f"exit {done.returncode}")
    return json.loads(done.stdout)


def report_document(verification: dict, checks: dict, proofs: list) -> dict:
    """A verifier's report: its checks, bound to exactly this work and candidate."""
    claim = verification["claim"]
    return {"protocol": verification["protocol"], "checks": checks, "proofs": proofs,
            "binding": {"run_id": claim["run_id"], "step": claim["step"], "key": claim["key"],
                        "attempt": claim["attempt"], "effect_key": verification["effect_key"],
                        "candidate": verification["candidate"]}}


def claim(run_id: str, profile: str, limit: int) -> list[dict]:
    return call("claim", run_id, "--profile", profile, "--limit", str(limit))


def verifications(run_id: str, profile: str, limit: int) -> list[dict]:
    return call("verifications", run_id, "--profile", profile, "--limit", str(limit))


def renew(envelope: dict) -> dict:
    return call("renew", "--envelope", "-", document=envelope)


def report(envelope: dict, candidate: dict, runtime: str) -> dict:
    return call("report", "--envelope", "-", "--candidate", candidate["uri"], "--sha256", candidate["sha256"],
                "--runtime", runtime, document=envelope)


def fail(envelope: dict, message: str) -> None:
    call("fail", "--envelope", "-", "--message", message, document=envelope)


def admit(verification: dict, report_ref: dict) -> dict:
    return call("admit", "--verification", "-", "--report", report_ref["uri"], "--sha256", report_ref["sha256"],
                document=verification)
