#!/usr/bin/env bash
# Sibling of cleanup-s3-staging.sh (ADR 0004). Default is dry-run.
# Selects billed warehouse duplicates: noncurrent Canonical Silver, aged
# identity-refresh run dirs, and gold run_id= copies outside the keep-set.
# Never deletes current Canonical Silver keys.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  reclaim-warehouse-duplicates.sh [options]

Default is a dry run that writes a local TSV and summary. No S3 deletes.

Options:
  --aws-profile <profile>          AWS CLI profile (default: AWS_PROFILE).
  --aws-region <region>            AWS region (default: AWS_REGION, AWS_DEFAULT_REGION, or us-east-1).
  --output-dir <path>              Local evidence root.
  --manifest <path>                Reviewed candidate-versions.tsv; required with --apply.
  --apply                          Delete the exact versions in this run's manifest.
  --confirm-delete-duplicates      Required together with --apply.
  -h, --help                       Show this help.

Target bucket is edgartools-prod-warehouse-<account-id>.
USAGE
}

fail() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "==> $*" >&2; }

AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
OUTPUT_ROOT=""
APPLY=false
CONFIRM_DELETE=false
MANIFEST_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile) AWS_PROFILE_NAME="${2:?--aws-profile requires a value}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?--aws-region requires a value}"; shift 2 ;;
    --output-dir) OUTPUT_ROOT="${2:?--output-dir requires a value}"; shift 2 ;;
    --manifest) MANIFEST_PATH="${2:?--manifest requires a value}"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    --confirm-delete-duplicates) CONFIRM_DELETE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; fail "unknown argument: $1" ;;
  esac
done

if [[ "$APPLY" == true && "$CONFIRM_DELETE" != true ]]; then
  fail "--apply requires --confirm-delete-duplicates"
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

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
run_reclaim() {
  (cd "$REPO_ROOT" && uv run python -m edgar_warehouse.infrastructure.warehouse_duplicate_reclaim "$@")
}

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "AWS returned an invalid account ID"
BUCKET="edgartools-prod-warehouse-${ACCOUNT_ID}"
EVIDENCE_PREFIX="warehouse/release-evidence/warehouse-duplicate-reclaim"

aws_cli s3api head-bucket --bucket "$BUCKET" >/dev/null || fail "verified target bucket is unavailable: $BUCKET"

OUTPUT_ROOT="${OUTPUT_ROOT:-${REPO_ROOT}/infra/.warehouse-duplicate-reclaim-evidence}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-${ACCOUNT_ID}"
RUN_DIR="${OUTPUT_ROOT%/}/${RUN_ID}"
mkdir -p "$RUN_DIR/listings" "$RUN_DIR/delete-results"

CANDIDATES="$RUN_DIR/candidate-versions.tsv"
SUMMARY="$RUN_DIR/summary.json"
MODE="dry-run"
[[ "$APPLY" == true ]] && MODE="apply"

log "Target: s3://${BUCKET}"
log "Mode: ${MODE}"
log "Local evidence: $RUN_DIR"

PREFIXES=(
  "warehouse/silver/sec/shards/"
  "warehouse/silver/sec/silver.duckdb"
  "warehouse/identity_refresh/"
  "warehouse/gold/"
)
LISTING_FILES=()
index=0
for prefix in "${PREFIXES[@]}"; do
  index=$((index + 1))
  listing="$RUN_DIR/listings/listing-${index}.json"
  log "Listing versions under ${prefix}"
  aws_cli s3api list-object-versions \
    --bucket "$BUCKET" \
    --prefix "$prefix" \
    --output json > "$listing"
  LISTING_FILES+=("$listing")
done

if [[ "$APPLY" != true ]]; then
  run_reclaim merge-select \
    "$CANDIDATES" "$SUMMARY" \
    --account-id "$ACCOUNT_ID" \
    --bucket "$BUCKET" \
    --run-id "$RUN_ID" \
    --mode "$MODE" \
    "${LISTING_FILES[@]}"
  SELECTED_COUNT="$(uv run --no-project python -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected_object_versions"])' "$SUMMARY")"
  SELECTED_GIB="$(uv run --no-project python -c 'import json,sys; print(json.load(open(sys.argv[1]))["selected_gib"])' "$SUMMARY")"
  log "Selected ${SELECTED_COUNT} object versions (${SELECTED_GIB} GiB)"
  log "Dry run complete. No S3 objects were deleted."
  log "Review: $SUMMARY and $CANDIDATES"
  log "To delete this reviewed selection, rerun with --apply --confirm-delete-duplicates --manifest $CANDIDATES."
  exit 0
fi

[[ -f "$MANIFEST_PATH" ]] || fail "manifest does not exist: $MANIFEST_PATH"
DELETE_MANIFEST="$RUN_DIR/reviewed-candidate-versions.tsv"
run_reclaim validate-manifest "$MANIFEST_PATH" "$DELETE_MANIFEST"
(cd "$REPO_ROOT" && uv run python - "$DELETE_MANIFEST" "$SUMMARY" "$ACCOUNT_ID" "$BUCKET" "$RUN_ID" <<'PY'
from edgar_warehouse.infrastructure.warehouse_duplicate_reclaim import read_tsv, write_summary
import sys
write_summary(
    sys.argv[2],
    rows=read_tsv(sys.argv[1]),
    mode="apply",
    account_id=sys.argv[3],
    bucket=sys.argv[4],
    run_id=sys.argv[5],
)
PY
)
SELECTED_COUNT="$(awk 'END {print (NR>0)?NR-1:0}' "$DELETE_MANIFEST")"
SELECTED_BYTES="$(awk -F '\t' 'NR > 1 {sum += $4} END {printf "%.0f", sum+0}' "$DELETE_MANIFEST")"
SELECTED_GIB="$(awk -v bytes="$SELECTED_BYTES" 'BEGIN {printf "%.3f", bytes / 1024 / 1024 / 1024}')"
log "Reviewed manifest selected ${SELECTED_COUNT} object versions (${SELECTED_GIB} GiB)"

EVIDENCE_URI="s3://${BUCKET}/${EVIDENCE_PREFIX}/${RUN_ID}/"
log "Uploading pre-delete evidence to ${EVIDENCE_URI}"
aws_cli s3 cp "$SUMMARY" "${EVIDENCE_URI}summary.json" >/dev/null
aws_cli s3 cp "$DELETE_MANIFEST" "${EVIDENCE_URI}candidate-versions.tsv" >/dev/null

BATCH_DIR="$RUN_DIR/delete-batches"
run_reclaim write-batches "$DELETE_MANIFEST" "$BATCH_DIR"
if compgen -G "$BATCH_DIR/batch-*.json" >/dev/null; then
  log "Deleting exact selected VersionIds in batches of 100"
  for batch_file in "$BATCH_DIR"/batch-*.json; do
    batch_name="$(basename "$batch_file" .json)"
    aws_cli s3api delete-objects \
      --bucket "$BUCKET" \
      --delete "file://${batch_file}" \
      --output json > "$RUN_DIR/delete-results/${batch_name}.json"
  done
fi

POST_LISTING="$RUN_DIR/post-delete-versions.json"
POST_VALIDATION="$RUN_DIR/post-delete-validation.json"
POST_FILES=()
index=0
for prefix in "${PREFIXES[@]}"; do
  index=$((index + 1))
  listing="$RUN_DIR/listings/post-${index}.json"
  aws_cli s3api list-object-versions \
    --bucket "$BUCKET" \
    --prefix "$prefix" \
    --output json > "$listing"
  POST_FILES+=("$listing")
done
uv run --no-project python - "$POST_LISTING" "${POST_FILES[@]}" <<'PY'
import json, sys
from pathlib import Path
out = Path(sys.argv[1])
versions = []
markers = []
for path in sys.argv[2:]:
    payload = json.loads(Path(path).read_text(encoding="utf-8") or "{}")
    versions.extend(payload.get("Versions") or [])
    markers.extend(payload.get("DeleteMarkers") or [])
out.write_text(json.dumps({"Versions": versions, "DeleteMarkers": markers}) + "\n", encoding="utf-8")
PY
run_reclaim remaining "$DELETE_MANIFEST" "$POST_LISTING" "$POST_VALIDATION"

aws_cli s3 cp "$POST_VALIDATION" "${EVIDENCE_URI}post-delete-validation.json" >/dev/null
COMPLETE="$(uv run --no-project python -c 'import json,sys; print("true" if json.load(open(sys.argv[1]))["complete"] else "false")' "$POST_VALIDATION")"
if [[ "$COMPLETE" != true ]]; then
  echo "WARN: Reclaim was incomplete. Durable evidence: ${EVIDENCE_URI}" >&2
  exit 1
fi

log "Reclaim complete: ${SELECTED_COUNT} exact object versions deleted."
