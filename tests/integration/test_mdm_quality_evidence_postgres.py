"""MDM quality receipt survives a lost Bookkeeping report and is admitted once.

All records and rules come from the synthetic clean-MDM fixture. The feature gate
is enabled only in this test; the configured-bookkeeping fixture supplies the
isolated disposable PostgreSQL 16 server and never reads provider data.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from edgar_warehouse.bookkeeping.clean import quality as bookkeeping_quality
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts
from edgar_warehouse.bookkeeping.clean.database import grant_profile
from edgar_warehouse.bookkeeping.clean.engine import Bookkeeping
from edgar_warehouse.mdm.store import migrate as migrate_mdm, register_policy
from edgar_warehouse.mastering import reads, store as mastering_store
from edgar_warehouse.rules import frozen
from edgar_warehouse.workers import mastering_merge
from tests.integration.test_configured_bookkeeping_postgres import databases  # noqa: F401
from tests.integration.test_run_pins_postgres import CODE, FIXTURE
from tests.support.bookkeeping_protocol import check_report
from tests.support.rules_authority import register_dataset

CHECK_ID = "fixture_name_allowed"
PASSING_NAME = "Synthetic Allowed Name"
PRIVATE_FAILING_NAME = "SYNTHETIC_PRIVATE_QUALITY_FAILURE"
DEFERRED_NAME = "Synthetic Deferred Identity"
AS_OF = "2026-11-22T00:00:00+00:00"


@pytest.fixture
def registered_quality_source(databases):
    """Register the existing synthetic source contract and quality check."""
    data_admin = create_engine(databases.admin.url.set(database="data"))
    try:
        migrate_mdm(data_admin, application_role="clean_application")
        contract = json.loads((FIXTURE / "dataset.json").read_text(encoding="utf-8"))
        contract["adapter"]["retain_deferred"] = True
        contract["nonblocking_deferred_reasons"] = ["missing_record_identity"]
        contract["quality"] = {
            "version": "fixture-quality-v1",
            "checks": [{
                "id": CHECK_ID,
                "test": "in_set@1",
                "value": "fields.name",
                "on_fail": "flag",
                "args": {"values": [PASSING_NAME]},
            }],
        }
        policy = json.loads((FIXTURE / "policy.json").read_text(encoding="utf-8"))
        with databases.admin.begin() as conn:
            policy_digest = register_policy(conn, policy)
            register_dataset(conn, CODE, str(uuid4()), contract)
        yield data_admin, policy_digest
    finally:
        data_admin.dispose()


def _prepared_manifest(artifacts, root: Path, policy_digest: str) -> dict:
    rows = [
        {"key": "quality-pass", "kind": "company", "name": PASSING_NAME},
        {"key": "quality-fail", "kind": "company", "name": PRIVATE_FAILING_NAME},
        {"kind": "company", "name": DEFERRED_NAME},
    ]
    content = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows).encode()
    records = artifacts.put_bytes((root / "records.jsonl").as_uri(), content)
    manifest = {
        "as_of": AS_OF,
        "batches": [{
            "batch_id": "fixture-quality-batch",
            "stage": "mastering",
            "consumer": "fixture/quality-evidence",
            "expected_checkpoint": 0,
            "checkpoint": 1,
            "input": {
                "path": "records.jsonl",
                "record_count": len(rows),
                "publication": {
                    "publication_key": "fixture-quality-publication",
                    "revision": 1,
                    "effective_at": AS_OF,
                },
                "sha256": records["sha256"],
                "source_code": CODE,
            },
        }],
        "contract_version": 2,
        "policy_digest": policy_digest,
    }
    return artifacts.put(root.as_uri(), manifest)



def _mastering_counts(engine) -> dict:
    store = mastering_store.open_store(engine)
    try:
        return reads.counts(store)
    finally:
        store.close()

def test_mdm_quality_receipt_survives_lost_report_and_is_admitted_once(
    databases, registered_quality_source, tmp_path, monkeypatch
):
    data_admin, policy_digest = registered_quality_source
    # All MDM worker connections point at the disposable integration databases.
    monkeypatch.setenv("DATA_URL", databases.loader["DATA_URL"])
    monkeypatch.setenv("CONTROL_URL", databases.loader["CONTROL_URL"])
    monkeypatch.setenv("MDM_APPLICATION_ROLE", "clean_application")
    monkeypatch.setenv("MASTERING_MERGE_PROCESSES", "1")
    monkeypatch.setenv("MDM_QUALITY_EVIDENCE_V1", "enabled")
    grant_profile(databases.admin, profile="mastering.merge", worker="bk_runtime")

    book = Bookkeeping(databases.runtime)
    prepared = _prepared_manifest(book.artifacts, tmp_path / "prepared", policy_digest)
    unit_key = "fixture-quality-unit"
    output = (tmp_path / "receipts" / "merge.json").as_uri()
    inputs = book.artifacts.put(tmp_path.as_uri() + "/worklist", {
        "version": 2,
        "steps": {"merge": [{"keys": {"unit": unit_key}, "input": prepared,
                              "output": output, "cursor": {}}]},
    })
    name = f"fixture-quality-{uuid4().hex}"
    source = {
        "source": name,
        "bookkeeping": {"version": 2, "targets": {"mastering": {
            "steps": [{"name": "merge", "operation": "mastering.merge", "requires": [],
                       "key": "{unit}", "leases": ["mdm:{unit}"],
                       "checks": [mastering_merge.CHECK, mastering_merge.QUALITY_CHECK], "input": {}}],
            "checks": ["manifest.hash", "work.accounting", "journal.delivered"],
        }}},
    }
    rules_ref = Artifacts().put(tmp_path.as_uri() + "/rules", frozen.of("source", name, source))
    run_id = book.start(rules_ref=rules_ref, inputs_ref=inputs, target="mastering", scope={"test": name})

    claim = book.claim(run_id, "merge", unit_key, sleep=lambda _: None)
    assert claim is not None
    envelope = book.envelope(claim)
    first_candidate = mastering_merge.execute(envelope, book.artifacts)
    first_bytes = book.artifacts.verified(first_candidate)
    first = json.loads(first_bytes)
    quality = first["quality"]
    assert quality["run_id"] == run_id and quality["step"] == "merge"
    (source_evidence,) = quality["sources"]
    assert source_evidence["table"] == CODE
    assert source_evidence["rule_version"] == "fixture-quality-v1"
    assert source_evidence["checks"] == {CHECK_ID: {
        "kind": "in_set@1", "failure_action": "flag", "rows_checked": 2,
        "rows_failed": 1, "rows_expected": 3, "rows_unknown": 1,
    }}
    synthetic_names = (PASSING_NAME, PRIVATE_FAILING_NAME, DEFERRED_NAME)
    assert all(name.encode() not in first_bytes for name in synthetic_names)
    first_counts = _mastering_counts(data_admin)
    assert first_counts["stage_records"] == {CODE: 2}
    assert first_counts["set_aside"] == {"missing_record_identity": 1}

    # The worker wrote its immutable receipt, but the report was lost before Bookkeeping admission.
    with databases.admin.begin() as conn:
        conn.execute(text(
            "UPDATE bookkeeping.lease SET expires_at=clock_timestamp()-interval '1 second' "
            "WHERE attempt=CAST(:attempt AS uuid)"
        ), {"attempt": claim.attempt})
    book.resume(run_id)
    replay_claim = book.claim(run_id, "merge", unit_key, sleep=lambda _: None)
    assert replay_claim is not None and replay_claim.attempt != claim.attempt
    replay_envelope = book.envelope(replay_claim)
    replay_candidate = mastering_merge.execute(replay_envelope, book.artifacts)
    replay_bytes = book.artifacts.verified(replay_candidate)
    assert replay_candidate == first_candidate
    assert replay_bytes == first_bytes
    assert json.loads(replay_bytes)["quality"]["observed_at"] == quality["observed_at"]
    assert _mastering_counts(data_admin) == first_counts  # the full public MDM readback is unchanged on replay
    checks, _ = mastering_merge.check(
        {**replay_envelope, "candidate": replay_candidate}, book.artifacts
    )
    assert checks == {mastering_merge.CHECK: True, mastering_merge.QUALITY_CHECK: True}
    report = check_report(book, replay_envelope, replay_candidate, mastering_merge)
    book.report(replay_envelope, replay_candidate, report)
    book.deliver(databases.ledger, run_id, limit=1000)
    state = book.finalize(run_id)
    assert state["run"]["state"] == "complete"

    admitted = bookkeeping_quality.aggregate(book, run_id)
    assert admitted["status"] == "unknown"  # the identity-deferred row is not a passing or failing check
    assert admitted["checks"] == [{
        "step": "merge", "table": CODE, "check": CHECK_ID, "kind": "in_set@1",
        "rule_version": "fixture-quality-v1",
        "failure_action": "flag", "units": 1, "rows_checked": 2, "rows_failed": 1,
        "rows_unknown": 1, "status": "unknown",
    }]
    assert all(name not in json.dumps(admitted) for name in synthetic_names)
