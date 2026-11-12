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


def reports_root(envelope: dict) -> str:
    return envelope["output"].rsplit("/", 1)[0] + "/reports"


def check_report(book, envelope: dict, candidate: dict, worker) -> dict:
    """The worker's own check of what it wrote, stored as its report."""
    candidate = {"uri": candidate["uri"], "sha256": candidate["sha256"]}
    checks, proofs = worker.check({**envelope, "candidate": candidate}, book.artifacts)
    return book.artifacts.put(reports_root(envelope), report_document(envelope, candidate, checks, proofs, RUNTIME))


def envelope_for(book, claim) -> dict:
    return book.envelope(claim)


def finish(book, envelope: dict, worker) -> dict:
    """Work, check and report one claimed unit; its receipt."""
    candidate = worker.execute(envelope, book.artifacts)
    report = check_report(book, envelope, candidate, worker)
    book.report(envelope, candidate, report)
    return {"uri": candidate["uri"], "sha256": candidate["sha256"],
            "evidence": {"uri": report["uri"], "sha256": report["sha256"]}}


def complete(book, rid, key="0", step="s0", worker=copy, profile="artifact.copy"):
    """Claim, work, check and report one unit."""
    claim = book.claim(rid, step, key, sleep=lambda _: None)
    assert claim
    return claim, finish(book, book.envelope(claim), worker)


def drive(book, rid, ledger, *, workers=None, limit=1000) -> dict:
    """What a worker per profile does, in step order, until nothing more can
    run; then deliver control's events and record the run's checks. Claims go
    through `tasks`, as the worker commands' do."""
    workers = workers or WORKERS
    _, config, _, _ = book._frozen(rid)
    done = 0
    for step in config["steps"]:
        profile = step["operation"]
        worker = workers[profile]
        while done < limit:
            envelopes = book.tasks(rid, profile, limit=limit - done)
            for envelope in envelopes:
                finish(book, envelope, worker)
                done += 1
            if not envelopes:
                break
    book.deliver(ledger, rid, limit=1000)
    return book.finalize(rid)
