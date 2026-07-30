#!/usr/bin/env python3
"""Small, credential-free helpers for dashboard release control."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"(?:^|/)releases/(sha-[0-9a-f]{12})/")


def _modified_sort_key(value: str) -> float:
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(value).timestamp()
        except (TypeError, ValueError):
            return 0.0


def prune_candidates(listing: Any, *, retain: int) -> list[str]:
    """Return exact release versions safe to remove, newest first retained."""
    if not 1 <= retain <= 50:
        raise ValueError("retain must be between 1 and 50")
    rows = listing[0] if isinstance(listing, list) and listing and isinstance(listing[0], list) else listing
    if not isinstance(rows, list):
        raise TypeError("SnowCLI LIST output must be a JSON array")
    newest_by_version: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        match = _VERSION_RE.search(str(row.get("name", "")))
        if not match:
            continue
        version = match.group(1)
        modified = str(row.get("last_modified", ""))
        newest_by_version[version] = max(newest_by_version.get(version, ""), modified)
    ordered = sorted(
        newest_by_version,
        key=lambda version: (_modified_sort_key(newest_by_version[version]), version),
        reverse=True,
    )
    return ordered[retain:]


def drift_status(dashboard_commit: str, warehouse_evidence: Path | None) -> dict[str, str | None]:
    """Compare dashboard source identity to warehouse release identity."""
    if warehouse_evidence is None:
        return {
            "status": "unknown",
            "dashboard_git_commit": dashboard_commit,
            "warehouse_git_commit": None,
        }
    payload = json.loads(warehouse_evidence.read_text(encoding="utf-8"))
    warehouse_commit = payload.get("commit_sha") or payload.get("git_commit")
    if not isinstance(warehouse_commit, str) or not re.fullmatch(
        r"[0-9a-f]{40}", warehouse_commit
    ):
        raise ValueError("warehouse evidence has no canonical 40-character commit")
    return {
        "status": "aligned" if warehouse_commit == dashboard_commit else "drift",
        "dashboard_git_commit": dashboard_commit,
        "warehouse_git_commit": warehouse_commit,
    }


def verify_downloaded(
    source_dir: Path, download_dir: Path, files: list[str]
) -> dict[str, str]:
    """Verify GET-back bytes from the stage against the promoted sources."""
    verified: dict[str, str] = {}
    for filename in files:
        source = source_dir / filename
        downloaded = download_dir / filename
        if not downloaded.is_file():
            raise ValueError(f"downloaded stage verification is missing {filename}")
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        actual = hashlib.sha256(downloaded.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"downloaded stage digest mismatch for {filename}")
        verified[filename] = actual
    return verified


def verify_streamlit(
    listing: Any, *, expected_name: str, expected_owner: str, expected_release: str
) -> dict[str, str]:
    """Verify one deployed Streamlit object's identity and owner boundary."""
    rows = listing[0] if isinstance(listing, list) and listing and isinstance(listing[0], list) else listing
    if not isinstance(rows, list):
        raise TypeError("SnowCLI SHOW STREAMLITS output must be a JSON array")
    matches = [
        row
        for row in rows
        if isinstance(row, dict)
        and str(row.get("name", "")).upper() == expected_name.upper()
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one Streamlit named {expected_name}")
    row = matches[0]
    if str(row.get("owner", "")).upper() != expected_owner.upper():
        raise ValueError(f"Streamlit owner mismatch for {expected_name}")
    comment = str(row.get("comment", ""))
    if f"release={expected_release}" not in comment:
        raise ValueError(f"Streamlit release identity mismatch for {expected_name}")
    return {
        "name": expected_name.upper(),
        "owner": expected_owner.upper(),
        "release": expected_release,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prune = subparsers.add_parser("prune-candidates")
    prune.add_argument("--listing", type=Path, required=True)
    prune.add_argument("--retain", type=int, required=True)

    drift = subparsers.add_parser("drift-status")
    drift.add_argument("--dashboard-commit", required=True)
    drift.add_argument("--warehouse-evidence", type=Path)

    downloaded = subparsers.add_parser("verify-downloaded")
    downloaded.add_argument("--source-dir", type=Path, required=True)
    downloaded.add_argument("--download-dir", type=Path, required=True)
    downloaded.add_argument("--file", action="append", dest="files", required=True)

    streamlit = subparsers.add_parser("verify-streamlit")
    streamlit.add_argument("--listing", type=Path, required=True)
    streamlit.add_argument("--expected-name", required=True)
    streamlit.add_argument("--expected-owner", required=True)
    streamlit.add_argument("--expected-release", required=True)

    args = parser.parse_args()
    if args.command == "prune-candidates":
        listing = json.loads(args.listing.read_text(encoding="utf-8"))
        for version in prune_candidates(listing, retain=args.retain):
            print(version)
        return 0
    if args.command == "drift-status":
        result = drift_status(args.dashboard_commit, args.warehouse_evidence)
    elif args.command == "verify-downloaded":
        result = verify_downloaded(args.source_dir, args.download_dir, args.files)
    else:
        listing = json.loads(args.listing.read_text(encoding="utf-8"))
        result = verify_streamlit(
            listing,
            expected_name=args.expected_name,
            expected_owner=args.expected_owner,
            expected_release=args.expected_release,
        )
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
