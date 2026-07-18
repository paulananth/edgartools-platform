"""Build Step Functions input JSON for Ticket 20 strict bulk-load.

Reads optional freeze metadata from a candidate manifest (local or s3://),
validates agent-window eligibility when --preflight is set, and writes the
exact input shape expected by edgartools-*-bronze-seed-silver-gold in
release_mode.

Example::

    uv run python -m edgar_warehouse.scripts.build_ticket20_strict_execution_input \\
      --candidate-manifest s3://edgartools-prodb-bronze/warehouse/bronze/reference/\\
relationship_release/ticket20-agent-…/candidate_manifest.json \\
      --candidate-batches-key warehouse/bronze/reference/relationship_release/\\
ticket20-agent-…/candidate_batches.jsonl \\
      --attestations-json '{"warehouse":"…","mdm":"…","graph":"…",\\
"release_data_operator":"…","release_owner":"…"}' \\
      --preflight \\
      --output /tmp/ticket20-strict-input.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    build_ticket20_strict_execution_input,
    normalize_s3_object_key,
    preflight_strict_release_manifest,
)
from edgar_warehouse.infrastructure.object_storage import read_bytes, write_uri_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-manifest",
        required=True,
        help="Local path or s3:// URI of candidate_manifest.json",
    )
    parser.add_argument(
        "--candidate-batches-key",
        default=None,
        help=(
            "Bucket-relative key or s3:// URI for cik batches JSONL. "
            "Default: sibling candidate_batches.jsonl next to the manifest."
        ),
    )
    parser.add_argument(
        "--attestations-json",
        required=True,
        help="JSON object with five named gate attestation roles",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Fail closed unless the freeze is agent-window eligible",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Local path or s3:// URI for the execution input JSON",
    )
    return parser


def _default_batches_key(manifest_ref: str) -> str:
    key = normalize_s3_object_key(manifest_ref, field_name="candidate_manifest")
    if key.endswith("candidate_manifest.json"):
        return key[: -len("candidate_manifest.json")] + "candidate_batches.jsonl"
    parent = key.rsplit("/", 1)[0] if "/" in key else ""
    return f"{parent}/candidate_batches.jsonl" if parent else "candidate_batches.jsonl"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw_manifest = read_bytes(str(args.candidate_manifest)).decode("utf-8")
        manifest = json.loads(raw_manifest)
        if args.preflight:
            preflight_strict_release_manifest(manifest)
        try:
            attestations = json.loads(str(args.attestations_json))
        except json.JSONDecodeError as exc:
            raise InventoryError("attestations-json must be valid JSON") from exc
        batches_ref = args.candidate_batches_key or _default_batches_key(
            str(args.candidate_manifest)
        )
        payload = build_ticket20_strict_execution_input(
            candidate_manifest_key=str(args.candidate_manifest),
            candidate_batches_key=str(batches_ref),
            attestations=attestations,
            batch_size=int(args.batch_size),
            watermark=manifest.get("watermark"),
            fingerprint=str(manifest.get("fingerprint") or "") or None,
        )
        body = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        write_uri_text(str(args.output), body)
        # Also print for operators piping into aws cli.
        print(body, end="")
    except (OSError, UnicodeError, json.JSONDecodeError, InventoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
