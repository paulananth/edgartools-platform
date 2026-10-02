"""Drive Bookkeeping's task protocol in-process, for control tests.

Production workers are separate processes (`python -m edgar_warehouse.workers`)
and are tested end to end; these helpers call the same protocol methods a
worker's commands call, so a control test stays fast and exact.
"""
from __future__ import annotations

from edgar_warehouse.workers import copy

RUNTIME = "a" * 64
WORKERS = {"artifact.copy": copy}


def reports_root(envelope: dict) -> str:
    return envelope["output"].rsplit("/", 1)[0] + "/reports"


def verification_report(book, verification: dict, worker) -> dict:
    checks, proofs = worker.verify(verification, book.artifacts)
    claim = verification["claim"]
    report = {"protocol": verification["protocol"], "checks": checks, "proofs": proofs,
              "binding": {"run_id": claim["run_id"], "step": claim["step"], "key": claim["key"],
                          "attempt": claim["attempt"], "effect_key": verification["effect_key"],
                          "candidate": verification["candidate"]}}
    return book.artifacts.put(reports_root(verification), report)


def envelope_for(book, claim) -> dict:
    return book.envelope(claim)


def verification_for(book, rid: str, step: str, key: str, profile: str = "artifact.copy") -> dict:
    return next(v for v in book.verifications(rid, profile, limit=1000)
                if (v["claim"]["step"], v["claim"]["key"]) == (step, key))


def complete(book, rid, key="0", step="s0", worker=copy, profile="artifact.copy"):
    """Claim, work, report, verify and admit one unit."""
    claim = book.claim(rid, step, key, sleep=lambda _: None)
    assert claim
    envelope = book.envelope(claim)
    candidate = worker.execute(envelope, book.artifacts)
    book.report(envelope, candidate, RUNTIME)
    verification = verification_for(book, rid, step, key, profile)
    report = verification_report(book, verification, worker)
    book.admit(verification, report)
    receipt = {"uri": candidate["uri"], "sha256": candidate["sha256"], "evidence": report}
    return claim, receipt


def drive(book, rid, ledger, *, workers=None, limit=1000) -> dict:
    """Work every step in order until nothing more can run, then deliver
    control's events and record the run's checks (the runner's old order)."""
    from sqlalchemy import text

    workers = workers or WORKERS
    _, config, _, _ = book._frozen(rid)
    done = 0
    for step in config["steps"]:
        worker = workers[step["operation"]]
        with book.engine.connect() as conn:
            keys = conn.scalars(text("SELECT unit_key FROM bookkeeping.work_item WHERE run_id=CAST(:r AS uuid) "
                                     "AND step=:s AND state<>'verified' ORDER BY ordinal LIMIT :n"),
                                {"r": rid, "s": step["name"], "n": limit - done}).all()
        for key in keys:
            claim = book.claim(rid, step["name"], key, sleep=lambda _: None)
            if claim is None:
                continue
            envelope = book.envelope(claim)
            book.report(envelope, worker.execute(envelope, book.artifacts), RUNTIME)
            verification = verification_for(book, rid, step["name"], key, step["operation"])
            book.admit(verification, verification_report(book, verification, worker))
            done += 1
        if done >= limit:
            break
    book.deliver(ledger, rid, limit=1000)
    return book.finalize(rid)
