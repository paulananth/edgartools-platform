"""Adversarial coverage for ticket 48's Direct-Evidence GO contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from edgar_warehouse.application.release_evidence import (
    _CONTRACT_GATES,
    GateRejectedError,
    add_gate,
    build_manifest,
    validate_manifest,
)

COMMIT = "e0fa0eaafb095c18ad75659cadb4066b5426d327"
FREEZE = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
WATERMARK = {
    "bronze_input_manifest_digest": "sha256:" + "a" * 64,
    "max_eligible_business_date": "2026-07-28",
    "full_chain_execution_id": "full-chain",
    "full_chain_execution_scope": "all",
    "silver_shard_manifest_digest": "sha256:" + "b" * 64,
    "snowflake_export": {"run_id": "run", "business_date": "2026-07-28", "manifest_digest": "sha256:" + "c" * 64},
    "mdm_publication_watermark": "mdm",
    "hosted_graph": {"generation_id": "generation", "publication_id": "publication"},
}


def _registry() -> dict:
    roles = {role for _, roles in _CONTRACT_GATES for role in roles} | {"release_owner"}
    return {
        "registry_version": "2026-07-29",
        "roles": {role: [{"handle": f"{role}-user", "key_fingerprint": f"FPR-{role}"}] for role in roles},
    }


def _manifest(tmp_path):
    registry = _registry()
    path = tmp_path / "docs/release-readiness/release-authority-registry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry), encoding="utf-8")
    return build_manifest(
        commit_sha=COMMIT,
        source_branch="main",
        warehouse_image_digest="sha256:" + "1" * 64,
        mdm_image_digest="sha256:" + "2" * 64,
        release_data_watermark=WATERMARK,
        identity_freeze_timestamp=FREEZE.isoformat(),
        authority_registry_path="docs/release-readiness/release-authority-registry.json",
        authority_registry=registry,
        rollback_mechanism_id="rollback-contract-v1",
    )


def _complete_attempt(tmp_path):
    manifest = _manifest(tmp_path)
    evidence_dir = tmp_path / "docs/release-readiness/releases" / manifest["candidate_id"] / "evidence"
    evidence_dir.mkdir(parents=True)
    for index, (name, roles) in enumerate(_CONTRACT_GATES):
        captured = FREEZE + timedelta(minutes=index + 1)
        evidence = f'{{"gate":"{name}"}}'.encode()
        evidence_path = evidence_dir / f"{index}.json"
        evidence_path.write_bytes(evidence)
        manifest = add_gate(
            manifest, gate_name=name, status="pass",
            evidence_relpath=evidence_path.relative_to(tmp_path).as_posix(),
            evidence_bytes=evidence, media_type="application/json", capture_tool="test",
            capture_tool_version="1", captured_at=captured.isoformat(),
            rollback_mechanism_id="rollback-contract-v1" if name == "rollback_readiness" else None,
        )
        for role in roles:
            manifest["attempts"][0]["attestations"].append({
                "attempt_id": "attempt-001", "gate_name": name, "role": role,
                "approver_handle": f"{role}-user", "key_fingerprint": f"FPR-{role}",
                "signature": "operator-signed", "candidate_id": manifest["candidate_id"],
                "watermark_digest": manifest["attempts"][0]["watermark_digest"],
                "evidence_digest": "sha256:" + manifest["attempts"][0]["gates"][-1]["evidence_sha256"],
                "attested_at": (captured + timedelta(seconds=1)).isoformat(),
            })
    return manifest


def test_complete_attempt_is_ready_for_owner(tmp_path):
    report = validate_manifest(_complete_attempt(tmp_path), repo_root=tmp_path, as_of=FREEZE + timedelta(minutes=20))
    assert report.ok
    assert report.readiness == "ready_for_owner"


def test_contract_rejects_unknown_or_reordered_gate(tmp_path):
    manifest = _manifest(tmp_path)
    kwargs = {
        "status": "pass",
        "evidence_relpath": f"docs/release-readiness/releases/{manifest['candidate_id']}/evidence/x.json",
        "evidence_bytes": b"{}",
        "media_type": "application/json",
        "capture_tool": "test",
        "capture_tool_version": "1",
        "captured_at": (FREEZE + timedelta(minutes=1)).isoformat(),
    }
    with pytest.raises(GateRejectedError, match="fixed gate inventory"):
        add_gate(manifest, gate_name="operator_override", **kwargs)
    with pytest.raises(GateRejectedError, match="gate order"):
        add_gate(manifest, gate_name="rollback_readiness", **kwargs)


def test_contract_gate_indexes_multiple_digest_bound_artifacts(tmp_path):
    manifest = _manifest(tmp_path)
    evidence_dir = tmp_path / "docs/release-readiness/releases" / manifest["candidate_id"] / "evidence"
    evidence_dir.mkdir(parents=True)
    primary, extra = evidence_dir / "primary.json", evidence_dir / "extra.json"
    primary.write_bytes(b'{"primary": true}')
    extra.write_bytes(b'{"extra": true}')
    manifest = add_gate(
        manifest, gate_name="candidate_identity_binding", status="pass",
        evidence_relpath=primary.relative_to(tmp_path).as_posix(), evidence_bytes=primary.read_bytes(),
        media_type="application/json", capture_tool="test", capture_tool_version="1",
        captured_at=(FREEZE + timedelta(minutes=1)).isoformat(),
        additional_evidence=((extra.relative_to(tmp_path).as_posix(), extra.read_bytes()),),
    )
    assert len(manifest["attempts"][0]["gates"][0]["artifacts"]) == 2
    report = validate_manifest(manifest, repo_root=tmp_path, as_of=FREEZE + timedelta(minutes=2))
    assert not any(f.code in {"invalid_artifacts", "artifact_digest_mismatch"} for f in report.findings)


def test_contract_rejects_registry_drift_and_unauthorized_gate_signer(tmp_path):
    manifest = _complete_attempt(tmp_path)
    manifest["attempts"][0]["attestations"][0]["approver_handle"] = "not-in-registry"
    report = validate_manifest(manifest, repo_root=tmp_path, as_of=FREEZE + timedelta(minutes=20))
    assert any(f.code == "unauthorized_signer" for f in report.findings)
    registry_path = tmp_path / "docs/release-readiness/release-authority-registry.json"
    registry_path.write_text(json.dumps({"registry_version": "later", "roles": {}}), encoding="utf-8")
    report = validate_manifest(manifest, repo_root=tmp_path, as_of=FREEZE + timedelta(minutes=20))
    assert any(f.code == "registry_digest_mismatch" for f in report.findings)


def test_go_requires_an_authorized_verified_release_seal(tmp_path):
    manifest = _complete_attempt(tmp_path)
    manifest["disposition"] = "go"  # simulates the human's separate final action
    manifest["finalized_evidence_commit"] = COMMIT
    manifest["release_owner_attestation"] = {
        "role": "release_owner", "approver_handle": "release_owner-user",
        "key_fingerprint": "FPR-release_owner", "attested_at": (FREEZE + timedelta(minutes=12)).isoformat(),
        "attempt_id": "attempt-001", "candidate_id": manifest["candidate_id"],
        "watermark_digest": manifest["attempts"][0]["watermark_digest"], "signature": "owner-signed",
    }
    manifest["release_seal"] = {
        "tag": "release-rc", "target_commit": COMMIT, "signer_handle": "release_owner-user",
        "key_fingerprint": "FPR-release_owner", "timestamp": (FREEZE + timedelta(minutes=13)).isoformat(),
    }
    report = validate_manifest(manifest, repo_root=tmp_path, as_of=FREEZE + timedelta(days=2), git_verifier=lambda *_: True)
    assert report.ok
    assert report.readiness == "go_verified"
    report = validate_manifest(manifest, repo_root=tmp_path, as_of=FREEZE + timedelta(minutes=14), git_verifier=lambda *_: False)
    assert any(f.code == "release_seal_verification_failed" for f in report.findings)
