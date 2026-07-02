"""Build the 13F institutional manager CIK list for Branch B bootstrap.

Uses edgartools' quarterly filing index (edgar.get_filings) to collect every
distinct CIK that filed a 13F-HR form in the target year range, then writes
the result as a flat JSON list of integer CIKs.

Usage:
  python -m edgar_warehouse.scripts.build_13f_filer_list \\
      --output-path /tmp/13f_filer_ciks.json \\
      --start-year 2020 --end-year 2024
  # or S3:
  python -m edgar_warehouse.scripts.build_13f_filer_list \\
      --output-path s3://my-bucket/reference/cohorts/thirteenf_ciks.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import edgar

log = logging.getLogger(__name__)

_QUARTERS = (1, 2, 3, 4)


def collect_13f_ciks(start_year: int, end_year: int, *, get_filings=edgar.get_filings) -> list[int]:
    """Return sorted unique CIKs that filed 13F-HR in [start_year, end_year].

    form="13F-HR" matches both "13F-HR" and "13F-HR/A" (amendments) -- same
    coverage as the previous raw full-index startswith("13F-HR") filter,
    confirmed against a live quarter before this change landed.
    """
    seen: set[int] = set()

    for year in range(start_year, end_year + 1):
        for quarter in _QUARTERS:
            log.info("Fetching %d Q%d 13F-HR filings…", year, quarter)
            try:
                filings = get_filings(year=year, quarter=quarter, form="13F-HR")
            except Exception as exc:
                log.error("Failed to fetch %d Q%d: %s — skipping quarter", year, quarter, exc)
                continue

            count_before = len(seen)
            if filings is not None:
                for cik in filings.to_pandas()["cik"]:
                    seen.add(int(cik))
            new_this_quarter = len(seen) - count_before
            log.info(
                "  %d Q%d: %d new 13F-HR filers (running total: %d)",
                year, quarter, new_this_quarter, len(seen),
            )

    result = sorted(seen)
    log.info("Collected %d distinct 13F-HR filer CIKs (%d–%d)", len(result), start_year, end_year)
    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_json(data: list[int], path_str: str) -> None:
    if path_str.startswith("s3://"):
        _write_s3_json(data, path_str)
    else:
        dest = Path(path_str)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, indent=2))
        log.info("Wrote %d CIKs to %s", len(data), dest)


def _write_s3_json(data: list[int], s3_uri: str) -> None:
    import boto3

    without_proto = s3_uri[5:]
    bucket, _, key = without_proto.partition("/")
    body = json.dumps(data, indent=2).encode()
    boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")
    log.info("Uploaded %d CIKs to %s", len(data), s3_uri)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Build 13F institutional filer CIK list from SEC quarterly index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-path",
        required=True,
        metavar="PATH",
        help="Local file path or S3 URI for the output JSON file",
    )
    parser.add_argument(
        "--start-year", type=int, default=2020,
        help="First year to include in scan (default: 2020)",
    )
    parser.add_argument(
        "--end-year", type=int, default=2024,
        help="Last year to include in scan (default: 2024)",
    )
    args = parser.parse_args(argv)

    if args.start_year > args.end_year:
        parser.error(f"--start-year ({args.start_year}) must be <= --end-year ({args.end_year})")

    ciks = collect_13f_ciks(args.start_year, args.end_year)
    _write_json(ciks, args.output_path)


if __name__ == "__main__":
    _main(sys.argv[1:])
