"""Select billed warehouse duplicates for VersionId Reclaim.

Sibling of the ADR 0004 staging cleanup: this module never selects current
Canonical Silver keys. Staging cleanup remains a separate script.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

CANONICAL_SILVER_KEYS = frozenset(
    {
        "warehouse/silver/sec/silver.duckdb",
        "warehouse/silver/sec/shards/shard-0.duckdb",
        "warehouse/silver/sec/shards/shard-1.duckdb",
        "warehouse/silver/sec/shards/shard-2.duckdb",
        "warehouse/silver/sec/shards/shard-3.duckdb",
    }
)
IDENTITY_PREFIX = "warehouse/identity_refresh/"
GOLD_PREFIX = "warehouse/gold/"
SHARD_PREFIX = "warehouse/silver/sec/shards/"
SILVER_DUCKDB_KEY = "warehouse/silver/sec/silver.duckdb"
IDENTITY_SKIP_HOURS = 24
DELETE_BATCH_SIZE = 100
TSV_FIELDS = (
    "key",
    "version_id",
    "last_modified",
    "size_bytes",
    "is_latest",
)


class CanonicalSilverDeniedError(ValueError):
    """Raised when a reviewed manifest includes a current Canonical Silver version."""


class ApplyFlagError(ValueError):
    """Raised when --apply is missing its confirm flag or reviewed manifest."""


def require_apply_flags(*, apply: bool, confirm: bool, manifest_path: str | None) -> None:
    if not apply:
        return
    if not confirm:
        raise ApplyFlagError("--apply requires --confirm-delete-duplicates")
    if not manifest_path:
        raise ApplyFlagError("--apply requires --manifest from a reviewed dry run")


def _parse_modified(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace("Z", "+00:00"))


def _row(version: dict[str, Any]) -> dict[str, Any]:
    modified = _parse_modified(version["LastModified"])
    return {
        "key": version["Key"],
        "version_id": version["VersionId"],
        "last_modified": modified.isoformat(),
        "size_bytes": int(version.get("Size") or 0),
        "is_latest": bool(version.get("IsLatest", False)),
        "_modified": modified,
    }


def _identity_run_id(key: str) -> str | None:
    parts = key.split("/")
    if (
        len(parts) >= 5
        and key.startswith("warehouse/identity_refresh/runs/")
    ):
        return parts[3]
    return None


def _gold_table_and_run(key: str) -> tuple[str, str] | None:
    # warehouse/gold/{table}/run_id={slug}/...
    parts = key.split("/")
    if len(parts) < 4 or not key.startswith(GOLD_PREFIX):
        return None
    table = parts[2]
    if table == "runs":
        return None
    run_part = parts[3]
    if not run_part.startswith("run_id="):
        return None
    return table, run_part.removeprefix("run_id=")


def _gold_keep_run_ids(rows: list[dict[str, Any]]) -> set[str]:
    """Keep the newest complete gold run.

    A run is complete when it has a current object for every gold table
    present in the listing. Completeness is parquet coverage, not UUID
    sort and not a partial table's newest LastModified. If no run covers
    every table, fall back to the union of per-table newest run_ids so a
    split listing cannot empty the keep-set.
    """
    tables: set[str] = set()
    current_by_run: dict[str, dict[str, datetime]] = {}
    for row in rows:
        parsed = _gold_table_and_run(str(row["key"]))
        if parsed is None or not row["is_latest"]:
            continue
        table, run_id = parsed
        tables.add(table)
        modified: datetime = row["_modified"]
        by_table = current_by_run.setdefault(run_id, {})
        prior = by_table.get(table)
        if prior is None or modified > prior:
            by_table[table] = modified
    if not tables:
        return set()
    complete: list[tuple[datetime, str]] = []
    for run_id, by_table in current_by_run.items():
        if tables <= by_table.keys():
            complete.append((max(by_table.values()), run_id))
    if complete:
        complete.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return {complete[0][1]}
    newest: dict[str, tuple[datetime, str]] = {}
    for run_id, by_table in current_by_run.items():
        for table, modified in by_table.items():
            prior = newest.get(table)
            if prior is None or modified > prior[0]:
                newest[table] = (modified, run_id)
    return {run_id for _, run_id in newest.values()}


def _identity_skip_runs(rows: list[dict[str, Any]], cutoff: datetime) -> set[str]:
    newest: dict[str, datetime] = {}
    for row in rows:
        run_id = _identity_run_id(str(row["key"]))
        if run_id is None:
            continue
        modified: datetime = row["_modified"]
        prior = newest.get(run_id)
        if prior is None or modified > prior:
            newest[run_id] = modified
    return {run_id for run_id, when in newest.items() if when >= cutoff}


def select_candidates(
    listing: dict[str, Any],
    *,
    now: datetime | None = None,
    identity_skip_hours: int = IDENTITY_SKIP_HOURS,
) -> list[dict[str, Any]]:
    clock = now or datetime.now(UTC)
    cutoff = clock - timedelta(hours=identity_skip_hours)
    rows = [
        _row(version)
        for version in listing.get("Versions") or []
        if isinstance(version.get("Key"), str)
        and isinstance(version.get("VersionId"), str)
        and version.get("LastModified")
    ]
    skip_runs = _identity_skip_runs(rows, cutoff)
    keep_gold = _gold_keep_run_ids(rows)
    selected: list[dict[str, Any]] = []
    for row in rows:
        key = str(row["key"])
        latest = bool(row["is_latest"])
        if key in CANONICAL_SILVER_KEYS:
            if latest:
                continue
            selected.append(row)
            continue
        if key.startswith(IDENTITY_PREFIX):
            run_id = _identity_run_id(key)
            if run_id is None or run_id in skip_runs:
                continue
            selected.append(row)
            continue
        if key.startswith(GOLD_PREFIX):
            parsed = _gold_table_and_run(key)
            if parsed is None:
                continue
            _, run_id = parsed
            if run_id in keep_gold:
                continue
            selected.append(row)
            continue
    selected.sort(key=lambda item: (str(item["key"]), str(item["version_id"])))
    for row in selected:
        row.pop("_modified", None)
    return selected


def summarize_by_prefix(rows: list[dict[str, Any]]) -> dict[str, dict[str, int | float]]:
    groups = {
        "shards": SHARD_PREFIX,
        "silver.duckdb": SILVER_DUCKDB_KEY,
        "identity_refresh": IDENTITY_PREFIX,
        "gold": GOLD_PREFIX,
    }
    summary: dict[str, dict[str, int | float]] = {}
    for name, prefix in groups.items():
        matched = [
            row
            for row in rows
            if str(row["key"]) == prefix or str(row["key"]).startswith(prefix)
        ]
        total = sum(int(row["size_bytes"]) for row in matched)
        summary[name] = {
            "count": len(matched),
            "bytes": total,
            "gib": round(total / 1024**3, 3),
        }
    return summary


def validate_manifest(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        key = str(row["key"])
        latest = str(row.get("is_latest", "")).lower() in {"true", "1"}
        if isinstance(row.get("is_latest"), bool):
            latest = bool(row["is_latest"])
        if key in CANONICAL_SILVER_KEYS and latest:
            raise CanonicalSilverDeniedError(
                f"manifest includes current Canonical Silver version {key}"
            )
        if not row.get("version_id"):
            raise ValueError("manifest row missing version_id")


def write_tsv(path: Any, rows: list[dict[str, Any]]) -> None:
    import csv
    from pathlib import Path

    destination = Path(path)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(TSV_FIELDS), delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: Any) -> list[dict[str, Any]]:
    import csv
    from pathlib import Path

    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
    for row in rows:
        row["size_bytes"] = int(row["size_bytes"])
        row["is_latest"] = str(row["is_latest"]).lower() in {"true", "1"}
    return rows


def merge_listings(listings: list[dict[str, Any]]) -> dict[str, Any]:
    versions: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []
    for listing in listings:
        versions.extend(listing.get("Versions") or [])
        markers.extend(listing.get("DeleteMarkers") or [])
    return {"Versions": versions, "DeleteMarkers": markers}


def iter_delete_batches(
    rows: list[dict[str, Any]], batch_size: int = DELETE_BATCH_SIZE
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for offset in range(0, len(rows), batch_size):
        chunk = rows[offset : offset + batch_size]
        payloads.append(
            {
                "Objects": [
                    {"Key": row["key"], "VersionId": row["version_id"]} for row in chunk
                ],
                "Quiet": False,
            }
        )
    return payloads


def remaining_selected(
    selected: list[dict[str, Any]], post_listing: dict[str, Any]
) -> list[tuple[str, str]]:
    wanted = {(str(row["key"]), str(row["version_id"])) for row in selected}
    return sorted(
        (str(item["Key"]), str(item["VersionId"]))
        for item in post_listing.get("Versions") or []
        if (str(item.get("Key")), str(item.get("VersionId"))) in wanted
    )


def write_summary(
    path: Any,
    *,
    rows: list[dict[str, Any]],
    mode: str,
    account_id: str,
    bucket: str,
    run_id: str,
) -> None:
    import json
    from pathlib import Path

    total = sum(int(row["size_bytes"]) for row in rows)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": mode,
        "account_id": account_id,
        "bucket": bucket,
        "selected_object_versions": len(rows),
        "selected_bytes": total,
        "selected_gib": round(total / 1024**3, 3),
        "by_prefix": summarize_by_prefix(rows),
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="warehouse-duplicate-reclaim")
    sub = parser.add_subparsers(dest="cmd", required=True)

    merge = sub.add_parser("merge-select")
    merge.add_argument("tsv")
    merge.add_argument("summary")
    merge.add_argument("--account-id", required=True)
    merge.add_argument("--bucket", required=True)
    merge.add_argument("--run-id", required=True)
    merge.add_argument("--mode", required=True)
    merge.add_argument("listings", nargs="+")

    validate = sub.add_parser("validate-manifest")
    validate.add_argument("manifest")
    validate.add_argument("copy")

    batches = sub.add_parser("write-batches")
    batches.add_argument("manifest")
    batches.add_argument("output_dir")

    remaining = sub.add_parser("remaining")
    remaining.add_argument("manifest")
    remaining.add_argument("post_listing")
    remaining.add_argument("output")

    args = parser.parse_args(argv)
    if args.cmd == "merge-select":
        listings = [
            json.loads(Path(path).read_text(encoding="utf-8") or "{}")
            for path in args.listings
        ]
        rows = select_candidates(merge_listings(listings))
        write_tsv(args.tsv, rows)
        write_summary(
            args.summary,
            rows=rows,
            mode=args.mode,
            account_id=args.account_id,
            bucket=args.bucket,
            run_id=args.run_id,
        )
        return 0
    if args.cmd == "validate-manifest":
        rows = read_tsv(args.manifest)
        validate_manifest(rows)
        write_tsv(args.copy, rows)
        return 0
    if args.cmd == "write-batches":
        from pathlib import Path as P

        out = P(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        rows = read_tsv(args.manifest)
        validate_manifest(rows)
        payloads = iter_delete_batches(rows)
        if not payloads:
            return 0
        for index, payload in enumerate(payloads, start=1):
            (out / f"batch-{index:04d}.json").write_text(
                json.dumps(payload, indent=2) + "\n", encoding="utf-8"
            )
        return 0
    if args.cmd == "remaining":
        rows = read_tsv(args.manifest)
        post = json.loads(Path(args.post_listing).read_text(encoding="utf-8") or "{}")
        leftover = remaining_selected(rows, post)
        Path(args.output).write_text(
            json.dumps(
                {
                    "selected_versions": len(rows),
                    "selected_versions_still_present": len(leftover),
                    "complete": not leftover,
                    "remaining": [
                        {"key": key, "version_id": version_id}
                        for key, version_id in leftover
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
