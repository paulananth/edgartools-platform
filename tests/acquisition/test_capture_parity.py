"""Ticket 51: 1-CIK then 100-CIK filing_artifact capture-parity harness.

Ticket 10 Decision 2: gated capture must be equal-or-superset of legacy
for the same window, with zero silent gaps. This file tests the compare
seam with constructed snapshots — no SEC network, no warehouse orchestrator.
"""
from __future__ import annotations

from pathlib import Path

from edgar_warehouse.acquisition.capture_parity import (
    APPLE_CIK,
    CaptureArtifact,
    CaptureSnapshot,
    artifact_from_silver_raw_object,
    artifact_from_source_fetch_decision,
    compare_capture_snapshots,
    evaluate_capture_parity_files,
    filter_discovery_rows_by_cik,
    load_capture_snapshot,
    resolve_parity_scope,
    should_record_family_catchup,
    write_capture_snapshot,
)
from edgar_warehouse.acquisition.discovery import DiscoveryCandidate


def _key(cik: int, accession: str) -> str:
    return DiscoveryCandidate(
        accession_number=accession,
        cik=cik,
        form="4",
        source_url="https://www.sec.gov/example.txt",
        in_scope=True,
    ).logical_source_key


def _artifact(
    cik: int,
    accession: str,
    *,
    evidence: str | None = "bronze:abc",
    decision_id: str | None = "dec-1",
) -> CaptureArtifact:
    return CaptureArtifact(
        cik=cik,
        logical_source_key=_key(cik, accession),
        verified_evidence_reference=evidence,
        decision_id=decision_id,
    )


def _snapshot(path: str, cause: str, artifacts: list[CaptureArtifact]) -> CaptureSnapshot:
    return CaptureSnapshot(path=path, cause_reference=cause, artifacts=tuple(artifacts))


def test_stage_one_scope_is_exactly_apple() -> None:
    scope = resolve_parity_scope(business_date="2026-08-26")
    assert scope.cik_list == (APPLE_CIK,)
    assert scope.limit == 1
    assert APPLE_CIK == 320193


def test_stage_two_limit_100_drops_unrelated_ciks() -> None:
    universe = tuple(range(1, 121))
    scope = resolve_parity_scope(
        business_date="2026-08-26",
        cik_list=universe,
        limit=100,
    )
    assert len(scope.cik_list) == 100
    assert scope.cik_list == universe[:100]
    assert 101 not in scope.cik_list
    assert 120 not in scope.cik_list


def test_stage_two_compare_fails_when_gated_processed_cik_101() -> None:
    universe = tuple(range(1, 101))
    artifacts = [_artifact(cik, f"0001140361-26-{cik:06d}") for cik in universe]
    extra = _artifact(101, "0001140361-26-000101")
    scope = resolve_parity_scope(
        business_date="2026-08-26", cik_list=universe, limit=100
    )
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-100", artifacts),
        gated=_snapshot("gated", "gated-101", artifacts + [extra]),
        scope=scope,
    )
    assert verdict.passed is False
    assert 101 in verdict.out_of_scope_ciks


def test_equal_sets_pass_decision_two() -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-capture:2026-08-26:apple", [apple]),
        gated=_snapshot("gated", "discovery-manifest:aaa:registry:filing_artifact-v1", [apple]),
        scope=scope,
    )
    assert verdict.passed is True
    assert verdict.reasons == ()
    assert verdict.logical_source_keys.gated_covers_legacy is True


def test_gated_superset_passes() -> None:
    shared = _artifact(APPLE_CIK, "0001140361-26-000001")
    extra = _artifact(APPLE_CIK, "0001140361-26-000099", decision_id="dec-extra")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-a", [shared]),
        gated=_snapshot("gated", "gated-a", [shared, extra]),
        scope=scope,
    )
    assert verdict.passed is True
    assert extra.logical_source_key in verdict.logical_source_keys.only_gated


def test_silent_gap_fails_when_legacy_has_a_key_gated_lacks() -> None:
    legacy_only = _artifact(APPLE_CIK, "0001140361-26-000001")
    gated_other = _artifact(APPLE_CIK, "0001140361-26-000002")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-a", [legacy_only]),
        gated=_snapshot("gated", "gated-a", [gated_other]),
        scope=scope,
    )
    assert verdict.passed is False
    assert legacy_only.logical_source_key in verdict.logical_source_keys.only_legacy
    assert any("silent gap" in reason for reason in verdict.reasons)


def test_out_of_scope_cik_fails_even_when_keys_otherwise_match() -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    other = _artifact(999999, "0001140361-26-000002")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-a", [apple]),
        gated=_snapshot("gated", "gated-a", [apple, other]),
        scope=scope,
    )
    assert verdict.passed is False
    assert 999999 in verdict.out_of_scope_ciks
    assert any("out of scope" in reason for reason in verdict.reasons)


def test_shared_cause_reference_fails_closed() -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "same-cause", [apple]),
        gated=_snapshot("gated", "same-cause", [apple]),
        scope=scope,
    )
    assert verdict.passed is False
    assert any("cause_reference" in reason for reason in verdict.reasons)


def test_missing_cause_reference_fails_closed() -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "", [apple]),
        gated=_snapshot("gated", "gated-a", [apple]),
        scope=scope,
    )
    assert verdict.passed is False
    assert any("cause_reference" in reason for reason in verdict.reasons)


def test_evidence_gap_fails_even_when_logical_keys_match() -> None:
    keyed = _key(APPLE_CIK, "0001140361-26-000001")
    legacy = CaptureArtifact(
        cik=APPLE_CIK,
        logical_source_key=keyed,
        verified_evidence_reference="bronze:legacy-hash",
        decision_id=None,
    )
    gated = CaptureArtifact(
        cik=APPLE_CIK,
        logical_source_key=keyed,
        verified_evidence_reference=None,
        decision_id="dec-1",
    )
    scope = resolve_parity_scope(business_date="2026-08-26")
    verdict = compare_capture_snapshots(
        legacy=_snapshot("legacy", "legacy-a", [legacy]),
        gated=_snapshot("gated", "gated-a", [gated]),
        scope=scope,
    )
    assert verdict.passed is False
    assert keyed in verdict.verified_evidence.only_legacy
    assert any("Verified Source Evidence" in reason for reason in verdict.reasons)


def test_artifact_from_silver_raw_object_matches_discovery_logical_source_key() -> None:
    artifact = artifact_from_silver_raw_object(
        {
            "cik": APPLE_CIK,
            "accession_number": "0001140361-26-000001",
            "sha256": "abc",
        }
    )
    assert artifact.logical_source_key == _key(APPLE_CIK, "0001140361-26-000001")
    assert artifact.verified_evidence_reference == "abc"
    assert artifact.decision_id is None


def test_artifact_from_source_fetch_decision_uses_ledger_fields() -> None:
    key = _key(APPLE_CIK, "0001140361-26-000001")
    artifact = artifact_from_source_fetch_decision(
        {
            "logical_source_key": key,
            "verified_evidence_reference": "bronze:abc",
            "decision_id": "dec-1",
        }
    )
    assert artifact.cik == APPLE_CIK
    assert artifact.logical_source_key == key
    assert artifact.verified_evidence_reference == "bronze:abc"
    assert artifact.decision_id == "dec-1"


def test_filter_discovery_rows_keeps_only_scoped_ciks() -> None:
    rows = [
        {"cik": 320193, "accession_number": "0001140361-26-000001"},
        {"cik": 999999, "accession_number": "0001140361-26-000002"},
        {"cik": "789019", "accession_number": "0001140361-26-000003"},
    ]
    filtered = filter_discovery_rows_by_cik(rows, (320193, 789019))
    assert [int(row["cik"]) for row in filtered] == [320193, 789019]


def test_unfiltered_discovery_records_catchup_scoped_does_not() -> None:
    assert should_record_family_catchup(None) is True
    assert should_record_family_catchup(()) is True
    assert should_record_family_catchup((APPLE_CIK,)) is False


def test_json_snapshot_round_trip(tmp_path: Path) -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    original = _snapshot("gated", "discovery-manifest:abc", [apple])
    path = tmp_path / "gated.json"
    write_capture_snapshot(path, original)
    loaded = load_capture_snapshot(path)
    assert loaded == original


def test_cli_handler_exits_zero_on_pass_and_one_on_silent_gap(tmp_path: Path) -> None:
    from argparse import Namespace

    from edgar_warehouse.cli import _handle_compare_filing_artifact_capture

    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    missing = _artifact(APPLE_CIK, "0001140361-26-000002")
    legacy_path = tmp_path / "legacy.json"
    gated_ok = tmp_path / "gated-ok.json"
    gated_gap = tmp_path / "gated-gap.json"
    write_capture_snapshot(
        legacy_path, _snapshot("legacy", "legacy-capture:2026-08-26:apple", [apple])
    )
    write_capture_snapshot(
        gated_ok, _snapshot("gated", "discovery-manifest:abc", [apple])
    )
    write_capture_snapshot(
        gated_gap, _snapshot("gated", "discovery-manifest:def", [missing])
    )

    pass_code = _handle_compare_filing_artifact_capture(
        Namespace(
            business_date="2026-08-26",
            legacy_snapshot=str(legacy_path),
            gated_snapshot=str(gated_ok),
            cik_list=None,
            limit=1,
        )
    )
    fail_code = _handle_compare_filing_artifact_capture(
        Namespace(
            business_date="2026-08-26",
            legacy_snapshot=str(legacy_path),
            gated_snapshot=str(gated_gap),
            cik_list=None,
            limit=1,
        )
    )
    assert pass_code == 0
    assert fail_code == 1


def test_evaluate_files_stage_one_pass(tmp_path: Path) -> None:
    apple = _artifact(APPLE_CIK, "0001140361-26-000001")
    legacy_path = tmp_path / "legacy.json"
    gated_path = tmp_path / "gated.json"
    write_capture_snapshot(
        legacy_path, _snapshot("legacy", "legacy-capture:2026-08-26:apple", [apple])
    )
    write_capture_snapshot(
        gated_path,
        _snapshot("gated", "discovery-manifest:abc:registry:filing_artifact-v1", [apple]),
    )
    verdict = evaluate_capture_parity_files(
        legacy_path=legacy_path,
        gated_path=gated_path,
        business_date="2026-08-26",
    )
    assert verdict.passed is True
    assert verdict.scope.cik_list == (APPLE_CIK,)
