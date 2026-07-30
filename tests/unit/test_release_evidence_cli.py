"""CLI wrapper for ticket 09's Release Evidence Automation.

Thin argparse layer over edgar_warehouse.application.release_evidence — see
tests/application/test_release_evidence.py for the pure-logic test suite.
These tests exercise init/add-gate/validate end to end against a scratch
repo_root, the way an operator would actually invoke the tool.
"""

from __future__ import annotations

import json
from pathlib import Path

from edgar_warehouse.scripts import release_evidence_cli as command

COMMIT_SHA = "e0fa0eaafb095c18ad75659cadb4066b5426d327"
CANDIDATE_ID = "rc-20260729-e0fa0eaafb09"
WATERMARK_JSON = json.dumps(
    {
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
)


def _init(tmp_path: Path, **overrides: str) -> int:
    args = [
        "init",
        "--repo-root",
        str(tmp_path),
        "--commit-sha",
        COMMIT_SHA,
        "--source-branch",
        "main",
        "--warehouse-image-digest",
        "sha256:" + "1" * 64,
        "--mdm-image-digest",
        "sha256:" + "2" * 64,
        "--watermark-json",
        WATERMARK_JSON,
        "--identity-freeze-timestamp",
        "2026-07-29T12:00:00+00:00",
    ]
    for flag, value in overrides.items():
        args += [f"--{flag.replace('_', '-')}", value]
    return command.main(args)


def _candidate_dir(tmp_path: Path) -> Path:
    return tmp_path / "docs/release-readiness/releases" / CANDIDATE_ID


class TestInit:
    def test_creates_manifest_and_evidence_dir(self, tmp_path: Path) -> None:
        exit_code = _init(tmp_path)
        assert exit_code == 0
        candidate_dir = _candidate_dir(tmp_path)
        manifest_path = candidate_dir / "release-evidence.json"
        assert manifest_path.exists()
        assert (candidate_dir / "evidence").is_dir()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["candidate_id"] == CANDIDATE_ID
        assert manifest["commit_sha"] == COMMIT_SHA
        assert manifest["gates"] == []

    def test_reinit_with_identical_inputs_is_an_idempotent_no_op(
        self, tmp_path: Path
    ) -> None:
        assert _init(tmp_path) == 0
        # Same commit, same digests, same watermark, same freeze timestamp —
        # re-running init (e.g. a retried deploy step) must succeed quietly,
        # not treat a byte-identical re-request as a mutation attempt.
        assert _init(tmp_path) == 0
        manifest_path = _candidate_dir(tmp_path) / "release-evidence.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["commit_sha"] == COMMIT_SHA
        assert manifest["gates"] == []

    def test_reinit_with_a_changed_image_digest_is_rejected_not_silently_merged(
        self, tmp_path: Path
    ) -> None:
        """Ticket 01: "Any commit or image-digest change creates a new
        candidate." Same commit + same date collide on the same candidate_id
        text, so this must fail loudly rather than silently overwrite the
        frozen original with different content."""
        assert _init(tmp_path) == 0
        conflicting = _init(tmp_path, warehouse_image_digest="sha256:" + "9" * 64)
        assert conflicting != 0
        manifest_path = _candidate_dir(tmp_path) / "release-evidence.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        # untouched by the rejected conflicting init
        assert manifest["warehouse_image_digest"] == "sha256:" + "1" * 64

    def test_add_gate_against_a_missing_candidate_reports_a_clean_error(
        self, tmp_path: Path
    ) -> None:
        missing_dir = tmp_path / "docs/release-readiness/releases/rc-does-not-exist"
        evidence_path = tmp_path / "evidence.json"
        evidence_path.write_bytes(b"{}")
        exit_code = command.main(
            [
                "add-gate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(missing_dir),
                "--gate-name",
                "x",
                "--status",
                "pass",
                "--evidence-file",
                str(evidence_path),
                "--media-type",
                "application/json",
                "--capture-tool",
                "x",
                "--capture-tool-version",
                "1.0.0",
                "--captured-at",
                "2026-07-29T12:05:00+00:00",
            ]
        )
        assert exit_code != 0  # not a raw traceback / uncaught exception

    def test_validate_against_a_missing_candidate_reports_a_clean_error(
        self, tmp_path: Path
    ) -> None:
        missing_dir = tmp_path / "docs/release-readiness/releases/rc-does-not-exist"
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(missing_dir),
                "--as-of",
                "2026-07-29T12:30:00+00:00",
            ]
        )
        assert exit_code != 0  # not a raw traceback / uncaught exception

    def test_rejects_malformed_image_digest(self, tmp_path: Path) -> None:
        exit_code = command.main(
            [
                "init",
                "--repo-root",
                str(tmp_path),
                "--commit-sha",
                COMMIT_SHA,
                "--source-branch",
                "main",
                "--warehouse-image-digest",
                "690839588395.dkr.ecr.us-east-1.amazonaws.com/x@sha256:" + "1" * 64,
                "--mdm-image-digest",
                "sha256:" + "2" * 64,
                "--watermark-json",
                WATERMARK_JSON,
                "--identity-freeze-timestamp",
                "2026-07-29T12:00:00+00:00",
            ]
        )
        assert exit_code != 0
        assert not (_candidate_dir(tmp_path) / "release-evidence.json").exists()

    def test_rejects_non_object_watermark_before_writing(self, tmp_path: Path) -> None:
        exit_code = _init(tmp_path, watermark_json="[]")
        assert exit_code != 0
        assert not (_candidate_dir(tmp_path) / "release-evidence.json").exists()

    def test_rejects_secret_in_watermark_before_writing(self, tmp_path: Path) -> None:
        watermark = json.loads(WATERMARK_JSON)
        watermark["snowflake_export"]["run_id"] = (
            "snowflake://release_user:password@org-account/database"
        )
        exit_code = _init(tmp_path, watermark_json=json.dumps(watermark))
        assert exit_code != 0
        assert not (_candidate_dir(tmp_path) / "release-evidence.json").exists()

    def test_rejects_symlinked_canonical_candidate_directory_before_writing(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        candidate_dir = _candidate_dir(tmp_path)
        candidate_dir.parent.mkdir(parents=True)
        candidate_dir.symlink_to(outside, target_is_directory=True)
        assert _init(tmp_path) == 1
        assert not (outside / "release-evidence.json").exists()
        assert not (outside / "evidence").exists()


class TestAddGate:
    def _evidence_file(
        self, tmp_path: Path, content: bytes = b'{"status": "pass"}'
    ) -> Path:
        evidence_dir = _candidate_dir(tmp_path) / "evidence"
        evidence_path = evidence_dir / "maxconcurrency4-data-integrity.json"
        evidence_path.write_bytes(content)
        return evidence_path

    def test_appends_gate_and_persists_it(self, tmp_path: Path) -> None:
        assert _init(tmp_path) == 0
        evidence_path = self._evidence_file(tmp_path)
        exit_code = command.main(
            [
                "add-gate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--gate-name",
                "batchsilver_integrity",
                "--status",
                "pass",
                "--evidence-file",
                str(evidence_path),
                "--media-type",
                "application/json",
                "--capture-tool",
                "maxconcurrency4_proof.py",
                "--capture-tool-version",
                "1.0.0",
                "--captured-at",
                "2026-07-29T12:05:00+00:00",
            ]
        )
        assert exit_code == 0
        manifest = json.loads(
            (_candidate_dir(tmp_path) / "release-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        assert len(manifest["gates"]) == 1
        assert manifest["gates"][0]["gate_name"] == "batchsilver_integrity"
        assert manifest["gates"][0]["evidence_path"] == (
            f"docs/release-readiness/releases/{CANDIDATE_ID}/evidence/"
            "maxconcurrency4-data-integrity.json"
        )

    def test_rejects_evidence_with_a_secret_and_does_not_persist(
        self, tmp_path: Path
    ) -> None:
        assert _init(tmp_path) == 0
        evidence_path = self._evidence_file(
            tmp_path, content=b'{"arn": "arn:aws:iam::690839588395:role/x"}'
        )
        exit_code = command.main(
            [
                "add-gate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--gate-name",
                "leaky_gate",
                "--status",
                "pass",
                "--evidence-file",
                str(evidence_path),
                "--media-type",
                "application/json",
                "--capture-tool",
                "x",
                "--capture-tool-version",
                "1.0.0",
                "--captured-at",
                "2026-07-29T12:05:00+00:00",
            ]
        )
        assert exit_code != 0
        manifest = json.loads(
            (_candidate_dir(tmp_path) / "release-evidence.json").read_text(
                encoding="utf-8"
            )
        )
        assert manifest["gates"] == []

    def test_rejects_manifest_loaded_from_noncanonical_candidate_directory(
        self, tmp_path: Path
    ) -> None:
        assert _init(tmp_path) == 0
        untrusted_dir = tmp_path / "untrusted" / "nested"
        untrusted_dir.mkdir(parents=True)
        copied_manifest = untrusted_dir / "release-evidence.json"
        copied_manifest.write_bytes(
            (_candidate_dir(tmp_path) / "release-evidence.json").read_bytes()
        )
        evidence_path = self._evidence_file(tmp_path)
        exit_code = command.main(
            [
                "add-gate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(untrusted_dir),
                "--gate-name",
                "batchsilver_integrity",
                "--status",
                "pass",
                "--evidence-file",
                str(evidence_path),
                "--media-type",
                "application/json",
                "--capture-tool",
                "x",
                "--capture-tool-version",
                "1.0.0",
                "--captured-at",
                "2026-07-29T12:05:00+00:00",
            ]
        )
        assert exit_code == 1
        assert json.loads(copied_manifest.read_text(encoding="utf-8"))["gates"] == []


class TestValidate:
    def _init_and_add_gate(self, tmp_path: Path) -> None:
        assert _init(tmp_path) == 0
        evidence_dir = _candidate_dir(tmp_path) / "evidence"
        evidence_path = evidence_dir / "a.json"
        evidence_path.write_bytes(b'{"status": "pass"}')
        assert (
            command.main(
                [
                    "add-gate",
                    "--repo-root",
                    str(tmp_path),
                    "--candidate-dir",
                    str(_candidate_dir(tmp_path)),
                    "--gate-name",
                    "batchsilver_integrity",
                    "--status",
                    "pass",
                    "--evidence-file",
                    str(evidence_path),
                    "--media-type",
                    "application/json",
                    "--capture-tool",
                    "x",
                    "--capture-tool-version",
                    "1.0.0",
                    "--captured-at",
                    "2026-07-29T12:05:00+00:00",
                ]
            )
            == 0
        )

    def test_validate_ok(self, tmp_path: Path, capsys) -> None:
        self._init_and_add_gate(tmp_path)
        capsys.readouterr()  # drain init/add-gate output before validate
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--as-of",
                "2026-07-29T12:30:00+00:00",
            ]
        )
        assert exit_code == 0
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is True
        assert report["findings"] == []

    def test_rejects_manifest_loaded_from_noncanonical_candidate_directory(
        self, tmp_path: Path, capsys
    ) -> None:
        assert _init(tmp_path) == 0
        capsys.readouterr()
        untrusted_dir = tmp_path / "untrusted" / "nested"
        untrusted_dir.mkdir(parents=True)
        (untrusted_dir / "release-evidence.json").write_bytes(
            (_candidate_dir(tmp_path) / "release-evidence.json").read_bytes()
        )
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(untrusted_dir),
                "--as-of",
                "2026-07-29T12:30:00+00:00",
            ]
        )
        assert exit_code == 1
        assert "canonical candidate directory" in capsys.readouterr().err

    def test_rejects_symlinked_manifest_file(self, tmp_path: Path, capsys) -> None:
        assert _init(tmp_path) == 0
        capsys.readouterr()
        manifest_path = _candidate_dir(tmp_path) / "release-evidence.json"
        outside_manifest = tmp_path / "outside-release-evidence.json"
        manifest_path.replace(outside_manifest)
        manifest_path.symlink_to(outside_manifest)
        assert _init(tmp_path) == 1
        capsys.readouterr()
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--as-of",
                "2026-07-29T12:30:00+00:00",
            ]
        )
        assert exit_code == 1
        assert "regular non-symlink file" in capsys.readouterr().err

    def test_validate_reports_findings_and_nonzero_exit(
        self, tmp_path: Path, capsys
    ) -> None:
        self._init_and_add_gate(tmp_path)
        capsys.readouterr()  # drain init/add-gate output before validate
        # 10 days later -> well past the 24h freshness window
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--as-of",
                "2026-08-08T12:30:00+00:00",
            ]
        )
        assert exit_code == 1
        report = json.loads(capsys.readouterr().out)
        assert report["ok"] is False
        assert any(f["code"] == "evidence_stale" for f in report["findings"])

    def test_validate_writes_report_file_when_requested(
        self, tmp_path: Path, capsys
    ) -> None:
        self._init_and_add_gate(tmp_path)
        capsys.readouterr()  # drain init/add-gate output before validate
        report_out = tmp_path / "validation-report.json"
        exit_code = command.main(
            [
                "validate",
                "--repo-root",
                str(tmp_path),
                "--candidate-dir",
                str(_candidate_dir(tmp_path)),
                "--as-of",
                "2026-07-29T12:30:00+00:00",
                "--report-out",
                str(report_out),
            ]
        )
        assert exit_code == 0
        written = json.loads(report_out.read_text(encoding="utf-8"))
        assert written["ok"] is True
