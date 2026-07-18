"""Preflight a Ticket 20 frozen candidate manifest before strict bulk-load.

Fails closed unless the freeze carries locked agent ``coverage_by_document_type``
windows and every candidate sits inside those windows. Use this after building
a new agent-window freeze and **before** starting ``bronze_seed_silver_gold``
in ``release_mode``.

Legacy 2013-era freezes without a type map exit non-zero (not GO).

Example::

    uv run python -m edgar_warehouse.scripts.validate_relationship_release_manifest \\
      --candidate-manifest s3://edgartools-prodb-bronze/warehouse/bronze/reference/\\
relationship_release/ticket20-agent-…/candidate_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    preflight_strict_release_manifest,
)
from edgar_warehouse.infrastructure.object_storage import read_bytes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-manifest",
        required=True,
        help="Local path or s3:// URI of the frozen candidate_manifest.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(read_bytes(str(args.candidate_manifest)).decode("utf-8"))
        report = preflight_strict_release_manifest(payload)
        report["candidate_manifest"] = str(args.candidate_manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, InventoryError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "candidate_manifest": str(args.candidate_manifest),
                    "strict_release_eligible": False,
                    "disposition": "NO_GO",
                    "error": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
