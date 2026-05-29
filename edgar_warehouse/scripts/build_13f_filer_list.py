"""Build the 13F institutional manager CIK list for Branch B bootstrap.

Downloads SEC EDGAR quarterly full-index files to collect every distinct CIK
that filed a 13F-HR form in the target year range, then writes the result as a
flat JSON list of integer CIKs.

Target: ~5,500 distinct institutional managers from the full SEC 13F filer list.

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
import csv
import gzip
import io
import json
import logging
import sys
import time
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# SEC quarterly full-index URL pattern
# Each file has columns: company name | form type | CIK | date filed | filename
_INDEX_URL = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/company.gz"

_QUARTERS = (1, 2, 3, 4)

# Throttle between index downloads to stay within SEC rate limits (10 req/s)
_INTER_REQUEST_DELAY_S = 0.15


def _fetch_gz(url: str, *, retries: int = 3) -> bytes:
    """Download a gzip file, returning raw bytes."""
    import urllib.request

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "edgar-warehouse/1.0 contact@edgartools.io"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as exc:
            if attempt == retries:
                raise
            delay = 2 ** attempt
            log.warning("Fetch attempt %d/%d failed for %s (%s); retrying in %ds…",
                        attempt, retries, url, exc, delay)
            time.sleep(delay)
    return b""  # unreachable


def _iter_13f_ciks_from_index(raw_gz: bytes) -> Iterator[int]:
    """Parse company.gz full-index and yield CIKs for 13F-HR filers."""
    with gzip.open(io.BytesIO(raw_gz), "rt", encoding="latin-1") as f:
        # First 9 lines are a header block (skip until the dashed separator)
        for line in f:
            if line.startswith("---"):
                break
        # Remaining lines are pipe-separated: company|form|CIK|date|filename
        reader = csv.reader(f, delimiter="|")
        for row in reader:
            if len(row) < 4:
                continue
            form_type = row[1].strip()
            if form_type.startswith("13F-HR"):
                try:
                    yield int(row[2].strip())
                except ValueError:
                    pass


def collect_13f_ciks(start_year: int, end_year: int) -> list[int]:
    """Return sorted unique CIKs that filed 13F-HR in [start_year, end_year]."""
    seen: set[int] = set()

    for year in range(start_year, end_year + 1):
        for quarter in _QUARTERS:
            url = _INDEX_URL.format(year=year, quarter=quarter)
            log.info("Fetching %s…", url)
            try:
                raw = _fetch_gz(url)
            except Exception as exc:
                log.error("Failed to fetch %s: %s — skipping quarter", url, exc)
                time.sleep(_INTER_REQUEST_DELAY_S)
                continue

            count_before = len(seen)
            for cik in _iter_13f_ciks_from_index(raw):
                seen.add(cik)
            new_this_quarter = len(seen) - count_before
            log.info(
                "  %d Q%d: %d new 13F-HR filers (running total: %d)",
                year, quarter, new_this_quarter, len(seen),
            )
            time.sleep(_INTER_REQUEST_DELAY_S)

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
