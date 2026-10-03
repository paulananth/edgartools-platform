"""Drive Bookkeeping's task protocol in-process, for control tests.

Production workers are separate processes (`python -m edgar_warehouse.workers`)
and are tested end to end; these helpers call the same protocol methods a
worker's commands call, so a control test stays fast and exact.
"""
from __future__ import annotations

from edgar_warehouse.workers import copy
from edgar_warehouse.workers.control import report_document

RUNTIME = "a" * 64
WORKERS = {"artifact.copy": copy}


def verifier_of(book):
    """The verifier's own login: never the one that reported (to-do 20b)."""
    return getattr(book, "verifier", book)


def reports_root(envelope: dict) -> str:
    return envelope["output"].rsplit("/", 1)[0] + "/reports"


def verification_report(book, verification: dict, worker) -> dict:
    checks, proofs = worker.verify(verification, book.artifacts)
    return book.artifacts.put(reports_root(verification), report_document(verification, checks, proofs, RUNTIME))


def envelope_for(book, claim) -> dict:
    return book.envelope(claim)


def verification_for(book, rid: str, step: str, key: str, profile: str = "artifact.copy") -> dict:
    return next(v for v in verifier_of(book).verifications(rid, profile, limit=1000)
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
    verifier_of(book).admit(verification, report)
    receipt = {"uri": candidate["uri"], "sha256": candidate["sha256"], "evidence": report}
    return claim, receipt


def drive(book, rid, ledger, *, workers=None, limit=1000) -> dict:
    """What a worker and a verifier per profile do, in step order, until
    nothing more can run; then deliver control's events and record the run's
    checks. Claims go through `tasks`, as the worker commands' do."""
    workers = workers or WORKERS
    _, config, _, _ = book._frozen(rid)
    done = 0
    for step in config["steps"]:
        profile = step["operation"]
        worker = workers[profile]
        while done < limit:
            envelopes = book.tasks(rid, profile, limit=limit - done)
            for envelope in envelopes:
                book.report(envelope, worker.execute(envelope, book.artifacts), RUNTIME)
            for verification in verifier_of(book).verifications(rid, profile, limit=1000):
                verifier_of(book).admit(verification, verification_report(book, verification, worker))
                done += 1
            if not envelopes:
                break
    book.deliver(ledger, rid, limit=1000)
    return book.finalize(rid)
