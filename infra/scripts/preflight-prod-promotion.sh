#!/usr/bin/env bash
# Read-only gate for promoting the former production-shaped environment to prod.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SECRETS_MANIFEST_JSON_PATH="${SCRIPT_DIR}/secrets-manifest.json"

usage() {
  cat <<'EOF'
Usage: preflight-prod-promotion.sh [options]
  --aws-profile <name>       Default: aws-admin-prod
  --aws-account-id <id>      Expected 12-digit AWS account ID. Required.
  --aws-region <region>      Must be us-east-1
  --snow-connection <name>   Default: edgartools-prod
  --source-bucket <name>     Legacy environment bucket to compare (optional)
  --expected-source-count N  Require this many source objects

Post-cutover invariant check (the prodb->prod promotion completed 2026-07-19):
canonical prod resources must exist, and no legacy EDGARTOOLS_PRODB Snowflake
resources may remain. This command performs only STS, S3 list/head, Secrets
Manager describe, ECR describe, and Snowflake SHOW queries. It never writes
or applies changes.
EOF
}

AWS_PROFILE_NAME="aws-admin-prod"
AWS_REGION_NAME="us-east-1"
SNOW_CONNECTION="edgartools-prod"
SOURCE_BUCKET=""
EXPECTED_SOURCE_COUNT=""
ACCOUNT_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-account-id) ACCOUNT_ID="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --source-bucket) SOURCE_BUCKET="${2:?}"; shift 2 ;;
    --expected-source-count) EXPECTED_SOURCE_COUNT="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || { echo "ERROR: --aws-account-id must be a 12-digit AWS account ID" >&2; exit 2; }

failures=0
pass() { printf 'PASS: %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; failures=$((failures + 1)); }
aws_read() { aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"; }

[[ "$AWS_REGION_NAME" == "us-east-1" ]] || fail "canonical production region is us-east-1"
actual_account="$(aws_read sts get-caller-identity --query Account --output text 2>/dev/null || true)"
[[ "$actual_account" == "$ACCOUNT_ID" ]] && pass "canonical AWS account selected" || fail "wrong AWS account (expected ${ACCOUNT_ID})"

targets=(
  "edgartools-prod-bronze-${ACCOUNT_ID}"
  "edgartools-prod-warehouse-${ACCOUNT_ID}"
  "edgartools-prod-snowflake-export-${ACCOUNT_ID}"
)
for bucket in "${targets[@]}"; do
  if aws_read s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    pass "canonical bucket exists: ${bucket}"
  else
    fail "canonical bucket missing: ${bucket}"
  fi
done

# edgar-identity uses a separate legacy hyphenated naming convention and is
# deliberately not in secrets-manifest.json (see the manifest's own
# top-level $comment) -- checked here on its own, not from the manifest loop.
aws_read secretsmanager describe-secret --secret-id edgartools-prod-edgar-identity >/dev/null 2>&1 \
  && pass "secret container exists: edgartools-prod-edgar-identity" \
  || fail "missing secret container: edgartools-prod-edgar-identity"

# Every secret this platform depends on, per secrets-manifest.json (Ticket 5
# of the credential-isolation breakdown) -- previously a hardcoded list of
# 2, which is exactly how the dbt/snowflake gap this manifest exists to
# document went uncaught pre-promotion. describe-secret only (metadata),
# never get-secret-value -- no secret value is ever read by this check.
[[ -f "$SECRETS_MANIFEST_JSON_PATH" ]] || fail "secrets manifest not found at ${SECRETS_MANIFEST_JSON_PATH}"
if [[ -f "$SECRETS_MANIFEST_JSON_PATH" ]]; then
  while IFS=$'\t' read -r manifest_name populated_in_prod; do
    secret_id="edgartools-prod/${manifest_name}"
    # Check the command's own exit status, not output emptiness -- a
    # successful describe-secret with a genuinely empty body (as this
    # script's own test fakes, and possibly some real edge case) must still
    # count as "exists," matching the pre-existing check's own >/dev/null
    # 2>&1 && ... || ... pattern for every other AWS check in this file.
    if describe_json="$(aws_read secretsmanager describe-secret --secret-id "$secret_id" 2>/dev/null)"; then
      pass "secret container exists: ${secret_id}"
    else
      fail "missing secret container: ${secret_id}"
      continue
    fi
    if [[ "$populated_in_prod" == "true" ]]; then
      # VersionIdsToStages is part of describe-secret's own response (still
      # metadata, not a value) -- empty/absent means the container exists
      # but has never actually been written to, exactly the shape of the
      # gap this check exists to catch.
      has_version="$(jq -r '(.VersionIdsToStages // {}) | length > 0' <<<"$describe_json" 2>/dev/null || echo false)"
      if [[ "$has_version" == "true" ]]; then
        pass "secret has a value: ${secret_id}"
      else
        fail "secret container exists but has never been populated: ${secret_id}"
      fi
    fi
  done < <(jq -r '.secrets[] | [.name, (.populated_in_prod | tostring)] | @tsv' "$SECRETS_MANIFEST_JSON_PATH")
fi

for repository in edgartools-prod-warehouse edgartools-prod-mdm; do
  aws_read ecr describe-images --repository-name "$repository" --filter tagStatus=TAGGED --max-items 1 >/dev/null 2>&1 \
    && pass "tagged image available: ${repository}" \
    || fail "no tagged image available: ${repository}"
done

if [[ -n "$SOURCE_BUCKET" ]]; then
  # NOTE: with --output text the CLI emits the JMESPath result PER PAGE (one
  # line per 1000 keys), so page counts must be summed client-side.
  count_objects() {
    aws_read s3api list-objects-v2 --bucket "$1" --prefix "$2" \
      --query 'length(Contents || `[]`)' --output text 2>/dev/null \
      | awk '{s+=$1} END {if (NR>0) print s+0}'
  }
  # Same prefix on both sides — the migration copy preserves keys exactly,
  # so an asymmetric prefix (warehouse/ vs warehouse/bronze/) undercounts the
  # target by any non-bronze keys (e.g. warehouse/release-evidence/) that
  # were legitimately copied.
  source_count="$(count_objects "$SOURCE_BUCKET" warehouse/ || true)"
  target_count="$(count_objects "edgartools-prod-bronze-${ACCOUNT_ID}" warehouse/ || true)"
  [[ "$source_count" =~ ^[0-9]+$ ]] || { fail "unable to count source objects"; source_count=""; }
  [[ "$target_count" =~ ^[0-9]+$ ]] || { fail "unable to count target objects"; target_count=""; }
  if [[ -n "$source_count" && -n "$target_count" ]]; then
    if [[ -n "$EXPECTED_SOURCE_COUNT" ]]; then
      [[ "$source_count" == "$EXPECTED_SOURCE_COUNT" ]] || fail "source count ${source_count} does not equal expected ${EXPECTED_SOURCE_COUNT}"
    fi
    [[ "$source_count" == "$target_count" ]] && pass "source and target object counts match (${source_count})" || fail "copy incomplete: source=${source_count}, target=${target_count}"
  fi
fi

# Single statements per invocation (multi-statement output is not reliably
# parseable across snow CLI versions), CSV format (snow supports only
# TABLE/JSON/JSON_EXT/CSV — TSV has never been valid), and empty output
# fails closed — an empty result must never satisfy the "no PRODB
# remnants" check.
snow_rows=""
snow_ok=true
for stmt in \
  "SHOW DATABASES LIKE 'EDGARTOOLS_PROD%'" \
  "SHOW WAREHOUSES LIKE 'EDGARTOOLS_PROD%'" \
  "SHOW INTEGRATIONS LIKE 'EDGARTOOLS_PROD%'"; do
  rows="$(snow sql --connection "$SNOW_CONNECTION" --format CSV -q "$stmt" 2>/dev/null || true)"
  [[ -n "$rows" ]] || { [[ "$stmt" == *DATABASES* ]] && snow_ok=false; }
  snow_rows+="$rows"$'\n'
done
if [[ "$snow_ok" != true ]]; then
  fail "Snowflake inventory query returned no databases (connection failure or empty account) — cannot verify"
elif grep -q 'EDGARTOOLS_PRODB' <<<"$snow_rows"; then
  fail "legacy EDGARTOOLS_PRODB resources still present (decommission incomplete)"
else
  pass "no legacy EDGARTOOLS_PRODB resources remain"
fi
if grep -Eq '(^|[[:space:]"'"'"',])EDGARTOOLS_PROD([[:space:]"'"'"',]|$)' <<<"$snow_rows"; then
  pass "canonical Snowflake database exists"
else
  fail "canonical Snowflake database is missing"
fi

if (( failures > 0 )); then
  printf 'Preflight failed with %d blocking finding(s). No changes were made.\n' "$failures" >&2
  exit 1
fi
echo "Preflight passed. No changes were made."
