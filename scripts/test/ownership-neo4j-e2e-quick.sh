#!/usr/bin/env bash
# Quick two-phase e2e: Form 4 → Snowflake gold AND MDM entities → Neo4j IS_INSIDER.
# Runtime: ~15 min for 5 CIKs.
#
# Prerequisites:
#   - AWS credentials with Step Functions + ECS permissions
#   - SnowCLI installed with a configured connection
#
# Usage:
#   SNOW_CONNECTION=snowconn bash scripts/test/ownership-neo4j-e2e-quick.sh

set -euo pipefail

REGION="us-east-1"
ACCOUNT_ID="077127448006"
NAME_PREFIX="edgartools-dev"
SNOW_CONNECTION="${SNOW_CONNECTION:-snowconn}"
DB="EDGARTOOLS_DEV"

SM_RESYNC="${NAME_PREFIX}-targeted-resync"
SM_MDM_RUN="${NAME_PREFIX}-mdm-run"
SM_MDM_BACKFILL="${NAME_PREFIX}-mdm-backfill-relationships"
SM_MDM_SYNC="${NAME_PREFIX}-mdm-sync-graph"
SM_MDM_VERIFY="${NAME_PREFIX}-mdm-verify-graph"

# Well-known Form 4 filers — insiders file against these companies
CIKS=(320193 789019 1318605 1045810 1326801)   # AAPL MSFT TSLA NVDA META
PREFIX="quick-e2e-$(date +%s)"
MDM_LIMIT=5

wait_for_execution() {
  local arn="$1"
  local label="$2"
  while true; do
    STATUS=$(aws stepfunctions describe-execution \
      --execution-arn "$arn" --query 'status' --output text)
    echo "  $label: $STATUS"
    [[ "$STATUS" == "RUNNING" ]] || break
    sleep 20
  done
  [[ "$STATUS" == "SUCCEEDED" ]] || { echo "FAILED: $label ($STATUS)"; exit 1; }
}

start_execution() {
  local sm="$1"
  local name="$2"
  local input="$3"
  aws stepfunctions start-execution \
    --state-machine-arn "arn:aws:states:${REGION}:${ACCOUNT_ID}:stateMachine:${sm}" \
    --name "$name" \
    --input "$input" \
    --query 'executionArn' --output text
}

# ── Phase 1: Form 4 parsing → Snowflake gold (parallel, ~5 min) ──────────────
echo "=== Phase 1: targeted-resync for ${#CIKS[@]} CIKs in parallel ==="

EXEC_ARNS=()
EXEC_NAMES=()
for CIK in "${CIKS[@]}"; do
  NAME="${PREFIX}-cik-${CIK}"
  ARN=$(start_execution "$SM_RESYNC" "$NAME" \
    "{\"scope_type\":\"cik\",\"scope_key\":\"${CIK}\"}")
  EXEC_ARNS+=("$ARN")
  EXEC_NAMES+=("$NAME")
  echo "  Started $NAME"
done

echo "Waiting for targeted-resync executions..."
for i in "${!EXEC_ARNS[@]}"; do
  wait_for_execution "${EXEC_ARNS[$i]}" "${EXEC_NAMES[$i]}"
done

echo "Loading exports into Snowflake source tables..."
for NAME in "${EXEC_NAMES[@]}"; do
  snow sql --connection "$SNOW_CONNECTION" --query \
    "CALL ${DB}.EDGARTOOLS_SOURCE.LOAD_EXPORTS_FOR_RUN('targeted-resync', '${NAME}')"
done

echo "Refreshing gold ownership tables..."
for TABLE in OWNERSHIP_ACTIVITY OWNERSHIP_HOLDINGS FILING_DETAIL FILING_ACTIVITY; do
  snow sql --connection "$SNOW_CONNECTION" --query \
    "ALTER DYNAMIC TABLE ${DB}.EDGARTOOLS_GOLD.${TABLE} REFRESH"
done

echo "Snowflake gold counts:"
snow sql --connection "$SNOW_CONNECTION" --query "
SELECT 'COMPANY'             AS tbl, COUNT(*) AS rows FROM ${DB}.EDGARTOOLS_GOLD.COMPANY
UNION ALL SELECT 'OWNERSHIP_ACTIVITY', COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY
UNION ALL SELECT 'OWNERSHIP_HOLDINGS', COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.OWNERSHIP_HOLDINGS
UNION ALL SELECT 'FILING_DETAIL'      , COUNT(*) FROM ${DB}.EDGARTOOLS_GOLD.FILING_DETAIL
ORDER BY 1"

# ── Phase 2: MDM entity resolution → Neo4j IS_INSIDER (sequential, ~10 min) ──
echo ""
echo "=== Phase 2: MDM entity resolution + Neo4j sync (limit=${MDM_LIMIT}) ==="

MDM_RUN_ARN=$(start_execution "$SM_MDM_RUN" "${PREFIX}-mdm-run" \
  "{\"limit\":${MDM_LIMIT}}")
wait_for_execution "$MDM_RUN_ARN" "mdm-run"

MDM_BACKFILL_ARN=$(start_execution "$SM_MDM_BACKFILL" "${PREFIX}-mdm-backfill" \
  "{\"limit\":${MDM_LIMIT}}")
wait_for_execution "$MDM_BACKFILL_ARN" "mdm-backfill-relationships"

MDM_SYNC_ARN=$(start_execution "$SM_MDM_SYNC" "${PREFIX}-mdm-sync" "{}")
wait_for_execution "$MDM_SYNC_ARN" "mdm-sync-graph"

MDM_VERIFY_ARN=$(start_execution "$SM_MDM_VERIFY" "${PREFIX}-mdm-verify" "{}")
wait_for_execution "$MDM_VERIFY_ARN" "mdm-verify-graph"

echo ""
echo "Done. Check mdm-verify-graph CloudWatch logs for IS_INSIDER edge counts."
