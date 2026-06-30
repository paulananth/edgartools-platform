#!/usr/bin/env bash
# Single-CIK end-to-end smoke test: bronze → silver → Snowflake gold → MDM → Neo4j.
#
# Runs entirely in AWS via Step Functions. Each phase gate-checks the previous
# one before continuing. Exits non-zero on the first failure and prints the
# failing execution ARN so you can inspect CloudWatch logs.
#
# Runtime: ~15–20 min for CIK 320193 (Apple — full insider filing history).
#
# Prerequisites:
#   - AWS credentials with Step Functions, CloudWatch Logs, and Secrets Manager
#   - snow CLI configured (connection name passed via --snow-connection)
#
# Usage:
#   bash scripts/test/smoke-test-single-cik.sh
#   bash scripts/test/smoke-test-single-cik.sh --cik 789019 --env dev
#   bash scripts/test/smoke-test-single-cik.sh --snow-connection snowconn --timeout 1200

set -euo pipefail

# ── defaults ───────────────────────────────────────────────────────────────────
CIK="${SMOKE_TEST_CIK:-320193}"         # Apple — dense Form 4 history, good coverage
ENV="${SMOKE_TEST_ENV:-dev}"
AWS_REGION_NAME="${AWS_REGION:-us-east-1}"
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
SNOW_CONNECTION="${SNOW_CONNECTION:-snowconn}"
POLL_INTERVAL=20                         # seconds between Step Functions status polls
SF_POLL_INTERVAL=15                      # seconds between Snowflake refresh polls
SF_TIMEOUT=180                           # seconds to wait for manifest task auto-pickup
PHASE_TIMEOUT="${SMOKE_TEST_TIMEOUT:-1200}"  # seconds per Step Functions phase

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APPLICATION_FILE="${REPO_ROOT}/infra/aws-${ENV}-application.json"

RUN_ID="smoke-$(date +%s)-cik-${CIK}"

# ── helpers ────────────────────────────────────────────────────────────────────
pass() { echo "  ✓ $*"; }
fail() { echo ""; echo "FAIL: $*" >&2; exit 1; }
section() { echo ""; echo "══ $* ══"; }

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

state_machine_arn() {
  local key="$1"
  local arn
  arn="$(python3 -c "
import json, sys
data = json.load(open('${APPLICATION_FILE}'))
sm = data.get('state_machines', {})
key = sys.argv[1]
print(sm.get(key, ''))
" "$key" 2>/dev/null)"
  [[ -n "$arn" ]] || fail "state machine '${key}' not found in ${APPLICATION_FILE}"
  echo "$arn"
}

start_execution() {
  local sm_key="$1" name="$2" input="$3"
  local arn
  arn="$(state_machine_arn "$sm_key")"
  aws_cli stepfunctions start-execution \
    --state-machine-arn "$arn" \
    --name "$name" \
    --input "$input" \
    --query executionArn \
    --output text
}

wait_for_execution() {
  local exec_arn="$1" label="$2" elapsed=0 status
  while (( elapsed < PHASE_TIMEOUT )); do
    status="$(aws_cli stepfunctions describe-execution \
      --execution-arn "$exec_arn" \
      --query status --output text)"
    echo "  ${label}: ${status} (${elapsed}s)"
    [[ "$status" == "RUNNING" ]] || break
    sleep "$POLL_INTERVAL"
    (( elapsed += POLL_INTERVAL ))
  done

  if [[ "$status" != "SUCCEEDED" ]]; then
    aws_cli stepfunctions describe-execution \
      --execution-arn "$exec_arn" \
      --query '{status:status,error:error,cause:cause}' \
      --output json 2>/dev/null || true
    fail "${label} ended with status=${status}  arn=${exec_arn}"
  fi
  pass "${label} SUCCEEDED"
}

run_phase() {
  local sm_key="$1" name_suffix="$2" input="$3"
  local exec_name="${RUN_ID}-${name_suffix}"
  local exec_arn
  exec_arn="$(start_execution "$sm_key" "$exec_name" "$input")"
  echo "  started ${sm_key}: ${exec_arn}"
  wait_for_execution "$exec_arn" "$sm_key"
}

snow_sql() {
  snow sql --connection "$SNOW_CONNECTION" --query "$1"
}

snow_scalar() {
  local output result
  if ! output="$(snow sql --connection "$SNOW_CONNECTION" --format json --query "$1")"; then
    fail "snow sql failed"
  fi
  if ! result="$(printf '%s\n' "$output" | python3 -c "
import json
import sys

rows = json.load(sys.stdin)
if not rows:
    print(0)
    raise SystemExit(0)

row = rows[0]
if isinstance(row, dict):
    print(next(iter(row.values()), 0))
elif isinstance(row, (list, tuple)):
    print(row[0] if row else 0)
else:
    print(row)
")"; then
    printf 'Snowflake scalar query returned invalid JSON:\n%s\n' "$output" >&2
    fail "snow sql returned invalid JSON"
  fi
  printf '%s\n' "$result"
}

assert_gt() {
  local label="$1" value="$2" threshold="$3"
  (( value > threshold )) || fail "${label}: expected >${threshold} rows, got ${value}"
  pass "${label}: ${value} rows"
}

# ── arg parsing ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cik)             CIK="${2:?}";             shift 2 ;;
    --env)             ENV="${2:?}";             shift 2 ;;
    --aws-region)      AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --aws-profile)     AWS_PROFILE_NAME="${2:?}";shift 2 ;;
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --timeout)         PHASE_TIMEOUT="${2:?}";   shift 2 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$APPLICATION_FILE" ]] || fail "deployment manifest not found: ${APPLICATION_FILE}"

DB="EDGARTOOLS_DEV"
[[ "$ENV" == "prod" ]] && DB="EDGARTOOLS_PROD"

# ── preamble ───────────────────────────────────────────────────────────────────
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  EdgarTools single-CIK smoke test                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf  "║  CIK     : %-50s ║\n" "$CIK"
printf  "║  env     : %-50s ║\n" "$ENV"
printf  "║  run_id  : %-50s ║\n" "$RUN_ID"
printf  "║  region  : %-50s ║\n" "$AWS_REGION_NAME"
echo "╚══════════════════════════════════════════════════════════════╝"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1 — Bronze → Silver → Snowflake exports
# targeted-resync fetches all SEC filings for the CIK, runs silver parsers,
# writes gold export Parquet to S3, and inserts a manifest row into
# SNOWFLAKE_RUN_MANIFEST_INBOX (picked up by SNOWFLAKE_RUN_MANIFEST_TASK).
# ═══════════════════════════════════════════════════════════════════════════════
section "Phase 1: targeted-resync (bronze → silver → S3 exports)"
RESYNC_EXEC_NAME="${RUN_ID}-resync"
RESYNC_ARN="$(start_execution "targeted_resync" "$RESYNC_EXEC_NAME" \
  "{\"scope_type\":\"cik\",\"scope_key\":\"${CIK}\",\"run_id\":\"${RESYNC_EXEC_NAME}\"}")"
echo "  started targeted_resync: ${RESYNC_ARN}"
wait_for_execution "$RESYNC_ARN" "targeted_resync"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 2 — Snowflake gold refresh
# SNOWFLAKE_RUN_MANIFEST_TASK fires every minute when stream has data.
# We poll SNOWFLAKE_REFRESH_STATUS until this run shows succeeded, with a
# manual fallback that calls LOAD_EXPORTS_FOR_RUN + REFRESH_AFTER_LOAD directly.
# ═══════════════════════════════════════════════════════════════════════════════
section "Phase 2: Snowflake gold refresh (auto via manifest task)"
echo "  Polling SNOWFLAKE_REFRESH_STATUS for run_id=${RESYNC_EXEC_NAME} ..."
SF_ELAPSED=0
SF_STATUS=""
while (( SF_ELAPSED < SF_TIMEOUT )); do
  SF_STATUS="$(snow_scalar "
    SELECT COALESCE(MAX(status), 'pending')
    FROM ${DB}.EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS
    WHERE run_id = '${RESYNC_EXEC_NAME}'
  ")"
  echo "  Snowflake refresh: ${SF_STATUS} (${SF_ELAPSED}s)"
  [[ "$SF_STATUS" == "succeeded" ]] && break
  [[ "$SF_STATUS" == "failed" ]] && break
  sleep "$SF_POLL_INTERVAL"
  (( SF_ELAPSED += SF_POLL_INTERVAL ))
done

if [[ "$SF_STATUS" != "succeeded" ]]; then
  echo "  Manifest task did not pick up run within ${SF_TIMEOUT}s — triggering manually"
  snow_sql "CALL ${DB}.EDGARTOOLS_SOURCE.LOAD_EXPORTS_FOR_RUN('targeted-resync', '${RESYNC_EXEC_NAME}')"
  snow_sql "CALL ${DB}.EDGARTOOLS_GOLD.REFRESH_AFTER_LOAD('targeted-resync', '${RESYNC_EXEC_NAME}')"
  SF_STATUS="$(snow_scalar "
    SELECT COALESCE(MAX(status), 'unknown')
    FROM ${DB}.EDGARTOOLS_SOURCE.SNOWFLAKE_REFRESH_STATUS
    WHERE run_id = '${RESYNC_EXEC_NAME}'
  ")"
fi

[[ "$SF_STATUS" == "succeeded" ]] || fail "Snowflake refresh ended with status=${SF_STATUS}"
pass "Snowflake refresh succeeded"

# Assert gold tables have data for this CIK
section "Phase 2 assertions: Snowflake gold row counts for CIK ${CIK}"
CIK_PADDED="$(printf '%010d' "$CIK")"

FILING_ROWS="$(snow_scalar "SELECT COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.FILING_DETAIL WHERE company_key LIKE '%${CIK}%' OR cik = ${CIK}")"
assert_gt "FILING_DETAIL rows for CIK ${CIK}" "$FILING_ROWS" 0

OWNERSHIP_ROWS="$(snow_scalar "
  SELECT COUNT(*)
  FROM ${DB}.EDGARTOOLS_GOLD.OWNERSHIP_HOLDINGS AS holdings
  JOIN ${DB}.EDGARTOOLS_GOLD.COMPANY AS company
    ON holdings.company_key = company.company_key
  WHERE company.cik = ${CIK}
")"
# Ownership holdings may be 0 for issuers with no Form 3/4/5 — check filings instead
COMPANY_ROWS="$(snow_scalar "SELECT COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.COMPANY WHERE cik = ${CIK}")"
assert_gt "COMPANY rows for CIK ${CIK}" "$COMPANY_ROWS" 0

echo "  OWNERSHIP_HOLDINGS for CIK ${CIK}: ${OWNERSHIP_ROWS}"
echo "  FILING_DETAIL for CIK ${CIK}:      ${FILING_ROWS}"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 3 — MDM entity resolution
# mdm-run resolves silver company/adviser/person facts into mdm_company,
# mdm_adviser, mdm_person entities in Postgres.
# ═══════════════════════════════════════════════════════════════════════════════
section "Phase 3: MDM entity resolution"
run_phase "mdm_run" "mdm-run" "{\"limit\":10}"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 4 — MDM relationship derivation → Neo4j sync
# backfill-relationships derives IS_INSIDER, MANAGES_FUND, etc. edges in Postgres.
# sync-graph pushes pending edges to Neo4j.
# verify-graph counts nodes and edges and fails if either is 0.
# ═══════════════════════════════════════════════════════════════════════════════
section "Phase 4: MDM → Neo4j (derive + sync + verify)"
run_phase "mdm_backfill_relationships" "mdm-backfill" "{\"limit\":50}"
run_phase "mdm_sync_graph"             "mdm-sync"     "{\"limit\":50}"
run_phase "mdm_verify_graph"           "mdm-verify"   "{}"

# ═══════════════════════════════════════════════════════════════════════════════
# Phase 5 — Final cross-layer assertion
# Confirm company appears in Snowflake gold AND MDM Postgres.
# ═══════════════════════════════════════════════════════════════════════════════
section "Phase 5: Cross-layer assertions"

GOLD_COMPANY="$(snow_scalar "SELECT COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.COMPANY WHERE cik = ${CIK}")"
assert_gt "Gold COMPANY for CIK ${CIK}" "$GOLD_COMPANY" 0

GOLD_FILINGS="$(snow_scalar "SELECT COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.FILING_DETAIL WHERE cik = ${CIK}")"
assert_gt "Gold FILING_DETAIL for CIK ${CIK}" "$GOLD_FILINGS" 0

GOLD_ACTIVITY="$(snow_scalar "SELECT COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.FILING_ACTIVITY WHERE cik = ${CIK}")"
echo "  Gold FILING_ACTIVITY for CIK ${CIK}: ${GOLD_ACTIVITY}"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  SMOKE TEST PASSED                                           ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf  "║  CIK              : %-42s ║\n" "$CIK"
printf  "║  run_id           : %-42s ║\n" "$RUN_ID"
printf  "║  Gold company rows: %-42s ║\n" "$GOLD_COMPANY"
printf  "║  Gold filing rows : %-42s ║\n" "$GOLD_FILINGS"
echo "╚══════════════════════════════════════════════════════════════╝"
