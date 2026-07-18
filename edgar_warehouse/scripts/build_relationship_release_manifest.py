"""Freeze the strict relationship bulk-load candidate manifest.

This operator command reads the production silver snapshot, reconciles its
bounded company universe to every SEC quarterly index in the coverage window,
and writes both the immutable candidate manifest and the JSONL input consumed
by a Step Functions Distributed Map.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
import duckdb
import edgar

from edgar_warehouse.application.relationship_bulk_load import (
    InventoryError,
    agent_coverage_by_document_type,
    build_frozen_candidate_manifest,
    expected_quarters,
    index_floor_coverage_start,
    resolve_coverage_policy,
)


def fetch_quarter_indexes(
    *,
    coverage_start: date,
    watermark: date,
    get_filings=edgar.get_filings,
) -> dict[str, list[dict[str, object]]]:
    """Fetch every required SEC quarterly index, failing closed on any gap."""
    result: dict[str, list[dict[str, object]]] = {}
    for key in expected_quarters(coverage_start, watermark):
        year, quarter = int(key[:4]), int(key[-1])
        try:
            filings = get_filings(year=year, quarter=quarter)
            if filings is None:
                raise RuntimeError("SEC returned no index")
            rows = filings.to_pandas().to_dict(orient="records")
        except Exception as exc:
            raise InventoryError(f"failed to fetch required SEC index {key}") from exc
        if not rows:
            raise InventoryError(f"required SEC index {key} is empty")
        result[key] = rows
    return result


def _fetch_dicts(conn: duckdb.DuckDBPyConnection, sql: str, parameters: list[object]) -> list[dict]:
    cursor = conn.execute(sql, parameters)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _load_silver_inputs(
    silver_db: str,
    *,
    coverage_start: date,
    watermark: date,
    tracking_status_filter: str,
) -> tuple[set[int], dict[int, str], list[dict[str, object]]]:
    conn = duckdb.connect(silver_db, read_only=True)
    try:
        statuses = [value.strip() for value in tracking_status_filter.split(",") if value.strip()]
        if not statuses or "all" in statuses:
            cik_rows = _fetch_dicts(
                conn,
                "SELECT cik, last_main_sha256 FROM sec_company_sync_state ORDER BY cik",
                [],
            )
        else:
            placeholders = ",".join("?" for _ in statuses)
            cik_rows = _fetch_dicts(
                conn,
                f"SELECT cik, last_main_sha256 FROM sec_company_sync_state "
                f"WHERE tracking_status IN ({placeholders}) ORDER BY cik",
                statuses,
            )
        release_ciks = {int(row["cik"]) for row in cik_rows}
        source_manifest_fingerprints = {
            int(row["cik"]): str(row["last_main_sha256"])
            for row in cik_rows
            if row.get("last_main_sha256")
        }
        if not release_ciks:
            raise InventoryError("frozen silver contains no release CIKs")
        filings = _fetch_dicts(
            conn,
            """
            SELECT accession_number, cik, form, filing_date, report_date, items
            FROM sec_company_filing
            WHERE filing_date BETWEEN ? AND ?
              AND form IN ('DEF 14A', 'DEF 14A/A', 'DEFA14A', 'PRE 14A', '8-K', '8-K/A')
            ORDER BY accession_number
            """,
            [coverage_start, watermark],
        )
        return release_ciks, source_manifest_fingerprints, filings
    finally:
        conn.close()


def _write_text(path: str, payload: str) -> None:
    if path.startswith("s3://"):
        import fsspec

        with fsspec.open(path, "wt", encoding="utf-8") as handle:
            handle.write(payload)
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--silver-db", required=True, help="Local frozen production silver DuckDB")
    parser.add_argument("--output-path", required=True, help="Local or S3 candidate manifest path")
    parser.add_argument(
        "--batches-output-path", required=True,
        help="Local or S3 JSONL path for strict Distributed Map CIK batches",
    )
    parser.add_argument(
        "--coverage-start",
        type=date.fromisoformat,
        default=None,
        help=(
            "Optional uniform index/window start. When omitted, uses locked agent "
            "lookbacks (13F 3y/XML floor, proxy 5y, Item 5.02 8-K 2y) and sets "
            "coverage_start to the min-of-types index floor."
        ),
    )
    parser.add_argument(
        "--uniform-coverage",
        action="store_true",
        help=(
            "When set with --coverage-start, apply that start uniformly to all form "
            "families (legacy). Default is per-form agent lookbacks."
        ),
    )
    parser.add_argument("--watermark", type=date.fromisoformat, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--tracking-status-filter", default="all")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.uniform_coverage:
            if args.coverage_start is None:
                raise InventoryError("--uniform-coverage requires --coverage-start")
            coverage_start = args.coverage_start
            coverage_by_document_type = None
        elif args.coverage_start is not None:
            # Explicit start without --uniform-coverage: still agent windows, but
            # operators may pass a floor override only if it matches min(starts).
            windows = agent_coverage_by_document_type(args.watermark)
            floor = index_floor_coverage_start(windows)
            if args.coverage_start != floor:
                raise InventoryError(
                    f"--coverage-start {args.coverage_start.isoformat()} does not match "
                    f"agent index floor {floor.isoformat()}; omit the flag or pass "
                    f"--uniform-coverage for a single global start"
                )
            coverage_start = floor
            coverage_by_document_type = windows
        else:
            coverage_start, coverage_by_document_type = resolve_coverage_policy(
                args.watermark
            )

        release_ciks, source_manifest_fingerprints, silver_filings = _load_silver_inputs(
            args.silver_db,
            coverage_start=coverage_start,
            watermark=args.watermark,
            tracking_status_filter=args.tracking_status_filter,
        )
        quarter_indexes = fetch_quarter_indexes(
            coverage_start=coverage_start,
            watermark=args.watermark,
        )
        manifest = build_frozen_candidate_manifest(
            quarter_indexes,
            silver_filings=silver_filings,
            release_ciks=release_ciks,
            source_manifest_fingerprints=source_manifest_fingerprints,
            coverage_start=coverage_start,
            coverage_by_document_type=coverage_by_document_type,
            watermark=args.watermark,
            batch_size=args.batch_size,
        )
        manifest["release_cik_count"] = len(release_ciks)
        _write_text(args.output_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        batch_lines = "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in manifest["cik_batches"]
        )
        _write_text(args.batches_output_path, batch_lines)
    except (OSError, ValueError, duckdb.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "candidate_manifest": args.output_path,
        "candidate_batches": args.batches_output_path,
        "candidate_count": manifest["candidate_count"],
        "candidate_cik_count": manifest["candidate_cik_count"],
        "fingerprint": manifest["fingerprint"],
        "coverage_start": manifest["coverage_start"],
        "coverage_by_document_type": manifest.get("coverage_by_document_type"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
