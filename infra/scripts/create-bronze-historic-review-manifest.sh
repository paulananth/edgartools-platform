#!/usr/bin/env bash
# Create a read-only, version-aware review manifest for historical bronze
# filing artifacts. This tool never deletes data and its output is NOT a
# deletion authorization.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  create-bronze-historic-review-manifest.sh [options]

Builds a local review manifest for current bronze filing objects whose
accession year is older than the selected year. It makes only ListObjectVersions
requests; it never reads filing bodies, writes S3 objects, or deletes anything.

Options:
  --aws-profile <profile>       AWS CLI profile (default: AWS_PROFILE).
  --aws-region <region>         AWS region (default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1).
  --before-accession-year <n>   Candidate cutoff; select years before n (default: 2024).
  --output-dir <path>           Local output root (default: infra/.bronze-historic-review-manifests).
  --max-pages <n>               Limit the inventory for a test run; 0 means complete inventory (default: 0).
  -h, --help                    Show this help.

Every output row is REVIEW_REQUIRED_NOT_DELETE_AUTHORIZED. Before any later
deletion, it must be reconciled to the active release manifest, canonical
silver references, and feature-history requirements.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }

AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
BEFORE_ACCESSION_YEAR=2024
OUTPUT_ROOT=""
MAX_PAGES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile) AWS_PROFILE_NAME="${2:?--aws-profile requires a value}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?--aws-region requires a value}"; shift 2 ;;
    --before-accession-year) BEFORE_ACCESSION_YEAR="${2:?--before-accession-year requires a value}"; shift 2 ;;
    --output-dir) OUTPUT_ROOT="${2:?--output-dir requires a value}"; shift 2 ;;
    --max-pages) MAX_PAGES="${2:?--max-pages requires a value}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ "$BEFORE_ACCESSION_YEAR" =~ ^20[0-9]{2}$ ]] || fail "--before-accession-year must be a year from 2000 onward"
[[ "$MAX_PAGES" =~ ^[0-9]+$ ]] || fail "--max-pages must be zero or a positive whole number"
command -v aws >/dev/null 2>&1 || fail "AWS CLI is required"
command -v uv >/dev/null 2>&1 || fail "uv is required"

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "AWS returned an invalid account ID"
BUCKET="edgartools-prod-bronze-${ACCOUNT_ID}"
PREFIX="warehouse/bronze/filings/sec/"
aws_cli s3api head-bucket --bucket "$BUCKET" >/dev/null || fail "verified target bucket is unavailable: $BUCKET"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/infra/.bronze-historic-review-manifests}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${ACCOUNT_ID}"
RUN_DIR="${OUTPUT_ROOT%/}/${RUN_ID}"
mkdir -p "$RUN_DIR"
MANIFEST="$RUN_DIR/historic-review-manifest.tsv"
SUMMARY="$RUN_DIR/summary.json"

log "Target: s3://${BUCKET}/${PREFIX}"
log "Candidate rule: current filing object with accession year before ${BEFORE_ACCESSION_YEAR}"
[[ "$MAX_PAGES" != 0 ]] && log "TEST MODE: limiting inventory to ${MAX_PAGES} pages; output will be incomplete"
log "Local output: $RUN_DIR"

uv run --no-project --with boto3 python - \
  "$AWS_PROFILE_NAME" "$AWS_REGION_NAME" "$BUCKET" "$PREFIX" "$BEFORE_ACCESSION_YEAR" \
  "$MAX_PAGES" "$MANIFEST" "$SUMMARY" "$RUN_ID" <<'PY'
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import csv
import json
from pathlib import Path
import re
import sys

import boto3

profile, region, bucket, prefix, cutoff_text, max_pages_text, manifest_path, summary_path, run_id = sys.argv[1:]
cutoff = int(cutoff_text)
max_pages = int(max_pages_text)
session = boto3.Session(profile_name=profile or None, region_name=region)
client = session.client("s3")
accession_pattern = re.compile(r"/accession=(\d+-(\d{2})-\d+)/")
current_short_year = datetime.now(UTC).year % 100

manifest_rows: list[dict[str, object]] = []
pages = 0
all_current_objects = 0
all_current_bytes = 0
noncurrent_versions = 0
unparseable_current = 0
by_year: Counter[int] = Counter()
bytes_by_year: Counter[int] = Counter()
complete = True

for page in client.get_paginator("list_object_versions").paginate(
    Bucket=bucket,
    Prefix=prefix,
    PaginationConfig={"PageSize": 1000},
):
    pages += 1
    for version in page.get("Versions", []):
        if not version.get("IsLatest", False):
            noncurrent_versions += 1
            continue
        key = str(version.get("Key", ""))
        size = int(version.get("Size", 0))
        all_current_objects += 1
        all_current_bytes += size
        match = accession_pattern.search(key)
        if not match:
            unparseable_current += 1
            continue
        accession, short_year_text = match.groups()
        short_year = int(short_year_text)
        accession_year = 2000 + short_year if short_year <= current_short_year else 1900 + short_year
        by_year[accession_year] += 1
        bytes_by_year[accession_year] += size
        if accession_year >= cutoff:
            continue
        manifest_rows.append(
            {
                "key": key,
                "version_id": str(version["VersionId"]),
                "last_modified": str(version["LastModified"]),
                "size_bytes": size,
                "etag": str(version.get("ETag", "")),
                "accession": accession,
                "accession_year": accession_year,
                "selection_reason": f"accession_year_before_{cutoff}",
                "review_status": "REVIEW_REQUIRED_NOT_DELETE_AUTHORIZED",
            }
        )
    if pages % 25 == 0:
        print(f"progress pages={pages} current_objects={all_current_objects}", file=sys.stderr, flush=True)
    if max_pages and pages >= max_pages:
        complete = False
        break

manifest_rows.sort(key=lambda row: (str(row["key"]), str(row["version_id"])))
fieldnames = [
    "key", "version_id", "last_modified", "size_bytes", "etag", "accession",
    "accession_year", "selection_reason", "review_status",
]
with Path(manifest_path).open("w", newline="", encoding="utf-8") as output:
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t")
    writer.writeheader()
    writer.writerows(manifest_rows)

summary = {
    "run_id": run_id,
    "generated_at": datetime.now(UTC).isoformat(),
    "complete_inventory": complete,
    "account_id": session.client("sts").get_caller_identity()["Account"],
    "bucket": bucket,
    "eligible_prefix": prefix,
    "before_accession_year": cutoff,
    "current_filing_objects_scanned": all_current_objects,
    "current_filing_bytes_scanned": all_current_bytes,
    "candidate_review_versions": len(manifest_rows),
    "candidate_review_bytes": sum(int(row["size_bytes"]) for row in manifest_rows),
    "candidate_review_gib": round(sum(int(row["size_bytes"]) for row in manifest_rows) / 1024**3, 3),
    "noncurrent_versions_excluded": noncurrent_versions,
    "unparseable_current_objects_excluded": unparseable_current,
    "objects_by_accession_year": dict(sorted(by_year.items())),
    "bytes_by_accession_year": dict(sorted(bytes_by_year.items())),
    "authorization": "REVIEW_REQUIRED_NOT_DELETE_AUTHORIZED",
    "required_before_deletion": [
        "Reconcile every accession against the active release manifest.",
        "Reconcile every accession against canonical silver and required feature-history inputs.",
        "Approve an exact VersionId manifest in a separate deletion run.",
    ],
}
Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({
    "complete_inventory": complete,
    "current_filing_objects_scanned": all_current_objects,
    "candidate_review_versions": len(manifest_rows),
    "candidate_review_gib": summary["candidate_review_gib"],
    "manifest": manifest_path,
    "summary": summary_path,
}, sort_keys=True))
PY

log "Dry-run review manifest complete. It contains no deletion authorization."
log "Review manifest: $MANIFEST"
log "Summary: $SUMMARY"
