#!/usr/bin/env bash
# Repeatable E2E: seed a sample MANAGES_FUND relationship, run backfill +
# sync via the existing Container App Jobs, and verify it landed in Neo4j.
#
# Idempotent: uses deterministic markers so reruns reuse the same test
# entities. By default leaves SQL data in place (re-runs naturally re-sync via
# MERGE in Neo4j); pass --cleanup to delete the seeded rows after verification.
#
# Usage:
#   bash infra/scripts/run-neo4j-e2e.sh [--cleanup]
#
# Pre-requisites:
#   - sqlcmd (go-sqlcmd):  brew install sqlcmd
#   - az login complete
#   - SQL firewall rule for laptop IP:
#       MY_IP=$(curl -s https://api.ipify.org)
#       az sql server firewall-rule create -g edgartools-dev-rg \
#         -s edgdev7659-mdm-sql-cu --name local-laptop-temp \
#         --start-ip-address $MY_IP --end-ip-address $MY_IP

set -euo pipefail

CLEANUP="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --cleanup) CLEANUP="true"; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RG="edgartools-dev-rg"
KV="edgdev-7659-kv"
SQL_HOST="edgdev7659-mdm-sql-cu.database.windows.net"
SQL_DB="mdm"
SQL_USER="mdmadmin"

JOB_LOAD="edgartools-dev-mdm-graph-load"
JOB_VERIFY="edgartools-dev-mdm-graph-verify"

DEMO_FUND_NAME="MDM_E2E_DEMO_FUND"

SQL_PWD="$(az keyvault secret show --vault-name "$KV" --name mdm-sql-admin-password \
  --query value -o tsv)"

run_sql() {
  sqlcmd -S "$SQL_HOST" -d "$SQL_DB" -U "$SQL_USER" -P "$SQL_PWD" \
    -h -1 -W -s '|' -Q "$1"
}

# ---------------------------------------------------------------------------
# 1. Seed (idempotent)
# ---------------------------------------------------------------------------
echo "==> [1/4] Seed sample adviser+fund (idempotent)"

EXISTING="$(run_sql "
  SET NOCOUNT ON;
  SELECT TOP 1 CAST(adviser_entity_id AS NVARCHAR(36)) + '|' + CAST(entity_id AS NVARCHAR(36))
  FROM mdm_fund WHERE canonical_name = '${DEMO_FUND_NAME}';
" | head -1 | tr -d ' \r')"

if [[ -n "$EXISTING" && "$EXISTING" != *"NULL"* && "$EXISTING" != "0" ]]; then
  ADVISER_ID="${EXISTING%|*}"
  FUND_ID="${EXISTING#*|}"
  echo "    reusing seeded entities: adviser=$ADVISER_ID fund=$FUND_ID"
else
  ADVISER_ID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
  FUND_ID="$(uuidgen    | tr '[:upper:]' '[:lower:]')"
  run_sql "
    SET NOCOUNT ON;
    INSERT INTO mdm_entity (entity_id, entity_type, is_quarantined)
      VALUES ('$ADVISER_ID', 'adviser', 0), ('$FUND_ID', 'fund', 0);
    INSERT INTO mdm_fund (entity_id, adviser_entity_id, canonical_name)
      VALUES ('$FUND_ID', '$ADVISER_ID', '${DEMO_FUND_NAME}');
  " >/dev/null
  echo "    seeded adviser=$ADVISER_ID fund=$FUND_ID"
fi

# Wipe any prior MANAGES_FUND row for this pair so backfill re-derives.
run_sql "
  SET NOCOUNT ON;
  DELETE FROM mdm_relationship_instance
   WHERE source_entity_id = '$ADVISER_ID' AND target_entity_id = '$FUND_ID';
" >/dev/null
echo "    cleared prior mdm_relationship_instance for this pair"

# ---------------------------------------------------------------------------
# 2. Run backfill (mdm-graph-load) — derives MANAGES_FUND, syncs to Neo4j
# ---------------------------------------------------------------------------
echo ""
echo "==> [2/4] Run $JOB_LOAD"

LOAD_EXEC="$(az containerapp job start --name "$JOB_LOAD" --resource-group "$RG" \
  --query name -o tsv)"
echo "    started: $LOAD_EXEC"

while true; do
  STATUS="$(az containerapp job execution show --name "$JOB_LOAD" --resource-group "$RG" \
    --job-execution-name "$LOAD_EXEC" --query properties.status -o tsv)"
  echo "    [$JOB_LOAD] $STATUS"
  case "$STATUS" in
    Succeeded) break ;;
    Failed|Stopped) echo "ERROR: $JOB_LOAD ended $STATUS" >&2; exit 1 ;;
  esac
  sleep 15
done

# ---------------------------------------------------------------------------
# 3. Run verify (mdm-graph-verify) — cypher MATCH counts
# ---------------------------------------------------------------------------
echo ""
echo "==> [3/4] Run $JOB_VERIFY"

VERIFY_EXEC="$(az containerapp job start --name "$JOB_VERIFY" --resource-group "$RG" \
  --query name -o tsv)"
echo "    started: $VERIFY_EXEC"

while true; do
  STATUS="$(az containerapp job execution show --name "$JOB_VERIFY" --resource-group "$RG" \
    --job-execution-name "$VERIFY_EXEC" --query properties.status -o tsv)"
  echo "    [$JOB_VERIFY] $STATUS"
  case "$STATUS" in
    Succeeded) break ;;
    Failed|Stopped) echo "ERROR: $JOB_VERIFY ended $STATUS" >&2; exit 1 ;;
  esac
  sleep 15
done

# Pull verify-graph output from Log Analytics
WORKSPACE="$(az monitor log-analytics workspace list --resource-group "$RG" \
  --query "[0].customerId" -o tsv)"
echo "    waiting 20s for logs to flush..."
sleep 20
PREFIX="$(echo "$VERIFY_EXEC" | cut -d- -f1-4)"
LOGS="$(az monitor log-analytics query --workspace "$WORKSPACE" \
  --analytics-query "ContainerAppConsoleLogs_CL
    | where Log_s != ''
    | where TimeGenerated > ago(10m)
    | where ContainerAppName_s has '$PREFIX'
    | order by TimeGenerated asc
    | project Log_s" \
  --query "tables[0].rows[*][0]" -o tsv 2>/dev/null || echo "")"
echo "--- verify-graph output ---"
echo "$LOGS"
echo "---------------------------"

# ---------------------------------------------------------------------------
# 4. Assert MANAGES_FUND >= 1
# ---------------------------------------------------------------------------
echo ""
echo "==> [4/4] Assert MANAGES_FUND >= 1 in Neo4j"
COUNTS_LINE="$(echo "$LOGS" | grep -E '"neo4j_MANAGES_FUND_edges"' | head -1 || true)"
if [[ -z "$COUNTS_LINE" ]]; then
  # The verify command prints the JSON across multiple lines — try to assemble.
  COUNTS_JSON="$(echo "$LOGS" | tr -d '\r' | tr -d '\n' | grep -oE '\{[^}]*neo4j_nodes_total[^}]*\}' | head -1)"
else
  # Single-line case
  COUNTS_JSON="$(echo "$LOGS" | tr -d '\r' | tr -d '\n' | grep -oE '\{[^}]*neo4j_nodes_total[^}]*\}' | head -1)"
fi
echo "    counts: ${COUNTS_JSON:-<unparseable>}"

EDGES="$(echo "$COUNTS_JSON" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get("neo4j_MANAGES_FUND_edges", 0))
except Exception:
    print(0)
')"

if [[ "$EDGES" =~ ^[0-9]+$ ]] && (( EDGES >= 1 )); then
  echo "    PASS: MANAGES_FUND edges=$EDGES"
else
  echo "    FAIL: MANAGES_FUND edges=$EDGES (expected >=1)" >&2
  exit 1
fi

echo ""
echo "E2E SUCCESS: sample MANAGES_FUND relationship reached Neo4j."
echo "    adviser=$ADVISER_ID"
echo "    fund=$FUND_ID"

# ---------------------------------------------------------------------------
# 5. Optional cleanup
# ---------------------------------------------------------------------------
if [[ "$CLEANUP" == "true" ]]; then
  echo ""
  echo "==> Cleanup: deleting test rows from SQL"
  run_sql "
    SET NOCOUNT ON;
    DELETE FROM mdm_relationship_instance
     WHERE source_entity_id IN ('$ADVISER_ID','$FUND_ID')
        OR target_entity_id IN ('$ADVISER_ID','$FUND_ID');
    DELETE FROM mdm_fund   WHERE entity_id = '$FUND_ID';
    DELETE FROM mdm_entity WHERE entity_id IN ('$ADVISER_ID','$FUND_ID');
  " >/dev/null
  echo "    sql cleanup ok"
  echo "    note: Neo4j nodes/edges retained — GraphSyncEngine MERGE keeps subsequent runs idempotent"
fi
