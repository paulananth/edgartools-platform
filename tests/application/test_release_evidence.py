"""Ticket 09 (release-readiness map): Release Evidence Automation.

Covers `edgar_warehouse.application.release_evidence`, the pure module that
deterministically builds and maintains a Candidate Evidence Set manifest
(`release-evidence.json`) per ticket 01's Answer, while refusing to ever
write a Gate Attestation or Release Seal disposition itself.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from edgar_warehouse.application.release_evidence import (
    GateRejectedError,
    IdentityFrozenError,
    LineageError,
    SanitizationError,
    ValidationFinding,
    add_gate,
    build_manifest,
    candidate_id_for,
    scan_for_secrets,
    sha256_hex,
    validate_manifest,
)

COMMIT_SHA = "e0fa0eaafb095c18ad75659cadb4066b5426d327"
FREEZE_TS = "2026-07-29T12:00:00+00:00"
WATERMARK = {
    "bronze_input_manifest_digest": "sha256:" + "a" * 64,
    "max_eligible_business_date": "2026-07-28",
    "full_chain_execution_id": "full-chain-launch-rc-20260729-e0fa0eaafb09",
    "full_chain_execution_scope": "all",
    "silver_shard_manifest_digest": "sha256:" + "b" * 64,
    "snowflake_export": {
        "run_id": "run-123",
        "business_date": "2026-07-28",
        "manifest_digest": "sha256:" + "c" * 64,
    },
    "mdm_publication_watermark": "mdm-pub-20260728T060000Z",
    "hosted_graph": {"generation_id": "gen-14", "publication_id": "pub-9"},
}


def _base_manifest() -> dict:
    return build_manifest(
        commit_sha=COMMIT_SHA,
        source_branch="main",
        warehouse_image_digest="sha256:" + "1" * 64,
        mdm_image_digest="sha256:" + "2" * 64,
        release_data_watermark=WATERMARK,
        identity_freeze_timestamp=FREEZE_TS,
    )


class TestCandidateId:
    def test_candidate_id_format(self):
        assert (
            candidate_id_for(COMMIT_SHA, "20260729")
            == "rc-20260729-e0fa0eaafb09"
        )

    def test_candidate_id_uses_first_12_hex_chars_only(self):
        cid = candidate_id_for(COMMIT_SHA, "20260729")
        assert cid.endswith(COMMIT_SHA[:12])
        assert len(cid.split("-")[-1]) == 12


class TestBuildManifestDeterminism:
    def test_identical_inputs_produce_byte_identical_output(self):
        first = build_manifest(
            commit_sha=COMMIT_SHA,
            source_branch="main",
            warehouse_image_digest="sha256:" + "1" * 64,
            mdm_image_digest="sha256:" + "2" * 64,
            release_data_watermark=WATERMARK,
            identity_freeze_timestamp=FREEZE_TS,
        )
        second = build_manifest(
            commit_sha=COMMIT_SHA,
            source_branch="main",
            warehouse_image_digest="sha256:" + "1" * 64,
            mdm_image_digest="sha256:" + "2" * 64,
            release_data_watermark=WATERMARK,
            identity_freeze_timestamp=FREEZE_TS,
        )
        assert json.dumps(first, sort_keys=True) == json.dumps(
            second, sort_keys=True
        )

    def test_schema_version_and_candidate_id_present(self):
        manifest = _base_manifest()
        assert manifest["schema_version"] == 1
        assert manifest["candidate_id"] == "rc-20260729-e0fa0eaafb09"
        assert manifest["commit_sha"] == COMMIT_SHA
        assert manifest["source_branch"] == "main"
        assert manifest["identity_freeze_timestamp"] == FREEZE_TS
        assert manifest["lifecycle_status"] == "frozen"

    def test_image_digests_carry_no_registry_or_account(self):
        manifest = _base_manifest()
        assert manifest["warehouse_image_digest"].startswith("sha256:")
        assert "dkr.ecr" not in manifest["warehouse_image_digest"]
        assert "690839588395" not in manifest["warehouse_image_digest"]

    def test_starts_with_no_gates_no_attestations_null_disposition(self):
        manifest = _base_manifest()
        assert manifest["gates"] == []
        assert manifest["attestations"] == []
        assert manifest["disposition"] is None
        assert manifest["release_seal"] is None
        assert manifest["release_owner_attestation"] is None
        assert manifest["addendum_references"] == []

    def test_rejects_malformed_image_digest(self):
        with pytest.raises(ValueError):
            build_manifest(
                commit_sha=COMMIT_SHA,
                source_branch="main",
                warehouse_image_digest="690839588395.dkr.ecr.us-east-1.amazonaws.com/x@sha256:"
                + "1" * 64,
                mdm_image_digest="sha256:" + "2" * 64,
                release_data_watermark=WATERMARK,
                identity_freeze_timestamp=FREEZE_TS,
            )


class TestSanitizer:
    @pytest.mark.parametrize(
        "secret",
        [
            b"account id 690839588395 is active",
            b"arn:aws:iam::690839588395:role/EdgarToolsProdLoader",
            b"690839588395.dkr.ecr.us-east-1.amazonaws.com/edgartools-prod-warehouse",
            b"postgresql://mdm_admin:hunter2@edgartools-prod-mdm.example/mdm",
            b"account_locator: XCPCLKF-KB19989",
        ],
    )
    def test_flags_each_secret_class(self, secret: bytes):
        findings = scan_for_secrets(secret)
        assert findings, f"expected a finding for {secret!r}"

    def test_clean_content_has_no_findings(self):
        findings = scan_for_secrets(
            b'{"status": "pass", "rows_written": 24195, "note": "no secrets here"}'
        )
        assert findings == []


class TestAddGate:
    def test_appends_sanitized_gate_record(self):
        manifest = _base_manifest()
        evidence_bytes = b'{"status": "pass"}'
        updated = add_gate(
            manifest,
            gate_name="batchsilver_integrity",
            status="pass",
            evidence_relpath=(
                "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                "evidence/maxconcurrency4-data-integrity.json"
            ),
            evidence_bytes=evidence_bytes,
            media_type="application/json",
            capture_tool="maxconcurrency4_proof.py",
            capture_tool_version="1.0.0",
            captured_at="2026-07-29T12:05:00+00:00",
        )
        assert len(updated["gates"]) == 1
        gate = updated["gates"][0]
        assert gate["gate_name"] == "batchsilver_integrity"
        assert gate["status"] == "pass"
        assert gate["evidence_sha256"] == sha256_hex(evidence_bytes)
        assert gate["captured_at"] == "2026-07-29T12:05:00+00:00"
        assert gate["expires_at"] == "2026-07-30T12:05:00+00:00"
        assert gate["sanitization"] == {"scanned": True, "findings": []}
        # original manifest is untouched (pure, no in-place mutation)
        assert manifest["gates"] == []

    def test_live_evidence_window_is_fixed_at_24h_not_operator_configurable(self):
        """Ticket 01: "remain within the 24-hour Live-Evidence Window" is a
        fixed invariant, not a per-call knob — add_gate must take no
        expiry-hours argument at all."""
        import inspect

        assert "expiry_hours" not in inspect.signature(add_gate).parameters

    def test_rejects_gate_whose_evidence_contains_a_secret(self):
        manifest = _base_manifest()
        with pytest.raises(SanitizationError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/leaky.json"
                ),
                evidence_bytes=b'{"arn": "arn:aws:iam::690839588395:role/x"}',
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:05:00+00:00",
            )

    def test_rejects_evidence_path_outside_candidates_own_evidence_dir(self):
        manifest = _base_manifest()
        with pytest.raises(LineageError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath="docs/release-readiness/rollback-rehearsal.json",
                evidence_bytes=b"{}",
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:05:00+00:00",
            )

    def test_rejects_duplicate_gate_name(self):
        manifest = _base_manifest()
        manifest = add_gate(
            manifest,
            gate_name="batchsilver_integrity",
            status="pass",
            evidence_relpath=(
                "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                "evidence/a.json"
            ),
            evidence_bytes=b"{}",
            media_type="application/json",
            capture_tool="x",
            capture_tool_version="1.0.0",
            captured_at="2026-07-29T12:05:00+00:00",
        )
        with pytest.raises(GateRejectedError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/b.json"
                ),
                evidence_bytes=b"{}",
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:10:00+00:00",
            )

    def test_rejects_invalid_status(self):
        manifest = _base_manifest()
        with pytest.raises(GateRejectedError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="probably_fine",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/a.json"
                ),
                evidence_bytes=b"{}",
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:05:00+00:00",
            )


class TestValidateManifest:
    def _manifest_with_one_gate(self, tmp_path):
        manifest = _base_manifest()
        evidence_dir = (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence"
        )
        evidence_dir.mkdir(parents=True)
        evidence_bytes = b'{"status": "pass"}'
        (evidence_dir / "a.json").write_bytes(evidence_bytes)
        manifest = add_gate(
            manifest,
            gate_name="batchsilver_integrity",
            status="pass",
            evidence_relpath=(
                "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                "evidence/a.json"
            ),
            evidence_bytes=evidence_bytes,
            media_type="application/json",
            capture_tool="x",
            capture_tool_version="1.0.0",
            captured_at="2026-07-29T12:05:00+00:00",
        )
        return manifest

    def test_clean_manifest_validates_ok(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is True
        assert report.findings == []

    def test_flags_missing_evidence_file(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).unlink()
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_file_missing" for f in report.findings)

    def test_flags_digest_drift_when_file_mutated_after_recording(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).write_bytes(b'{"status": "fail", "tampered": true}')
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_digest_mismatch" for f in report.findings)

    def test_flags_stale_evidence_past_24h_window(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        as_of = datetime(2026, 7, 31, 0, 0, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_stale" for f in report.findings)

    def test_flags_secret_reintroduced_after_gate_was_added(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).write_bytes(b'{"arn": "arn:aws:iam::690839588395:role/x"}')
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "secret_found" for f in report.findings)

    def test_flags_missing_required_top_level_field(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["source_branch"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "missing_field" for f in report.findings)

    def test_flags_incomplete_gate_missing_field(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["gates"][0]["evidence_sha256"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_gate" for f in report.findings)

    def test_flags_invalid_disposition_value(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = "yolo"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "invalid_disposition" for f in report.findings)

    @pytest.mark.parametrize("valid_disposition", ["go", "no_go", "superseded", None])
    def test_accepts_every_valid_disposition_value(self, tmp_path, valid_disposition):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = valid_disposition
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert not any(f.code == "invalid_disposition" for f in report.findings)

    def test_flags_incomplete_attestation_record(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["attestations"] = [{"role": "aws_operator"}]  # missing other fields
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_attestation" for f in report.findings)

    def test_accepts_complete_attestation_record(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["attestations"] = [
            {
                "role": "aws_operator",
                "approver_handle": "jdoe",
                "attested_at": "2026-07-29T13:00:00+00:00",
                "candidate_id": manifest["candidate_id"],
                "watermark_digest": "sha256:" + "d" * 64,
                "evidence_digest": "sha256:" + "e" * 64,
            }
        ]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert not any(f.code == "incomplete_attestation" for f in report.findings)

    def test_flags_watermark_missing_required_subfield(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["release_data_watermark"]["mdm_publication_watermark"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_watermark" for f in report.findings)

    def test_flags_watermark_nested_snowflake_export_missing_subfield(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["release_data_watermark"]["snowflake_export"]["run_id"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_watermark" for f in report.findings)

    def test_flags_candidate_id_directory_mismatch(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["candidate_id"] = "rc-20260729-000000000000"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "candidate_id_commit_mismatch" for f in report.findings)

    def test_never_writes_attestation_or_disposition(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=timezone.utc)
        before = json.dumps(manifest, sort_keys=True)
        validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        after = json.dumps(manifest, sort_keys=True)
        assert before == after  # validate never mutates its input
        assert manifest["attestations"] == []
        assert manifest["disposition"] is None


class TestValidationFindingShape:
    def test_finding_is_serializable(self):
        finding = ValidationFinding(
            code="missing_field", message="x", gate_name=None
        )
        assert finding.code == "missing_field"


class TestIdentityFreezeGuard:
    def test_add_gate_after_manual_disposition_is_rejected(self):
        manifest = _base_manifest()
        manifest = dict(manifest)
        manifest["disposition"] = "go"
        with pytest.raises(IdentityFrozenError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/a.json"
                ),
                evidence_bytes=b"{}",
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:05:00+00:00",
            )
