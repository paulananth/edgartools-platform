"""The workers' only way to reach Bookkeeping: its commands, in a subprocess."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import threading


class ControlError(RuntimeError):
    pass


class Session:
    """One long-lived `bookkeeping serve` child, so a worker pays for a process and a connection once, not
    per command (a hosted store: about 2 s a command became about 0.3 s). Commands go one at a time, under a
    lock. A thread that must not wait on another's command (the lease renewal) takes its own Session."""

    def __init__(self, command: list[str] | None = None):
        self.command = command or [sys.executable, "-m", "edgar_warehouse.bookkeeping", "serve"]
        self.child, self.lock = None, threading.Lock()

    def _start(self):
        self.child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True)

    def close(self):
        with self.lock:
            self._stop()

    def _stop(self):
        child, self.child = self.child, None
        if child is not None:
            child.kill()
            child.wait()

    def ask(self, arguments: tuple[str, ...], document: dict | None = None):
        request = json.dumps({"argv": list(arguments), "document": document})
        with self.lock:
            if self.child is None or self.child.poll() is not None:
                self._start()
            # Bounded: a hung control call must not outlive the lease it serves; kill it, the next ask starts anew.
            timer = threading.Timer(TIMEOUT, self.child.kill)
            timer.start()
            try:
                self.child.stdin.write(request + "\n")
                self.child.stdin.flush()
                line = self.child.stdout.readline()
            except (BrokenPipeError, OSError):
                line = ""
            finally:
                timer.cancel()
            if not line:
                self._stop()
                raise ControlError("Bookkeeping session ended or timed out")
        reply = json.loads(line)
        if "error" in reply:
            raise ControlError(_reason(reply["error"]) or "Bookkeeping command failed")
        return reply["result"]


TIMEOUT = 300
# The lease renewal never waits behind another command: it has its own session, kept for every unit of the run.
_sessions = {"commands": Session(), "renewals": Session()}


def call(*arguments: str, document: dict | None = None, session: str = "commands"):
    """Run one Bookkeeping command through a session; a document goes in with the command."""
    return _sessions[session].ask(arguments, document)


def _reason(stderr: str) -> str:
    """The failure's own line: a database error's message (`(psycopg2.errors.X) ...`), not the SQL, its
    parameters (they can hold data values) or SQLAlchemy's closing link; else the last line."""
    lines = [line.strip() for line in stderr.strip().splitlines() if line.strip()]
    database = [line for line in lines if re.search(r"\(psycopg2?\.errors\.", line)]
    return (database[-1] if database else lines[-1]) if lines else ""


def report_document(verification: dict, checks: dict, proofs: list, runtime: str) -> dict:
    """A verifier's report: its checks and its own runtime, bound to exactly
    this work and candidate."""
    claim = verification["claim"]
    return {"protocol": verification["protocol"], "checks": checks, "proofs": proofs, "runtime": runtime,
            "binding": {"run_id": claim["run_id"], "step": claim["step"], "key": claim["key"],
                        "attempt": claim["attempt"], "effect_key": verification["effect_key"],
                        "candidate": verification["candidate"]}}


def claim(run_id: str, profile: str, limit: int) -> list[dict]:
    return call("claim", run_id, "--profile", profile, "--limit", str(limit))


def verifications(run_id: str, profile: str, limit: int) -> list[dict]:
    return call("verifications", run_id, "--profile", profile, "--limit", str(limit))


def renew(envelope: dict) -> dict:
    return call("renew", "--envelope", "-", document=envelope, session="renewals")


def report(envelope: dict, candidate: dict, runtime: str) -> dict:
    return call("report", "--envelope", "-", "--candidate", candidate["uri"], "--sha256", candidate["sha256"],
                "--runtime", runtime, document=envelope)


def fail(envelope: dict, message: str) -> None:
    call("fail", "--envelope", "-", "--message", message, document=envelope)


def admit(verification: dict, report_ref: dict) -> dict:
    return call("admit", "--verification", "-", "--report", report_ref["uri"], "--sha256", report_ref["sha256"],
                document=verification)
