"""Ticket 09 (release-readiness map): Release Evidence Automation.

Covers `edgar_warehouse.application.release_evidence`, the pure module that
deterministically builds and maintains a Candidate Evidence Set manifest
(`release-evidence.json`) per ticket 01's Answer, while refusing to ever
write a Gate Attestation or Release Seal disposition itself.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

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
    watermark_digest_for,
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
        assert candidate_id_for(COMMIT_SHA, "20260729") == "rc-20260729-e0fa0eaafb09"

    def test_candidate_id_uses_first_12_hex_chars_only(self):
        cid = candidate_id_for(COMMIT_SHA, "20260729")
        assert cid.endswith(COMMIT_SHA[:12])
        assert len(cid.split("-")[-1]) == 12

    @pytest.mark.parametrize(
        "commit_sha",
        ["abc123", "a/../../../outside", "g" * 40],
    )
    def test_rejects_noncanonical_full_commit_sha(self, commit_sha):
        with pytest.raises(ValueError):
            candidate_id_for(commit_sha, "20260729")


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
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

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
            b"snowflake://release_user:password@org-account/database",
            b"account_locator: XCPCLKF-KB19989",
            b"account_locator: xcpclkf-kb19989",
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

    @pytest.mark.parametrize("missing_field", ["gates", "candidate_id"])
    def test_malformed_existing_manifest_is_rejected_cleanly(self, missing_field):
        manifest = _base_manifest()
        del manifest[missing_field]
        with pytest.raises(GateRejectedError):
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

    def test_nul_in_new_gate_evidence_path_is_rejected_cleanly(self):
        manifest = _base_manifest()
        with pytest.raises(LineageError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/a.json\x00"
                ),
                evidence_bytes=b"{}",
                media_type="application/json",
                capture_tool="x",
                capture_tool_version="1.0.0",
                captured_at="2026-07-29T12:05:00+00:00",
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gate_name", ""),
            ("media_type", None),
            ("capture_tool", []),
            ("capture_tool_version", {}),
        ],
    )
    def test_invalid_new_gate_metadata_is_rejected_cleanly(self, field, value):
        kwargs = {
            "gate_name": "batchsilver_integrity",
            "status": "pass",
            "evidence_relpath": (
                "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                "evidence/a.json"
            ),
            "evidence_bytes": b"{}",
            "media_type": "application/json",
            "capture_tool": "x",
            "capture_tool_version": "1.0.0",
            "captured_at": "2026-07-29T12:05:00+00:00",
        }
        kwargs[field] = value
        with pytest.raises(GateRejectedError):
            add_gate(_base_manifest(), **kwargs)

    def test_live_evidence_window_is_fixed_at_24h_not_operator_configurable(self):
        """Ticket 01: "remain within the 24-hour Live-Evidence Window" is a
        fixed invariant, not a per-call knob — add_gate must take no
        expiry-hours argument at all."""
        import inspect

        assert "expiry_hours" not in inspect.signature(add_gate).parameters

    def test_rejects_naive_non_utc_capture_timestamp(self):
        manifest = _base_manifest()
        with pytest.raises(GateRejectedError):
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
                captured_at="2026-07-29T12:05:00",
            )

    def test_rejects_capture_before_candidate_identity_freeze(self):
        with pytest.raises(GateRejectedError):
            add_gate(
                _base_manifest(),
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
                captured_at="2026-07-29T11:59:59+00:00",
            )

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

    def test_rejects_traversal_hidden_beneath_candidate_evidence_prefix(self):
        manifest = _base_manifest()
        with pytest.raises(LineageError):
            add_gate(
                manifest,
                gate_name="batchsilver_integrity",
                status="pass",
                evidence_relpath=(
                    "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
                    "evidence/../../outside.json"
                ),
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
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is True
        assert report.findings == []

    def test_flags_missing_evidence_file(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).unlink()
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_file_missing" for f in report.findings)

    def test_flags_digest_drift_when_file_mutated_after_recording(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).write_bytes(b'{"status": "fail", "tampered": true}')
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_digest_mismatch" for f in report.findings)

    def test_flags_stale_evidence_past_24h_window(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        as_of = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "evidence_stale" for f in report.findings)

    def test_flags_secret_reintroduced_after_gate_was_added(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence/a.json"
        ).write_bytes(b'{"arn": "arn:aws:iam::690839588395:role/x"}')
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "secret_found" for f in report.findings)

    def test_rejects_traversal_during_validation_even_when_target_exists(
        self, tmp_path
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        outside = (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/outside.json"
        )
        outside.write_bytes(b'{"status": "pass"}')
        manifest["gates"][0]["evidence_path"] = (
            "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/"
            "evidence/../outside.json"
        )
        manifest["gates"][0]["evidence_sha256"] = sha256_hex(outside.read_bytes())
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(
            f.code == "gate_evidence_path_lineage_violation" for f in report.findings
        )

    def test_rejects_extended_or_future_evidence_window(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        gate = manifest["gates"][0]
        gate["captured_at"] = "2099-01-01T00:00:00+00:00"
        gate["expires_at"] = "2099-01-03T00:00:00+00:00"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert {f.code for f in report.findings} >= {
            "evidence_from_future",
            "invalid_evidence_window",
        }

    def test_flags_evidence_captured_before_candidate_identity_freeze(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0]["captured_at"] = "2026-07-29T11:59:59+00:00"
        manifest["gates"][0]["expires_at"] = "2026-07-30T11:59:59+00:00"
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "evidence_before_identity_freeze" for f in report.findings)

    def test_naive_gate_timestamps_return_findings_instead_of_crashing(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0]["captured_at"] = "2026-07-29T12:05:00"
        manifest["gates"][0]["expires_at"] = "2026-07-30T12:05:00"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "invalid_timestamp" for f in report.findings)

    def test_flags_missing_required_top_level_field(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["source_branch"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "missing_field" for f in report.findings)

    @pytest.mark.parametrize("source_branch", [None, "", [], {}])
    def test_flags_invalid_source_branch(self, tmp_path, source_branch):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["source_branch"] = source_branch
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_source_branch" for f in report.findings)

    @pytest.mark.parametrize("disposition", [[], {}, 7])
    def test_malformed_disposition_returns_finding_instead_of_crashing(
        self, tmp_path, disposition
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = disposition
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_disposition" for f in report.findings)

    @pytest.mark.parametrize("status", [[], {}, 7, ""])
    def test_malformed_gate_status_returns_finding_instead_of_crashing(
        self, tmp_path, status
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0]["status"] = status
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_gate_status" for f in report.findings)

    @pytest.mark.parametrize("evidence_path", [123, {}, [], "\x00"])
    def test_non_path_gate_evidence_returns_finding_instead_of_passing_or_crashing(
        self, tmp_path, evidence_path
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0]["evidence_path"] = evidence_path
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_evidence_path" for f in report.findings)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gate_name", ""),
            ("media_type", None),
            ("capture_tool", []),
            ("capture_tool_version", {}),
        ],
    )
    def test_invalid_gate_metadata_fails_closed(self, tmp_path, field, value):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0][field] = value
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_gate_metadata" for f in report.findings)

    def test_duplicate_gate_names_fail_closed(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"].append(dict(manifest["gates"][0]))
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "duplicate_gate_name" for f in report.findings)

    @pytest.mark.parametrize(
        ("field", "malformed_value"),
        [
            ("release_data_watermark", None),
            ("release_data_watermark", []),
            ("gates", ["not-an-object"]),
            ("attestations", "not-an-array"),
            ("addendum_references", {}),
        ],
    )
    def test_malformed_container_types_return_structured_findings(
        self, tmp_path, field, malformed_value
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest[field] = malformed_value
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "invalid_type" for f in report.findings)

    @pytest.mark.parametrize("nested_field", ["snowflake_export", "hosted_graph"])
    def test_malformed_watermark_nested_objects_fail_closed(
        self, tmp_path, nested_field
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["release_data_watermark"][nested_field] = []
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "invalid_type" for f in report.findings)

    @pytest.mark.parametrize(
        ("field", "tampered_value", "finding_code"),
        [
            ("schema_version", 999, "invalid_schema_version"),
            ("lifecycle_status", "editable", "invalid_lifecycle_status"),
        ],
    )
    def test_flags_tampered_frozen_identity_fields(
        self, tmp_path, field, tampered_value, finding_code
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest[field] = tampered_value
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert any(f.code == finding_code for f in report.findings)

    def test_candidate_date_must_match_identity_freeze_date(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["candidate_id"] = f"rc-20991231-{COMMIT_SHA[:12]}"
        manifest["gates"][0]["evidence_path"] = (
            f"docs/release-readiness/releases/{manifest['candidate_id']}/evidence/a.json"
        )
        new_evidence_dir = (
            tmp_path
            / "docs/release-readiness/releases"
            / manifest["candidate_id"]
            / "evidence"
        )
        new_evidence_dir.mkdir(parents=True)
        (new_evidence_dir / "a.json").write_bytes(b'{"status": "pass"}')
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "candidate_id_date_mismatch" for f in report.findings)

    @pytest.mark.parametrize(
        ("field", "tampered_value", "finding_code"),
        [
            ("status", None, "invalid_gate_status"),
            ("evidence_sha256", None, "invalid_evidence_digest"),
            ("sanitization", None, "invalid_sanitization"),
        ],
    )
    def test_flags_tampered_gate_fields(
        self, tmp_path, field, tampered_value, finding_code
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["gates"][0][field] = tampered_value
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert any(f.code == finding_code for f in report.findings)

    def test_flags_secret_embedded_in_manifest_metadata(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["release_data_watermark"]["snowflake_export"]["run_id"] = (
            "snowflake://release_user:password@org-account/database"
        )
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "manifest_secret_found" for f in report.findings)

    def test_flags_incomplete_gate_missing_field(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["gates"][0]["evidence_sha256"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_gate" for f in report.findings)

    def test_flags_invalid_disposition_value(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = "yolo"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "invalid_disposition" for f in report.findings)

    @pytest.mark.parametrize("valid_disposition", ["go", "no_go", "superseded", None])
    def test_accepts_every_valid_disposition_value(self, tmp_path, valid_disposition):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = valid_disposition
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert not any(f.code == "invalid_disposition" for f in report.findings)

    def test_flags_incomplete_attestation_record(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["attestations"] = [{"role": "aws_operator"}]  # missing other fields
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
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
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert not any(f.code == "incomplete_attestation" for f in report.findings)

    def test_rejects_attestation_not_bound_to_candidate_and_watermark(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["attestations"] = [
            {
                "role": "aws_operator",
                "approver_handle": "jdoe",
                "attested_at": "2026-07-29T13:00:00+00:00",
                "candidate_id": "rc-20260729-000000000000",
                "watermark_digest": "sha256:" + "d" * 64,
                "evidence_digest": "sha256:" + "e" * 64,
            }
        ]
        as_of = datetime(2026, 7, 29, 13, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert {f.code for f in report.findings} >= {
            "attestation_candidate_mismatch",
            "attestation_watermark_mismatch",
            "attestation_evidence_mismatch",
        }

    def test_flags_attestation_before_candidate_identity_freeze(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        gate_digest = "sha256:" + manifest["gates"][0]["evidence_sha256"]
        manifest["attestations"] = [
            {
                "role": "aws_operator",
                "approver_handle": "jdoe",
                "attested_at": "2026-07-29T11:59:59+00:00",
                "candidate_id": manifest["candidate_id"],
                "watermark_digest": watermark_digest_for(
                    manifest["release_data_watermark"]
                ),
                "evidence_digest": gate_digest,
            }
        ]
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(
            f.code == "attestation_before_identity_freeze" for f in report.findings
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("release_owner_attestation", []),
            ("release_seal", 7),
            ("release_seal", ""),
        ],
    )
    def test_reserved_final_state_fields_require_null_or_valid_shape(
        self, tmp_path, field, value
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest[field] = value
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_final_state_field" for f in report.findings)

    def test_final_no_go_requires_release_seal(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        gate_digest = "sha256:" + manifest["gates"][0]["evidence_sha256"]
        manifest["disposition"] = "no_go"
        manifest["release_owner_attestation"] = {
            "role": "release_owner",
            "approver_handle": "owner",
            "attested_at": "2026-07-29T12:15:00+00:00",
            "candidate_id": manifest["candidate_id"],
            "watermark_digest": watermark_digest_for(
                manifest["release_data_watermark"]
            ),
            "evidence_digest": gate_digest,
        }
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "incomplete_final_disposition" for f in report.findings)

    def test_fabricated_go_without_human_approval_fails_closed(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = "go"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_final_disposition" for f in report.findings)

    def test_go_with_unhashable_attestation_digest_returns_structured_findings(
        self, tmp_path
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["disposition"] = "go"
        manifest["attestations"] = [
            {
                "role": "aws_operator",
                "approver_handle": "jdoe",
                "attested_at": "2026-07-29T12:10:00+00:00",
                "candidate_id": manifest["candidate_id"],
                "watermark_digest": watermark_digest_for(
                    manifest["release_data_watermark"]
                ),
                "evidence_digest": [],
            }
        ]
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_attestation_digest" for f in report.findings)

    def test_go_remains_fail_closed_until_go_packet_and_seal_verification_exist(
        self, tmp_path
    ):
        manifest = self._manifest_with_one_gate(tmp_path)
        gate_digest = "sha256:" + manifest["gates"][0]["evidence_sha256"]
        watermark_digest = watermark_digest_for(manifest["release_data_watermark"])
        manifest["attestations"] = [
            {
                "role": "aws_operator",
                "approver_handle": "jdoe",
                "attested_at": "2026-07-29T13:00:00+00:00",
                "candidate_id": manifest["candidate_id"],
                "watermark_digest": watermark_digest,
                "evidence_digest": gate_digest,
            }
        ]
        manifest["release_owner_attestation"] = {
            "role": "release_owner",
            "approver_handle": "owner",
            "attested_at": "2026-07-29T13:15:00+00:00",
            "candidate_id": manifest["candidate_id"],
            "watermark_digest": watermark_digest,
            "evidence_digest": gate_digest,
        }
        manifest["release_seal"] = "release-evidence/rc-20260729-e0fa0eaafb09"
        manifest["disposition"] = "go"
        as_of = datetime(2026, 7, 29, 13, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "go_validation_not_implemented" for f in report.findings)

    def test_flags_watermark_missing_required_subfield(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["release_data_watermark"]["mdm_publication_watermark"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_watermark" for f in report.findings)

    def test_flags_watermark_nested_snowflake_export_missing_subfield(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        del manifest["release_data_watermark"]["snowflake_export"]["run_id"]
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "incomplete_watermark" for f in report.findings)

    @pytest.mark.parametrize(
        ("path", "value"),
        [
            (("bronze_input_manifest_digest",), []),
            (("silver_shard_manifest_digest",), "not-a-digest"),
            (("max_eligible_business_date",), {}),
            (("max_eligible_business_date",), "2026-99-99"),
            (("full_chain_execution_id",), ""),
            (("full_chain_execution_scope",), None),
            (("mdm_publication_watermark",), []),
            (("snowflake_export", "run_id"), ""),
            (("snowflake_export", "business_date"), "tomorrow"),
            (("snowflake_export", "manifest_digest"), {}),
            (("hosted_graph", "generation_id"), ""),
            (("hosted_graph", "publication_id"), []),
        ],
    )
    def test_malformed_watermark_scalars_fail_closed(self, tmp_path, path, value):
        manifest = self._manifest_with_one_gate(tmp_path)
        target = manifest["release_data_watermark"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(f.code == "invalid_watermark_field" for f in report.findings)

    def test_symlinked_candidate_evidence_root_fails_closed(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        evidence_root = (
            tmp_path
            / "docs/release-readiness/releases/rc-20260729-e0fa0eaafb09/evidence"
        )
        (evidence_root / "a.json").unlink()
        evidence_root.rmdir()
        outside = tmp_path / "outside-evidence"
        outside.mkdir()
        (outside / "a.json").write_bytes(b'{"status": "pass"}')
        evidence_root.symlink_to(outside, target_is_directory=True)
        report = validate_manifest(
            manifest,
            repo_root=tmp_path,
            as_of=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )
        assert report.ok is False
        assert any(
            f.code == "gate_evidence_path_lineage_violation" for f in report.findings
        )

    def test_flags_candidate_id_directory_mismatch(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        manifest["candidate_id"] = "rc-20260729-000000000000"
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        report = validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        assert report.ok is False
        assert any(f.code == "candidate_id_commit_mismatch" for f in report.findings)

    def test_never_writes_attestation_or_disposition(self, tmp_path):
        manifest = self._manifest_with_one_gate(tmp_path)
        as_of = datetime(2026, 7, 29, 12, 30, tzinfo=UTC)
        before = json.dumps(manifest, sort_keys=True)
        validate_manifest(manifest, repo_root=tmp_path, as_of=as_of)
        after = json.dumps(manifest, sort_keys=True)
        assert before == after  # validate never mutates its input
        assert manifest["attestations"] == []
        assert manifest["disposition"] is None


class TestValidationFindingShape:
    def test_finding_is_serializable(self):
        finding = ValidationFinding(code="missing_field", message="x", gate_name=None)
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
