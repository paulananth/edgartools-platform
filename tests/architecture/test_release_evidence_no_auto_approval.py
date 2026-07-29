"""Ticket 09 (release-readiness map): Release Evidence Automation must never
manufacture human approval.

Ticket 01's Answer is explicit: "It must never manufacture human approval."
Gate Attestations and the final GO/NO_GO disposition (and Release Seal) are
reserved for humans. Documentation won't hold this — a test does: this file
asserts, both statically (no forbidden write sites in the source) and
behaviorally (running every public entry point never produces a non-null
disposition or a populated attestations list), that
``edgar_warehouse.application.release_evidence`` cannot set them itself.

Also enforces the determinism precondition ticket 09 depends on: the pure
module must never read the wall clock. Every timestamp is a caller-supplied
argument (see ``tests/application/test_release_evidence.py``'s determinism
test), which this file guards against silently regressing.
"""

from __future__ import annotations

import inspect
import unittest
from datetime import datetime, timezone
from pathlib import Path

from edgar_warehouse.application import release_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "edgar_warehouse" / "application" / "release_evidence.py"

_FORBIDDEN_APPROVAL_TOKENS = (
    '"disposition"] = "go"',
    '"disposition"] = "no_go"',
    "['disposition'] = 'go'",
    "['disposition'] = 'no_go'",
    "disposition = \"go\"",
    "disposition = \"no_go\"",
)

_FORBIDDEN_FUNCTION_NAME_FRAGMENTS = ("attest", "approve", "seal", "set_disposition")

_WALL_CLOCK_READ_TOKENS = ("datetime.now(", "datetime.utcnow(", "time.time(")


class NoAutoApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_source_never_literally_assigns_a_go_or_no_go_disposition(self) -> None:
        offenders = [
            token for token in _FORBIDDEN_APPROVAL_TOKENS if token in self.source
        ]
        self.assertEqual(offenders, [], f"forbidden disposition assignment: {offenders}")

    def test_no_public_function_named_like_an_approval_action(self) -> None:
        public_functions = [
            name
            for name, obj in vars(release_evidence).items()
            if inspect.isfunction(obj) and not name.startswith("_")
        ]
        offenders = [
            name
            for name in public_functions
            for fragment in _FORBIDDEN_FUNCTION_NAME_FRAGMENTS
            if fragment in name.lower()
        ]
        self.assertEqual(
            offenders,
            [],
            f"found a function whose name implies it manufactures approval: {offenders}",
        )

    def test_module_never_reads_the_wall_clock(self) -> None:
        offenders = [
            token for token in _WALL_CLOCK_READ_TOKENS if token in self.source
        ]
        self.assertEqual(
            offenders,
            [],
            "release_evidence.py must never read the wall clock itself; every "
            "timestamp must be a caller-supplied argument for determinism",
        )

    def test_build_manifest_never_produces_a_disposition_or_attestation(self) -> None:
        manifest = release_evidence.build_manifest(
            commit_sha="e0fa0eaafb095c18ad75659cadb4066b5426d327",
            source_branch="main",
            warehouse_image_digest="sha256:" + "1" * 64,
            mdm_image_digest="sha256:" + "2" * 64,
            release_data_watermark={},
            identity_freeze_timestamp="2026-07-29T12:00:00+00:00",
        )
        self.assertIsNone(manifest["disposition"])
        self.assertEqual(manifest["attestations"], [])
        self.assertIsNone(manifest["release_seal"])

    def test_add_gate_never_touches_disposition_or_attestations(self) -> None:
        manifest = release_evidence.build_manifest(
            commit_sha="e0fa0eaafb095c18ad75659cadb4066b5426d327",
            source_branch="main",
            warehouse_image_digest="sha256:" + "1" * 64,
            mdm_image_digest="sha256:" + "2" * 64,
            release_data_watermark={},
            identity_freeze_timestamp="2026-07-29T12:00:00+00:00",
        )
        updated = release_evidence.add_gate(
            manifest,
            gate_name="some_gate",
            status="pass",
            evidence_relpath=(
                f"docs/release-readiness/releases/{manifest['candidate_id']}/"
                "evidence/x.json"
            ),
            evidence_bytes=b"{}",
            media_type="application/json",
            capture_tool="x",
            capture_tool_version="1.0.0",
            captured_at="2026-07-29T12:05:00+00:00",
        )
        self.assertIsNone(updated["disposition"])
        self.assertEqual(updated["attestations"], [])
        self.assertIsNone(updated["release_seal"])

    def test_validate_manifest_is_read_only_even_when_disposition_is_set(self) -> None:
        manifest = release_evidence.build_manifest(
            commit_sha="e0fa0eaafb095c18ad75659cadb4066b5426d327",
            source_branch="main",
            warehouse_image_digest="sha256:" + "1" * 64,
            mdm_image_digest="sha256:" + "2" * 64,
            release_data_watermark={},
            identity_freeze_timestamp="2026-07-29T12:00:00+00:00",
        )
        manifest = dict(manifest)
        manifest["disposition"] = "go"  # simulates a human-attested final state
        before = dict(manifest)
        release_evidence.validate_manifest(
            manifest, repo_root=REPO_ROOT, as_of=datetime.now(timezone.utc)
        )
        self.assertEqual(manifest, before, "validate_manifest must never mutate its input")


if __name__ == "__main__":
    unittest.main()
