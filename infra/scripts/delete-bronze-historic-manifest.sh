#!/usr/bin/env bash
# Delete only the exact historical bronze object versions approved in a complete
# review manifest. Never use this script with a partial inventory.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  delete-bronze-historic-manifest.sh --manifest <path> --summary <path> [options]

Validates a complete historical-bronze review manifest, then (only with the
explicit apply flags) deletes its exact S3 VersionIds in batches of 100.

Options:
  --manifest <path>                  Complete historic-review-manifest.tsv. Required.
  --summary <path>                   Matching summary.json. Required.
  --aws-profile <profile>             AWS CLI profile (default: AWS_PROFILE).
  --aws-region <region>               AWS region (default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1).
  --output-dir <path>                 Local evidence root (default: infra/.bronze-historic-delete-evidence).
  --run-id <id>                       Resume a prior local evidence run; default is a new UTC run ID.
  --max-parallel <1-10>               Concurrent exact-version delete requests (default: 1).
  --apply                             Perform deletion after validation.
  --confirm-delete-bronze-historic    Required together with --apply.
  -h, --help                          Show this help.

Without --apply this is a local validation-only dry run. Apply writes durable
evidence to the production warehouse release-evidence prefix before deleting.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }
warn() { echo "WARN: $*" >&2; }

MANIFEST_PATH=""
SUMMARY_PATH=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
OUTPUT_ROOT=""
REQUESTED_RUN_ID=""
MAX_PARALLEL=1
APPLY=false
CONFIRM_DELETE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST_PATH="${2:?--manifest requires a value}"; shift 2 ;;
    --summary) SUMMARY_PATH="${2:?--summary requires a value}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?--aws-profile requires a value}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?--aws-region requires a value}"; shift 2 ;;
    --output-dir) OUTPUT_ROOT="${2:?--output-dir requires a value}"; shift 2 ;;
    --run-id) REQUESTED_RUN_ID="${2:?--run-id requires a value}"; shift 2 ;;
    --max-parallel) MAX_PARALLEL="${2:?--max-parallel requires a value}"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    --confirm-delete-bronze-historic) CONFIRM_DELETE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ -n "$MANIFEST_PATH" ]] || fail "--manifest is required"
[[ -n "$SUMMARY_PATH" ]] || fail "--summary is required"
[[ -f "$MANIFEST_PATH" ]] || fail "manifest does not exist: $MANIFEST_PATH"
[[ -f "$SUMMARY_PATH" ]] || fail "summary does not exist: $SUMMARY_PATH"
[[ "$MAX_PARALLEL" =~ ^[1-9]$|^10$ ]] || fail "--max-parallel must be an integer from 1 through 10"
if [[ "$APPLY" == true && "$CONFIRM_DELETE" != true ]]; then
  fail "--apply requires --confirm-delete-bronze-historic"
fi
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
BRONZE_BUCKET="edgartools-prod-bronze-${ACCOUNT_ID}"
WAREHOUSE_BUCKET="edgartools-prod-warehouse-${ACCOUNT_ID}"
BRONZE_PREFIX="warehouse/bronze/filings/sec/"
EVIDENCE_PREFIX="warehouse/release-evidence/bronze-historic-cleanup"
aws_cli s3api head-bucket --bucket "$BRONZE_BUCKET" >/dev/null || fail "verified bronze bucket is unavailable: $BRONZE_BUCKET"
aws_cli s3api head-bucket --bucket "$WAREHOUSE_BUCKET" >/dev/null || fail "verified warehouse evidence bucket is unavailable: $WAREHOUSE_BUCKET"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/infra/.bronze-historic-delete-evidence}"
RUN_ID="${REQUESTED_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${ACCOUNT_ID}}"
RUN_DIR="${OUTPUT_ROOT%/}/${RUN_ID}"
mkdir -p "$RUN_DIR/delete-batches" "$RUN_DIR/delete-results"
VALIDATED_MANIFEST="$RUN_DIR/approved-versions.tsv"
VALIDATION="$RUN_DIR/validation.json"

uv run --no-project python - "$MANIFEST_PATH" "$SUMMARY_PATH" "$VALIDATED_MANIFEST" \
  "$VALIDATION" "$ACCOUNT_ID" "$BRONZE_BUCKET" "$BRONZE_PREFIX" <<'PY'
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

manifest_path = Path(sys.argv[1])
summary_path = Path(sys.argv[2])
approved_path = Path(sys.argv[3])
validation_path = Path(sys.argv[4])
account_id, bucket, prefix = sys.argv[5:]
summary = json.loads(summary_path.read_text(encoding="utf-8"))
if summary.get("complete_inventory") is not True:
    raise SystemExit("summary does not prove a complete inventory")
if summary.get("account_id") != account_id or summary.get("bucket") != bucket:
    raise SystemExit("summary account or bucket does not match the authenticated target")
if summary.get("eligible_prefix") != prefix:
    raise SystemExit("summary prefix is outside the bronze filing scope")
cutoff = int(summary.get("before_accession_year", 0))
if cutoff < 2000:
    raise SystemExit("summary has an invalid accession-year cutoff")
expected_headers = [
    "key", "version_id", "last_modified", "size_bytes", "etag", "accession",
    "accession_year", "selection_reason", "review_status",
]
with manifest_path.open(newline="", encoding="utf-8") as source:
    reader = csv.DictReader(source, delimiter="\t")
    if reader.fieldnames != expected_headers:
        raise SystemExit("manifest has an unexpected header")
    rows = list(reader)
for row in rows:
    if not row["key"].startswith(prefix):
        raise SystemExit("manifest contains a key outside the bronze filing scope")
    if not row["version_id"]:
        raise SystemExit("manifest contains an empty VersionId")
    if int(row["accession_year"]) >= cutoff:
        raise SystemExit("manifest includes an accession outside its historical cutoff")
    if row["review_status"] != "REVIEW_REQUIRED_NOT_DELETE_AUTHORIZED":
        raise SystemExit("manifest review status is not the expected reviewed state")
    int(row["size_bytes"])
total_bytes = sum(int(row["size_bytes"]) for row in rows)
if len(rows) != int(summary.get("candidate_review_versions", -1)):
    raise SystemExit("manifest row count does not match its complete summary")
if total_bytes != int(summary.get("candidate_review_bytes", -1)):
    raise SystemExit("manifest byte total does not match its complete summary")
with approved_path.open("w", newline="", encoding="utf-8") as destination:
    writer = csv.DictWriter(destination, fieldnames=reader.fieldnames, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
validation = {
    "account_id": account_id,
    "bronze_bucket": bucket,
    "eligible_prefix": prefix,
    "approved_versions": len(rows),
    "approved_bytes": total_bytes,
    "approved_gib": round(total_bytes / 1024**3, 3),
    "source_manifest": str(manifest_path),
    "source_summary": str(summary_path),
    "validation": "passed",
}
validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

APPROVED_COUNT="$(awk -F ': ' '/"approved_versions"/ {gsub(/,/, "", $2); print $2}' "$VALIDATION")"
APPROVED_GIB="$(awk -F ': ' '/"approved_gib"/ {gsub(/,/, "", $2); print $2}' "$VALIDATION")"
log "Validated ${APPROVED_COUNT} exact historical bronze versions (${APPROVED_GIB} GiB)"

if [[ "$APPLY" != true ]]; then
  log "Dry run complete. No S3 writes or deletes were performed."
  log "Validation: $VALIDATION"
  exit 0
fi

EVIDENCE_URI="s3://${WAREHOUSE_BUCKET}/${EVIDENCE_PREFIX}/${RUN_ID}/"
log "Uploading pre-delete evidence to ${EVIDENCE_URI}"
aws_cli s3 cp "$MANIFEST_PATH" "${EVIDENCE_URI}source-historic-review-manifest.tsv" >/dev/null
aws_cli s3 cp "$SUMMARY_PATH" "${EVIDENCE_URI}source-summary.json" >/dev/null
aws_cli s3 cp "$VALIDATED_MANIFEST" "${EVIDENCE_URI}approved-versions.tsv" >/dev/null
aws_cli s3 cp "$VALIDATION" "${EVIDENCE_URI}validation.json" >/dev/null

uv run --no-project python - "$VALIDATED_MANIFEST" "$RUN_DIR/delete-batches" <<'PY'
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

manifest_path, output_dir = map(Path, sys.argv[1:])
with manifest_path.open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source, delimiter="\t"))
for number, offset in enumerate(range(0, len(rows), 100), start=1):
    objects = [{"Key": row["key"], "VersionId": row["version_id"]} for row in rows[offset : offset + 100]]
    (output_dir / f"batch-{number:05d}.json").write_text(
        json.dumps({"Objects": objects, "Quiet": False}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
PY

has_complete_api_response() {
  local result_file="$1"
  [[ -s "$result_file" ]] && grep -Eq '"(Deleted|Errors)"[[:space:]]*:' "$result_file"
}

delete_batch() {
  local batch_file="$1"
  local batch_name result_file temporary_file
  batch_name="$(basename "$batch_file" .json)"
  result_file="$RUN_DIR/delete-results/${batch_name}.json"
  has_complete_api_response "$result_file" && return 0
  temporary_file="${result_file}.tmp.$$"
  aws_cli s3api delete-objects --bucket "$BRONZE_BUCKET" --delete "file://${batch_file}" --output json \
    > "$temporary_file"
  mv "$temporary_file" "$result_file"
}

completed_batches=0
for completed_result in "$RUN_DIR"/delete-results/batch-*.json; do
  has_complete_api_response "$completed_result" && completed_batches=$((completed_batches + 1))
done
total_batches="$(find "$RUN_DIR/delete-batches" -maxdepth 1 -type f -name 'batch-*.json' | wc -l | tr -d ' ')"
log "Delete batches: ${completed_batches}/${total_batches} already have successful API responses; concurrency=${MAX_PARALLEL}"

export AWS_PROFILE_NAME AWS_REGION_NAME BRONZE_BUCKET RUN_DIR
export -f aws_cli has_complete_api_response delete_batch
find "$RUN_DIR/delete-batches" -maxdepth 1 -type f -name 'batch-*.json' -print0 | \
  xargs -0 -n 1 -P "$MAX_PARALLEL" bash -c 'delete_batch "$1"' _

DELETE_REPORT="$RUN_DIR/delete-report.json"
uv run --no-project python - "$RUN_DIR/delete-results" "$DELETE_REPORT" "$APPROVED_COUNT" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

results_dir, report_path, expected_count = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
deleted: list[object] = []
errors: list[object] = []
for result_path in sorted(results_dir.glob("*.json")):
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    deleted.extend(payload.get("Deleted", []))
    errors.extend(payload.get("Errors", []))
report_path.write_text(
    json.dumps(
        {
            "requested_versions": expected_count,
            "deleted_versions": len(deleted),
            "error_count": len(errors),
            "errors": errors,
            "complete": len(deleted) == expected_count and not errors,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PY
aws_cli s3 cp "$DELETE_REPORT" "${EVIDENCE_URI}delete-report.json" >/dev/null

COMPLETE="$(uv run --no-project python - "$DELETE_REPORT" <<'PY'
import json
import sys
print("true" if json.load(open(sys.argv[1], encoding="utf-8"))["complete"] else "false")
PY
)"
if [[ "$COMPLETE" != true ]]; then
  warn "Deletion was incomplete. Durable evidence: ${EVIDENCE_URI}"
  exit 1
fi

log "Deletion complete: ${APPROVED_COUNT} exact versions deleted."
log "Durable evidence: ${EVIDENCE_URI}"
