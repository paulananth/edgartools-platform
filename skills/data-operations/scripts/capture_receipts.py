#!/usr/bin/env python3
"""Give a capture folder the receipts file `edgar-warehouse load` reads.

`provider.capture` leaves one snapshot file per document and no `receipts.jsonl`. A load takes its documents from
that file: one row per file, `{"file": <path inside the folder>, "sha256": <of the file's bytes>}`. This writes it
from the files already in the folder, sorted by path, and prints the counts.

    capture_receipts.py <capture folder> [--glob "*.capture.zip"]

It never replaces a receipts file and never changes a captured file: a capture is additive and immutable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

RECEIPTS = "receipts.jsonl"


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def rows(folder: Path, pattern: str) -> list[dict]:
    """One receipt per matching file, by path inside the folder, never the receipts file itself."""
    found = sorted(path for path in folder.rglob(pattern) if path.is_file() and path.name != RECEIPTS)
    return [{"file": path.relative_to(folder).as_posix(), "sha256": digest(path)} for path in found]


def write(folder: Path, pattern: str) -> int:
    target = folder / RECEIPTS
    if target.exists():
        raise SystemExit(f"{target} exists: a capture's receipts are never replaced")
    receipts = rows(folder, pattern)
    if not receipts:
        raise SystemExit(f"No file matches {pattern} in {folder}")
    target.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in receipts), encoding="utf-8")
    return len(receipts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--glob", default="*.capture.zip", help="the files to give a receipt (default: %(default)s)")
    args = parser.parse_args()
    if not args.folder.is_dir():
        raise SystemExit(f"{args.folder} is not a folder")
    print(f"{write(args.folder, args.glob)} receipts written to {args.folder / RECEIPTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
