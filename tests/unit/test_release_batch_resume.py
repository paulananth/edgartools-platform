"""Ticket 20 P0/P2: batch done markers, remaining batches, artifact progress."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    LedgerError,
    batch_done_marker_path,
    batch_identity_for_ciks,
    build_batch_done_marker,
    build_remaining_cik_batches,
    list_done_batch_identities,
    parse_cik_batches_jsonl,
    release_freeze_prefix_from_path,
    validate_and_rebind_done_batch_ledger,
)
from edgar_warehouse.infrastructure.object_storage import (
    list_uri_child_names,
    write_uri_text,
)
from edgar_warehouse.scripts.build_remaining_release_batches import main as remaining_main


def test_batch_identity_is_stable_and_order_independent() -> None:
    assert batch_identity_for_ciks([3, 1, 2]) == batch_identity_for_ciks(["2", "1", "3"])
    assert len(batch_identity_for_ciks([1, 2])) == 16


def test_release_freeze_prefix_from_manifest_path() -> None:
    assert (
        release_freeze_prefix_from_path(
            "s3://bucket/warehouse/bronze/reference/relationship_release/run1/candidate_manifest.json"
        )
        == "s3://bucket/warehouse/bronze/reference/relationship_release/run1/"
    )


def test_build_remaining_cik_batches_drops_done() -> None:
    batches = [
        {"cik_list": "1,2"},
        {"cik_list": "3,4"},
        {"cik_list": "5"},
    ]
    done = {batch_identity_for_ciks([1, 2]), batch_identity_for_ciks([5])}
    remaining = build_remaining_cik_batches(batches, done)
    assert remaining == [{"cik_list": "3,4"}]


def test_parse_cik_batches_jsonl_and_marker_names(tmp_path: Path) -> None:
    identity = batch_identity_for_ciks([10, 20])
    rows = parse_cik_batches_jsonl('{"cik_list":"10,20"}\n{"cik_list":"30"}\n')
    assert len(rows) == 2
    done = list_done_batch_identities([f"{identity}.json", "not-a-marker.txt", "zz.json"])
    assert done == {identity}


def test_batch_done_marker_path_and_payload() -> None:
    path = batch_done_marker_path(
        "s3://b/freeze/",
        batch_identity_for_ciks([1]),
    )
    assert path.endswith(".json")
    assert "/batch_done/" in path
    marker = build_batch_done_marker(
        batch_identity=batch_identity_for_ciks([1]),
        ciks=[1],
        generation_id="run-1",
        inventory_fingerprint="inv",
        ledger_path="s3://b/ledger.json",
        ledger_fingerprint="led",
        terminal_counts={"applicable_loaded": 2},
        candidate_count=2,
        completed_at="2026-07-18T00:00:00Z",
    )
    assert marker["batch_identity"] == batch_identity_for_ciks([1])
    assert marker["terminal_counts"]["applicable_loaded"] == 2


def test_build_remaining_release_batches_script(tmp_path: Path) -> None:
    batches = tmp_path / "candidate_batches.jsonl"
    batches.write_text(
        '{"cik_list":"1,2"}\n{"cik_list":"3"}\n{"cik_list":"4,5"}\n',
        encoding="utf-8",
    )
    done_id = batch_identity_for_ciks([1, 2])
    done_dir = tmp_path / "batch_done"
    done_dir.mkdir()
    (done_dir / f"{done_id}.json").write_text("{}", encoding="utf-8")
    out = tmp_path / "remaining.jsonl"
    rc = remaining_main(
        [
            "--candidate-batches",
            str(batches),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    remaining_rows = parse_cik_batches_jsonl(out.read_text(encoding="utf-8"))
    assert remaining_rows == [{"cik_list": "3"}, {"cik_list": "4,5"}]


def test_done_marker_rebinds_valid_prior_ledger_to_resume_generation() -> None:
    outcomes = [
        {
            "generation_id": "old-run",
            "accession_number": "acc-1",
            "candidate_fingerprint": "candidate-1",
            "status": "applicable_loaded",
            "evidence_fingerprint": "evidence-1",
        },
        {
            "generation_id": "old-run",
            "accession_number": "acc-2",
            "candidate_fingerprint": "candidate-2",
            "status": "not_applicable",
            "evidence_fingerprint": "evidence-2",
        },
    ]
    fingerprint_payload = sorted(outcomes, key=lambda row: row["accession_number"])
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    ledger = {
        "generation_id": "old-run",
        "inventory_fingerprint": "inventory-1",
        "terminal_counts": {"applicable_loaded": 1, "not_applicable": 1},
        "fingerprint": fingerprint,
        "outcomes": outcomes,
    }
    marker = build_batch_done_marker(
        batch_identity=batch_identity_for_ciks([1, 2]),
        ciks=[1, 2],
        generation_id="old-run",
        inventory_fingerprint="inventory-1",
        ledger_path="s3://warehouse/release-evidence/old-run/ledger.json",
        ledger_fingerprint=fingerprint,
        terminal_counts={"applicable_loaded": 1, "not_applicable": 1},
        candidate_count=2,
        completed_at="2026-07-24T00:00:00Z",
    )

    rebound = validate_and_rebind_done_batch_ledger(
        marker,
        ledger,
        inventory_fingerprint="inventory-1",
        generation_id="new-run",
    )

    assert rebound["generation_id"] == "new-run"
    assert {row["generation_id"] for row in rebound["outcomes"]} == {"new-run"}
    assert {row["generation_id"] for row in ledger["outcomes"]} == {"old-run"}


def test_done_marker_rejects_tampered_prior_ledger() -> None:
    ledger = {
        "generation_id": "old-run",
        "inventory_fingerprint": "inventory-1",
        "terminal_counts": {"applicable_loaded": 1},
        "fingerprint": "tampered",
        "outcomes": [{
            "generation_id": "old-run",
            "accession_number": "acc-1",
            "candidate_fingerprint": "candidate-1",
            "status": "applicable_loaded",
            "evidence_fingerprint": "evidence-1",
        }],
    }
    marker = build_batch_done_marker(
        batch_identity=batch_identity_for_ciks([1]),
        ciks=[1],
        generation_id="old-run",
        inventory_fingerprint="inventory-1",
        ledger_path="s3://warehouse/release-evidence/old-run/ledger.json",
        ledger_fingerprint="tampered",
        terminal_counts={"applicable_loaded": 1},
        candidate_count=1,
        completed_at="2026-07-24T00:00:00Z",
    )

    with pytest.raises(LedgerError, match="fingerprint"):
        validate_and_rebind_done_batch_ledger(
            marker,
            ledger,
            inventory_fingerprint="inventory-1",
            generation_id="new-run",
        )


def test_list_uri_child_names_local(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")
    (tmp_path / "b.json").write_text("{}", encoding="utf-8")
    names = list_uri_child_names(str(tmp_path))
    assert set(names) == {"a.json", "b.json"}


def test_write_uri_text_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "marker.json"
    write_uri_text(str(target), '{"ok":true}\n')
    assert json.loads(target.read_text(encoding="utf-8"))["ok"] is True


def test_invalid_batch_identity_rejected() -> None:
    with pytest.raises(InventoryError, match="invalid batch identity"):
        batch_done_marker_path("s3://b/f/", "not-hex")


def test_accession_done_marker_roundtrip_and_skip(tmp_path: Path) -> None:
    from datetime import date

    from edgar_warehouse.application.relationship_bulk_load import (
        RelationshipSourceCandidate,
        accession_done_marker_path,
        build_accession_done_marker,
        load_terminal_accession_outcomes,
        terminal_outcome_from_accession_marker,
    )

    candidate = RelationshipSourceCandidate(
        accession_number="0000320193-24-000001",
        cik=320193,
        form="8-K",
        filing_date=date(2024, 5, 1),
        report_date=None,
        relationship_type="EMPLOYED_BY",
        candidate_reason="item_5_02_metadata",
        artifact_required=True,
        source_index_identity="2024Q2",
        source_manifest_fingerprint="src",
        fingerprint="cand-fp-1",
    )
    freeze = str(tmp_path) + "/"
    marker = build_accession_done_marker(
        accession_number=candidate.accession_number,
        candidate_fingerprint=candidate.fingerprint,
        inventory_fingerprint="inv-fp",
        status="applicable_loaded",
        evidence_fingerprint="ev-fp",
        generation_id="run-old",
        completed_at="2026-07-18T00:00:00Z",
    )
    path = accession_done_marker_path(freeze, candidate.accession_number)
    write_uri_text(path, json.dumps(marker) + "\n")

    loaded = load_terminal_accession_outcomes(
        freeze_prefix=freeze,
        candidates=[candidate],
        inventory_fingerprint="inv-fp",
        generation_id="run-new",
        read_text=lambda p: Path(p).read_text(encoding="utf-8"),
    )
    assert candidate.accession_number in loaded
    assert loaded[candidate.accession_number].status == "applicable_loaded"
    assert loaded[candidate.accession_number].generation_id == "run-new"

    # Stale candidate fingerprint must not resume.
    stale = terminal_outcome_from_accession_marker(
        marker,
        candidate=RelationshipSourceCandidate(
            **{**candidate.__dict__, "fingerprint": "other"},
        ),
        inventory_fingerprint="inv-fp",
        generation_id="run-new",
    )
    assert stale is None
