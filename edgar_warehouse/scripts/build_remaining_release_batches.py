"""Build remaining StrictBatchSilver CIK batches for Ticket 20 P0 resume.

After a fail-closed map failure (or any partial success), successful batches
write durable markers under::

    {freeze_prefix}/batch_done/{batch_identity}.json

This operator tool reads the frozen ``candidate_batches.jsonl`` plus those
markers and writes a new JSONL containing only unfinished batches. Point the
next ``bronze_seed_silver_gold`` strict execution's ``candidate_batches_key``
at that remaining file (keep the same ``candidate_manifest_key``).

Example::

    uv run python -m edgar_warehouse.scripts.build_remaining_release_batches \\
      --candidate-batches s3://…/ticket20-…/candidate_batches.jsonl \\
      --output s3://…/ticket20-…/candidate_batches_remaining.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    build_remaining_cik_batches,
    list_done_batch_identities,
    parse_cik_batches_jsonl,
    release_freeze_prefix_from_path,
)
from edgar_warehouse.infrastructure.object_storage import (
    list_uri_child_names,
    read_bytes,
    write_uri_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-batches",
        required=True,
        help="Frozen full cik_batches JSONL (local path or s3:// URI)",
    )
    parser.add_argument(
        "--done-prefix",
        default=None,
        help="Optional batch_done/ prefix; default is {freeze}/batch_done/ next to the batches file",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Remaining batches JSONL destination (local path or s3:// URI)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        batches_text = read_bytes(str(args.candidate_batches)).decode("utf-8")
        all_batches = parse_cik_batches_jsonl(batches_text)
        freeze_prefix = release_freeze_prefix_from_path(str(args.candidate_batches))
        if args.done_prefix:
            done_prefix = str(args.done_prefix)
            if not done_prefix.endswith("/"):
                done_prefix += "/"
        else:
            done_prefix = freeze_prefix + "batch_done/"
        done_names = list_uri_child_names(done_prefix)
        done_ids = list_done_batch_identities(done_names)
        remaining = build_remaining_cik_batches(all_batches, done_ids)
        body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in remaining)
        write_uri_text(str(args.output), body)
    except (OSError, UnicodeError, InventoryError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "candidate_batches": args.candidate_batches,
                "done_prefix": done_prefix,
                "done_batch_count": len(done_ids),
                "total_batch_count": len(all_batches),
                "remaining_batch_count": len(remaining),
                "output": args.output,
            },
            sort_keys=True,
        )
    )
    if not remaining:
        print(
            "warning: remaining batch count is 0 (all batches marked done)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
