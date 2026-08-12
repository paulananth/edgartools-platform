#!/usr/bin/env bash
# One-time, version-aware cleanup of abandoned warehouse staging objects.
#
# Safety contract:
# - Scope is only s3://edgartools-prod-warehouse-<current-account>/warehouse/_staging/
# - The default is read-only and writes a local evidence bundle.
# - --apply requires --confirm-delete-staging and deletes only VersionIds in
#   that run's manifest. It never uses recursive deletion or delete markers.
# - Apply records pre/post evidence under warehouse/release-evidence/staging-cleanup/.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  cleanup-s3-staging.sh [options]

One-time cleanup of stale production warehouse staging objects. The default is
a dry run that creates a local evidence bundle but makes no AWS changes.

Options:
  --aws-profile <profile>       AWS CLI profile (default: AWS_PROFILE).
  --aws-region <region>         AWS region (default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1).
  --older-than-hours <hours>    Select staging object versions older than this age (default: 24).
  --output-dir <path>           Local evidence root (default: infra/.s3-staging-cleanup-evidence).
  --manifest <path>             Reviewed candidate-versions.tsv; required with --apply.
  --apply                       Delete the exact versions in this run's manifest.
  --confirm-delete-staging      Required together with --apply.
  -h, --help                    Show this help.

The target bucket is derived and verified from the authenticated account:
edgartools-prod-warehouse-<account-id>. Only warehouse/_staging/ is eligible.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }
warn() { echo "WARN: $*" >&2; }

AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
OLDER_THAN_HOURS=24
OUTPUT_ROOT=""
APPLY=false
CONFIRM_DELETE_STAGING=false
MANIFEST_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile) AWS_PROFILE_NAME="${2:?--aws-profile requires a value}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?--aws-region requires a value}"; shift 2 ;;
    --older-than-hours) OLDER_THAN_HOURS="${2:?--older-than-hours requires a value}"; shift 2 ;;
    --output-dir) OUTPUT_ROOT="${2:?--output-dir requires a value}"; shift 2 ;;
    --manifest) MANIFEST_PATH="${2:?--manifest requires a value}"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    --confirm-delete-staging) CONFIRM_DELETE_STAGING=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

[[ "$OLDER_THAN_HOURS" =~ ^[1-9][0-9]*$ ]] || fail "--older-than-hours must be a positive whole number"
if [[ "$APPLY" == true && "$CONFIRM_DELETE_STAGING" != true ]]; then
  fail "--apply requires --confirm-delete-staging"
fi
if [[ "$APPLY" == true && -z "$MANIFEST_PATH" ]]; then
  fail "--apply requires --manifest from a reviewed dry run"
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

run_python() {
  uv run --no-project python "$@"
}

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "AWS returned an invalid account ID"
BUCKET="edgartools-prod-warehouse-${ACCOUNT_ID}"
STAGING_PREFIX="warehouse/_staging/"
EVIDENCE_PREFIX="warehouse/release-evidence/staging-cleanup"

aws_cli s3api head-bucket --bucket "$BUCKET" >/dev/null || fail "verified target bucket is unavailable: $BUCKET"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/infra/.s3-staging-cleanup-evidence}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${ACCOUNT_ID}"
RUN_DIR="${OUTPUT_ROOT%/}/${RUN_ID}"
mkdir -p "$RUN_DIR/delete-results"

PRE_LISTING="$RUN_DIR/pre-delete-versions.json"
CANDIDATES="$RUN_DIR/candidate-versions.tsv"
SUMMARY="$RUN_DIR/summary.json"
ACTIVE_EXECUTIONS="$RUN_DIR/active-executions.tsv"

log "Target: s3://${BUCKET}/${STAGING_PREFIX}"
log "Mode: $([[ "$APPLY" == true ]] && echo apply || echo dry-run)"
log "Candidate age: older than ${OLDER_THAN_HOURS} hours"
log "Local evidence: $RUN_DIR"

# Active work is evidence only. This one-time cleanup intentionally does not
# block on it; VersionIds and the dedicated random staging prefix bound scope.
# A running ECS-task snapshot is a bounded, current workload signal. Record the
# state-machine inventory too, without serially polling every state machine.
{
  printf 'running_ecs_task_arns\n'
  aws_cli ecs list-tasks \
    --cluster edgartools-prod-warehouse \
    --desired-status RUNNING \
    --query 'taskArns[]' \
    --output text 2>/dev/null || true
  printf '\nstate_machine_arns\n'
  aws_cli stepfunctions list-state-machines \
    --query "stateMachines[?starts_with(name, 'edgartools-prod-')].stateMachineArn" \
    --output text 2>/dev/null | tr '\t' '\n' || true
} > "$ACTIVE_EXECUTIONS"

log "Capturing version inventory"
aws_cli s3api list-object-versions \
  --bucket "$BUCKET" \
  --prefix "$STAGING_PREFIX" \
  --output json > "$PRE_LISTING"

run_python - "$PRE_LISTING" "$CANDIDATES" "$SUMMARY" \
  "$ACCOUNT_ID" "$BUCKET" "$STAGING_PREFIX" "$OLDER_THAN_HOURS" "$RUN_ID" "$APPLY" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import csv
import json
from pathlib import Path
import sys

listing_path, candidates_path, summary_path, account_id, bucket, prefix, hours, run_id, apply = sys.argv[1:]
cutoff = datetime.now(UTC) - timedelta(hours=int(hours))
listing = json.loads(Path(listing_path).read_text(encoding="utf-8"))
candidates: list[dict[str, object]] = []
for version in listing.get("Versions", []):
    key = version.get("Key")
    version_id = version.get("VersionId")
    modified_text = version.get("LastModified")
    if not isinstance(key, str) or not key.startswith(prefix):
        continue
    if not isinstance(version_id, str) or not isinstance(modified_text, str):
        continue
    modified = datetime.fromisoformat(modified_text.replace("Z", "+00:00"))
    if modified >= cutoff:
        continue
    candidates.append(
        {
            "key": key,
            "version_id": version_id,
            "last_modified": modified.isoformat(),
            "size_bytes": int(version.get("Size", 0)),
            "is_latest": bool(version.get("IsLatest", False)),
            "etag": version.get("ETag", ""),
        }
    )

candidates.sort(key=lambda item: (str(item["key"]), str(item["version_id"])))
with Path(candidates_path).open("w", newline="", encoding="utf-8") as output:
    writer = csv.DictWriter(
        output,
        fieldnames=["key", "version_id", "last_modified", "size_bytes", "is_latest", "etag"],
        delimiter="\t",
    )
    writer.writeheader()
    writer.writerows(candidates)

summary = {
    "run_id": run_id,
    "generated_at": datetime.now(UTC).isoformat(),
    "mode": "apply" if apply == "true" else "dry-run",
    "account_id": account_id,
    "bucket": bucket,
    "eligible_prefix": prefix,
    "cutoff_utc": cutoff.isoformat(),
    "selected_object_versions": len(candidates),
    "selected_bytes": sum(int(item["size_bytes"]) for item in candidates),
    "selected_gib": round(sum(int(item["size_bytes"]) for item in candidates) / 1024**3, 3),
    "delete_markers_observed": len(listing.get("DeleteMarkers", [])),
    "selection_rule": "Only object versions under the eligible prefix whose LastModified is older than cutoff_utc.",
}
Path(summary_path).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

SELECTED_COUNT="$(awk -F ': ' '/"selected_object_versions"/ {gsub(/,/, "", $2); print $2}' "$SUMMARY")"
SELECTED_GIB="$(awk -F ': ' '/"selected_gib"/ {gsub(/,/, "", $2); print $2}' "$SUMMARY")"
log "Selected ${SELECTED_COUNT} object versions (${SELECTED_GIB} GiB)"

if [[ "$APPLY" != true ]]; then
  log "Dry run complete. No S3 objects or evidence were written."
  log "Review: $SUMMARY and $CANDIDATES"
  log "To delete this reviewed selection, rerun with --apply --confirm-delete-staging --manifest $CANDIDATES."
  exit 0
fi

[[ -f "$MANIFEST_PATH" ]] || fail "manifest does not exist: $MANIFEST_PATH"
DELETE_MANIFEST="$RUN_DIR/reviewed-candidate-versions.tsv"
run_python - "$MANIFEST_PATH" "$DELETE_MANIFEST" "$STAGING_PREFIX" <<'PY'
from __future__ import annotations

import csv
from pathlib import Path
import sys

source_path = Path(sys.argv[1])
destination_path = Path(sys.argv[2])
prefix = sys.argv[3]
required = {"key", "version_id", "last_modified", "size_bytes", "is_latest", "etag"}
with source_path.open(newline="", encoding="utf-8") as source:
    reader = csv.DictReader(source, delimiter="\t")
    if set(reader.fieldnames or []) != required:
        raise SystemExit("manifest has an unexpected header")
    rows = list(reader)
for row in rows:
    if not row["key"].startswith(prefix) or not row["version_id"]:
        raise SystemExit("manifest contains an object outside the staging scope or without a VersionId")
    int(row["size_bytes"])
with destination_path.open("w", newline="", encoding="utf-8") as destination:
    writer = csv.DictWriter(destination, fieldnames=reader.fieldnames, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
PY
SELECTED_COUNT="$(awk 'END {print NR - 1}' "$DELETE_MANIFEST")"
SELECTED_BYTES="$(awk -F '\t' 'NR > 1 {sum += $4} END {printf "%.0f", sum}' "$DELETE_MANIFEST")"
SELECTED_GIB="$(awk -v bytes="$SELECTED_BYTES" 'BEGIN {printf "%.3f", bytes / 1024 / 1024 / 1024}')"
log "Reviewed manifest selected ${SELECTED_COUNT} object versions (${SELECTED_GIB} GiB)"

EVIDENCE_URI="s3://${BUCKET}/${EVIDENCE_PREFIX}/${RUN_ID}/"
log "Uploading pre-delete evidence to ${EVIDENCE_URI}"
aws_cli s3 cp "$PRE_LISTING" "${EVIDENCE_URI}pre-delete-versions.json" >/dev/null
aws_cli s3 cp "$DELETE_MANIFEST" "${EVIDENCE_URI}candidate-versions.tsv" >/dev/null
aws_cli s3 cp "$SUMMARY" "${EVIDENCE_URI}summary.json" >/dev/null
aws_cli s3 cp "$ACTIVE_EXECUTIONS" "${EVIDENCE_URI}active-executions.tsv" >/dev/null

if [[ "$SELECTED_COUNT" -gt 0 ]]; then
  log "Deleting exact selected VersionIds in batches of 100"
  BATCH_DIR="$RUN_DIR/delete-batches"
  mkdir -p "$BATCH_DIR"
  run_python - "$DELETE_MANIFEST" "$BATCH_DIR" <<'PY'
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

manifest, output_dir = map(Path, sys.argv[1:])
with manifest.open(newline="", encoding="utf-8") as source:
    rows = list(csv.DictReader(source, delimiter="\t"))
for number, offset in enumerate(range(0, len(rows), 100), start=1):
    objects = [
        {"Key": row["key"], "VersionId": row["version_id"]}
        for row in rows[offset : offset + 100]
    ]
    (output_dir / f"batch-{number:04d}.json").write_text(
        json.dumps({"Objects": objects, "Quiet": False}, indent=2) + "\n",
        encoding="utf-8",
    )
PY
  for batch_file in "$BATCH_DIR"/*.json; do
    batch_name="$(basename "$batch_file" .json)"
    aws_cli s3api delete-objects \
      --bucket "$BUCKET" \
      --delete "file://${batch_file}" \
      --output json > "$RUN_DIR/delete-results/${batch_name}.json"
  done
fi

DELETE_REPORT="$RUN_DIR/delete-report.json"
run_python - "$RUN_DIR/delete-results" "$DELETE_REPORT" "$SELECTED_COUNT" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

result_dir, report_path, selected_count = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
deleted = []
errors = []
for result_path in sorted(result_dir.glob("*.json")):
    result = json.loads(result_path.read_text(encoding="utf-8"))
    deleted.extend(result.get("Deleted", []))
    errors.extend(result.get("Errors", []))
report_path.write_text(
    json.dumps(
        {
            "requested_versions": selected_count,
            "deleted_versions": len(deleted),
            "errors": errors,
            "error_count": len(errors),
            "complete": len(deleted) == selected_count and not errors,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PY

POST_LISTING="$RUN_DIR/post-delete-versions.json"
POST_VALIDATION="$RUN_DIR/post-delete-validation.json"
aws_cli s3api list-object-versions \
  --bucket "$BUCKET" \
  --prefix "$STAGING_PREFIX" \
  --output json > "$POST_LISTING"
run_python - "$DELETE_MANIFEST" "$POST_LISTING" "$POST_VALIDATION" <<'PY'
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

manifest_path, post_listing_path, output_path = map(Path, sys.argv[1:])
with manifest_path.open(newline="", encoding="utf-8") as source:
    selected = {(row["key"], row["version_id"]) for row in csv.DictReader(source, delimiter="\t")}
post_listing = json.loads(post_listing_path.read_text(encoding="utf-8"))
remaining = sorted(
    (item["Key"], item["VersionId"])
    for item in post_listing.get("Versions", [])
    if (item.get("Key"), item.get("VersionId")) in selected
)
output_path.write_text(
    json.dumps(
        {
            "selected_versions": len(selected),
            "selected_versions_still_present": len(remaining),
            "remaining": [{"key": key, "version_id": version_id} for key, version_id in remaining],
            "complete": not remaining,
        },
        indent=2,
        sort_keys=True,
    ) + "\n",
    encoding="utf-8",
)
PY

for evidence_file in "$DELETE_REPORT" "$POST_LISTING" "$POST_VALIDATION"; do
  aws_cli s3 cp "$evidence_file" "${EVIDENCE_URI}$(basename "$evidence_file")" >/dev/null
done
for result_file in "$RUN_DIR/delete-results"/*.json; do
  aws_cli s3 cp "$result_file" "${EVIDENCE_URI}delete-results/$(basename "$result_file")" >/dev/null
done

COMPLETE="$(run_python - "$DELETE_REPORT" "$POST_VALIDATION" <<'PY'
import json, sys
delete_report = json.load(open(sys.argv[1], encoding="utf-8"))
post_validation = json.load(open(sys.argv[2], encoding="utf-8"))
print("true" if delete_report["complete"] and post_validation["complete"] else "false")
PY
)"
if [[ "$COMPLETE" != true ]]; then
  warn "Cleanup was incomplete. Durable evidence: ${EVIDENCE_URI}"
  exit 1
fi

log "Cleanup complete: ${SELECTED_COUNT} exact object versions deleted."
log "Durable evidence: ${EVIDENCE_URI}"
