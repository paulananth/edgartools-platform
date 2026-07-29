"""CLI for ticket 09's Release Evidence Automation.

A thin argparse wrapper over the pure logic in
``edgar_warehouse.application.release_evidence``. All wall-clock reads and
filesystem I/O live here; the imported module stays pure and unit-testable
without touching AWS/Snowflake/MDM or the clock.

Subcommands:

``init``
    Open a new Candidate Evidence Set at
    ``<repo-root>/docs/release-readiness/releases/rc-<date>-<commit>/``.
    Refuses to run if that directory's manifest already exists — identity,
    once frozen, is immutable; a changed commit or image digest is a new
    candidate, not an edit to this one.

``add-gate``
    Append one sanitized gate record pointing at an evidence file already
    written under the candidate's own ``evidence/`` directory.

``validate``
    Run schema/lineage/digest/freshness/secret-scan validation and print a
    JSON report (exit code 1 if any finding).

Example::

    uv run python -m edgar_warehouse.scripts.release_evidence_cli init \\
      --commit-sha e0fa0eaafb095c18ad75659cadb4066b5426d327 \\
      --source-branch main \\
      --warehouse-image-digest sha256:... \\
      --mdm-image-digest sha256:... \\
      --watermark-json '{"bronze_input_manifest_digest": "sha256:...", ...}'
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from edgar_warehouse.application.release_evidence import (
    ReleaseEvidenceError,
    add_gate,
    build_manifest,
    validate_manifest,
)


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    tmp_path.replace(path)


def _load_manifest(candidate_dir: Path) -> dict[str, Any]:
    manifest_path = candidate_dir / "release-evidence.json"
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _cmd_init(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    watermark = json.loads(args.watermark_json)
    identity_freeze_timestamp = (
        args.identity_freeze_timestamp
        or datetime.now(timezone.utc).isoformat()
    )

    manifest = build_manifest(
        commit_sha=args.commit_sha,
        source_branch=args.source_branch,
        warehouse_image_digest=args.warehouse_image_digest,
        mdm_image_digest=args.mdm_image_digest,
        release_data_watermark=watermark,
        identity_freeze_timestamp=identity_freeze_timestamp,
    )

    candidate_dir = repo_root / "docs/release-readiness/releases" / manifest["candidate_id"]
    manifest_path = candidate_dir / "release-evidence.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        # A byte-identical re-request (e.g. a retried deploy step) is a
        # harmless no-op. Anything else colliding on the same candidate_id
        # text (same commit, same date, different digests/branch/watermark)
        # is the exact case ticket 01 forbids silently merging: "Any commit
        # or image-digest change creates a new candidate."
        if existing == manifest:
            print(json.dumps({"candidate_id": manifest["candidate_id"], "path": str(manifest_path)}))
            return 0
        print(
            f"error: candidate {manifest['candidate_id']!r} is already frozen at "
            f"{manifest_path} with different content; a changed commit or "
            "image digest is a new candidate, not an edit to this one — this "
            "collision needs a distinct candidate identity, not a repeated init",
            file=sys.stderr,
        )
        return 1

    (candidate_dir / "evidence").mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_path, manifest)
    print(json.dumps({"candidate_id": manifest["candidate_id"], "path": str(manifest_path)}))
    return 0


def _cmd_add_gate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    candidate_dir = Path(args.candidate_dir)
    manifest = _load_manifest(candidate_dir)

    evidence_file = Path(args.evidence_file).resolve()
    evidence_relpath = evidence_file.relative_to(repo_root).as_posix()
    evidence_bytes = evidence_file.read_bytes()

    captured_at = args.captured_at or datetime.now(timezone.utc).isoformat()

    updated = add_gate(
        manifest,
        gate_name=args.gate_name,
        status=args.status,
        evidence_relpath=evidence_relpath,
        evidence_bytes=evidence_bytes,
        media_type=args.media_type,
        capture_tool=args.capture_tool,
        capture_tool_version=args.capture_tool_version,
        captured_at=captured_at,
    )

    _write_manifest(candidate_dir / "release-evidence.json", updated)
    print(json.dumps(updated["gates"][-1]))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root)
    candidate_dir = Path(args.candidate_dir)
    manifest = _load_manifest(candidate_dir)

    as_of = (
        datetime.fromisoformat(args.as_of)
        if args.as_of
        else datetime.now(timezone.utc)
    )

    report = validate_manifest(manifest, repo_root=repo_root, as_of=as_of)
    payload = {
        "ok": report.ok,
        "findings": [
            {"code": f.code, "message": f.message, "gate_name": f.gate_name}
            for f in report.findings
        ],
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.report_out:
        Path(args.report_out).write_text(rendered + "\n", encoding="utf-8")

    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Open a new Candidate Evidence Set and freeze its identity."
    )
    init_parser.add_argument("--repo-root", default=".")
    init_parser.add_argument("--commit-sha", required=True)
    init_parser.add_argument("--source-branch", required=True)
    init_parser.add_argument("--warehouse-image-digest", required=True)
    init_parser.add_argument("--mdm-image-digest", required=True)
    init_parser.add_argument(
        "--watermark-json",
        required=True,
        help="Inline JSON object for the Release Data Watermark.",
    )
    init_parser.add_argument(
        "--identity-freeze-timestamp",
        default=None,
        help="ISO8601 UTC timestamp; defaults to the current time.",
    )
    init_parser.set_defaults(func=_cmd_init)

    add_gate_parser = subparsers.add_parser(
        "add-gate", help="Append one sanitized gate record."
    )
    add_gate_parser.add_argument("--repo-root", default=".")
    add_gate_parser.add_argument("--candidate-dir", required=True)
    add_gate_parser.add_argument("--gate-name", required=True)
    add_gate_parser.add_argument("--status", required=True, choices=["pass", "fail"])
    add_gate_parser.add_argument(
        "--evidence-file",
        required=True,
        help="Path to the evidence file, already written under the candidate's evidence/ dir.",
    )
    add_gate_parser.add_argument("--media-type", required=True)
    add_gate_parser.add_argument("--capture-tool", required=True)
    add_gate_parser.add_argument("--capture-tool-version", required=True)
    add_gate_parser.add_argument(
        "--captured-at",
        default=None,
        help="ISO8601 UTC timestamp; defaults to the current time.",
    )
    add_gate_parser.set_defaults(func=_cmd_add_gate)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate schema, lineage, freshness, and secrets."
    )
    validate_parser.add_argument("--repo-root", default=".")
    validate_parser.add_argument("--candidate-dir", required=True)
    validate_parser.add_argument(
        "--as-of",
        default=None,
        help="ISO8601 UTC timestamp; defaults to the current time.",
    )
    validate_parser.add_argument("--report-out", default=None)
    validate_parser.set_defaults(func=_cmd_validate)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, UnicodeError, json.JSONDecodeError, ReleaseEvidenceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
