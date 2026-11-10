"""The recovery proof for version-2 silver quality evidence (openmetadata-quality-evidence ticket 04).

One disposable run over invented company-facts files: the `silver.land` step asks
for `silver.quality.evidence.v2`, the run is interrupted, and `bookkeeping resume`
reopens it. Two interruption shapes are proven, because they fail differently:

- the receipt was written and reported, and the verifier never admitted it: the
  verifier admits the retained receipt after the resume;
- the receipt was written but the report was lost (the worker stopped between
  writing its output and reporting it): the unit is re-executed after its lease
  ends, and the re-execution must reconcile with the retained output.

No provider data is read: every document here is invented, and every store is a
disposable PostgreSQL 16 container.
"""
from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text

from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.bookkeeping.clean.quality import aggregate
from edgar_warehouse.mdm import target_manifest
from edgar_warehouse.rules import files
from edgar_warehouse.silver_writer import database as silver
from edgar_warehouse.silver_writer.cli import spec_file
from edgar_warehouse.workers import silver_land, source_read
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.integration.test_silver_writer_postgres import RUNTIME as SILVER_RUNTIME, silver_database
from tests.support.bookkeeping_protocol import RUNTIME, verification_report
from tests.support.memory_journal import MemoryJournal

SOURCE = "sec.company-facts"
FOLDER = files.ROOT / "sources" / SOURCE
WORKERS = {"source.read": source_read, "silver.land": silver_land}
FILING = {"accn": "0000000042-26-000001", "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-01"}
CHECKS = {"one_form_per_filing", "one_filed_per_filing", "one_fiscal_year_filed_per_filing",
          "one_fiscal_period_filed_per_filing", "period_start_not_after_end"}


def document(cik: int) -> bytes:
    """One invented company-facts file: two facts, one of them a duration."""
    body = {"cik": cik, "facts": {"us-gaap": {"Revenues": {"label": "Revenues", "units": {"USD": [
        {"start": "2025-01-01", "end": "2025-12-31", "val": 123456789012345678901, "frame": "CY2025", **FILING},
        {"end": "2025-12-31", "val": 7, **FILING}]}}}}}
    return json.dumps(body).encode()


def key(cik: int) -> str:
    return f"warehouse/bronze/company_facts/sec/cik={cik:010d}/{cik:010d}.json"


def capture(tmp_path, ciks):
    """A capture of invented company-facts files, with its receipts."""
    receipts = []
    for cik in ciks:
        raw = document(cik)
        path = tmp_path / "capture" / "bronze" / key(cik).removeprefix("warehouse/bronze/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipts.append({"bytes": len(raw), "key": key(cik), "sha256": hashlib.sha256(raw).hexdigest()})
    (tmp_path / "capture" / "receipts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in receipts))
    listed = tmp_path / "documents.json"
    listed.write_text(json.dumps([key(cik) for cik in ciks]))
    return {"source": SOURCE, "target": "silver", "capture": str(tmp_path / "capture"), "documents": str(listed),
            "capture_run": "capture-1", "output": str(tmp_path / "bundle"), "as_of": "2026-11-02T00:00:00Z",
            "revision": 0, "journal": MemoryJournal()}


def recovery_target():
    """The source's `silver` target, with one landing that asks for version-2 evidence.

    The target keeps its read step and its landing; the derived tables and the
    Change Journal step are dropped, because this proof is about the landing's
    receipt and its resume, not the derivation.
    """
    reading = files.source(SOURCE)
    target = deepcopy(reading["bookkeeping"]["targets"]["silver"])
    target["steps"] = [step for step in target["steps"] if step["name"] in ("facts", "land")]
    for step in target["steps"]:
        if step["name"] == "land":
            step["checks"] = ["input.hash", "output.receipt", "silver.landed", "silver.quality.evidence.v2"]
            step["input"]["keys"]["silver"] = "recovery_fact"
    return target


def submit(databases, tmp_path, book, report, target):
    """The target as an active Rules document, with its manifest frozen."""
    body = {"source": f"facts-{uuid4().hex}", "bookkeeping": {"version": 2, "targets": {"silver": target}}}
    steps = book.artifacts.json(report["manifest"])["steps"]
    steps = {name: units for name, units in steps.items() if name in ("facts", "land")}
    for unit in steps["land"]:
        unit["keys"]["silver"] = "recovery_fact"
    manifest = book.artifacts.put(tmp_path.as_uri() + "/submitted", {"version": 2, "steps": steps})
    saved = databases.rules.save("source", body["source"], "1", body)
    databases.rules.prove("source", body["source"], "1",
                          {"digest": saved["digest"], "batch_hash": manifest["sha256"], "passed": True})
    databases.rules.activate("source", body["source"], "1")
    rules = databases.rules.resolve("source", body["source"], root=tmp_path.as_uri() + "/rules")
    rid = book.start(rules_ref=rules, inputs_ref=manifest, target="silver", scope={"test": body["source"]})
    return rid


def expire(databases, claim):
    """End a claim's lease, so its unit can be claimed again."""
    with databases.admin.begin() as conn:
        conn.execute(text("UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' "
                           "WHERE attempt=CAST(:a AS uuid)"), {"a": claim.attempt})


def read_units(book, rid):
    """Work and verify the run's read step; its units are what the landings read."""
    for envelope in book.tasks(rid, "source.read", limit=10):
        book.report(envelope, source_read.execute(envelope, book.artifacts), RUNTIME)
    for verification in book.verifier.verifications(rid, "source.read", limit=10):
        book.verifier.admit(verification, verification_report(book, verification, source_read))


def work_landings(book, rid):
    """Work and verify every landing the run can offer."""
    for envelope in book.tasks(rid, "silver.land", limit=10):
        book.report(envelope, silver_land.execute(envelope, book.artifacts), RUNTIME)
    for verification in book.verifier.verifications(rid, "silver.land", limit=10):
        book.verifier.admit(verification, verification_report(book, verification, silver_land))


@pytest.fixture
def recovery_run(databases, tmp_path, monkeypatch):
    """A submitted run over two invented files, with its disposable silver table."""
    for profile in WORKERS:
        grant_profile(databases.admin, profile=profile, worker="bk_runtime", verifier="bk_verifier")
    monkeypatch.setenv(silver_land.QUALITY_V2_GATE, "enabled")
    report = target_manifest.write_manifest(**capture(tmp_path, [42, 43]))
    book = Bookkeeping(databases.runtime)
    book.verifier = Bookkeeping(databases.verifier, artifacts=book.artifacts)
    rid = submit(databases, tmp_path, book, report, recovery_target())

    with silver_database(databases.admin) as (owner, runtime):
        silver.migrate(owner, runtime_role=SILVER_RUNTIME)
        # The disposable silver table: the source's own company_fact spec without
        # its Company link, because this proof is about the receipt and the
        # resume, not about MDM ids.
        spec = deepcopy(spec_file(FOLDER / "silver-company-fact.yaml", None))
        spec["table"] = "recovery_fact"
        spec["links"] = []
        assert silver.register(owner, spec, runtime_role=SILVER_RUNTIME)["created"]
        monkeypatch.setattr(silver_land, "engines", lambda: (runtime, None))
        monkeypatch.setattr(runtime, "dispose", lambda: None)
        read_units(book, rid)
        land_keys = [unit["keys"]["unit"] for unit in book.artifacts.json(report["manifest"])["steps"]["land"]]
        yield book, rid, runtime, land_keys, databases.ledger


def test_a_reported_but_unadmitted_version_2_landing_resumes_and_is_admitted(recovery_run):
    """The receipt was reported and the verifier stopped: the resume admits it."""
    book, rid, runtime, land_keys, ledger = recovery_run
    claim = book.claim(rid, "land", land_keys[0])
    envelope = book.envelope(claim)
    candidate = silver_land.execute(envelope, book.artifacts)
    book.report(envelope, candidate, RUNTIME)
    assert book.status(rid)["counts"] == {"verified": 1, "reported": 1}

    started = time.monotonic()
    reopened = book.resume(rid)
    for verification in book.verifier.verifications(rid, "silver.land", limit=10):
        book.verifier.admit(verification, verification_report(book, verification, silver_land))
    work_landings(book, rid)
    book.deliver(ledger, rid, limit=1000)
    state = book.finalize(rid)
    elapsed = time.monotonic() - started

    assert reopened["run"]["state"] == "running"
    assert state["run"]["state"] == "complete"
    assert state["counts"] == {"verified": 2}  # one reading, one landing
    with runtime.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM silver.recovery_fact")).scalar()
    assert rows == 4  # two files, two facts each, landed once

    summary = aggregate(book, rid)
    assert summary["status"] == "passed"
    assert summary["units_expected"] == 1 and summary["units_verified"] == 1
    assert {result["check"] for result in summary["results"]} == CHECKS

    print(f"\nRESUME_SECONDS={elapsed:.3f}\n")
    assert elapsed < 300


def test_a_lost_report_is_reconciled_by_the_re_execution(recovery_run, databases):
    """The receipt was written but the report was lost: the re-execution reconciles."""
    book, rid, runtime, land_keys, ledger = recovery_run
    claim = book.claim(rid, "land", land_keys[0])
    envelope = book.envelope(claim)
    candidate = silver_land.execute(envelope, book.artifacts)
    retained = book.artifacts.verified(candidate)
    # The worker stopped here: the receipt is on disk, the report was never made.
    assert book.status(rid)["counts"] == {"verified": 1, "running": 1}
    expire(databases, claim)

    started = time.monotonic()
    book.resume(rid)
    work_landings(book, rid)
    book.deliver(ledger, rid, limit=1000)
    state = book.finalize(rid)
    elapsed = time.monotonic() - started

    assert state["run"]["state"] == "complete"
    summary = aggregate(book, rid)
    assert summary["units_expected"] == 1 and summary["units_verified"] == 1
    assert summary["status"] == "passed"
    # The re-execution wrote the same receipt: the unit's evidence is unchanged.
    assert book.artifacts.verified({"uri": candidate["uri"], "sha256": candidate["sha256"]}) == retained
    with runtime.connect() as conn:
        rows = conn.execute(text("SELECT count(*) FROM silver.recovery_fact")).scalar()
    assert rows == 4  # two files, two facts each, landed once
    print(f"\nRESUME_SECONDS={elapsed:.3f}\n")
