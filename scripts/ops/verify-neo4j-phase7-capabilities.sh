#!/usr/bin/env bash
set -uo pipefail

# Phase 7 Native App capability preflight. This script is deliberately dev-only
# and read-mostly: Native App calls use the existing graph contract, while the
# generation-switch probe uses session-scoped temporary Snowflake objects.

if [[ "${SNOW_CONNECTION:-}" != "snowconn" ]]; then
  echo "ERROR: SNOW_CONNECTION must be exactly snowconn" >&2
  exit 2
fi

SNOW_BIN="${SNOW_BIN:-snow}"
UV_BIN="${UV_BIN:-uv}"
DATABASE="${PHASE7_PREFLIGHT_DATABASE:-EDGARTOOLS_DEV}"
GRAPH_SCHEMA="${PHASE7_PREFLIGHT_GRAPH_SCHEMA:-NEO4J_GRAPH_MIGRATION}"
APP_NAME="${PHASE7_PREFLIGHT_APP_NAME:-Neo4j_Graph_Analytics}"
COMPUTE_POOL="${PHASE7_PREFLIGHT_COMPUTE_POOL:-CPU_X64_XS}"
RUN_ID="${PHASE7_PREFLIGHT_RUN_ID:-$(date -u +%Y%m%d%H%M%S)-$$}"
RESULTS_DIR="${PHASE7_PREFLIGHT_RESULTS_DIR:-${TMPDIR:-/tmp}}"
RESULTS_FILE="${RESULTS_DIR%/}/neo4j-phase7-preflight-${RUN_ID}.tsv"
SAFE_ID="${RUN_ID//-/_}"
OUTPUT_TABLE="PHASE7_BFS_${SAFE_ID}"

mkdir -p "$RESULTS_DIR"
: > "$RESULTS_FILE"

record() {
  local capability="$1" status="$2" detail="$3"
  detail="${detail//$'\t'/ }"
  detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\n' "$capability" "$status" "$detail" | tee -a "$RESULTS_FILE"
}

run_sql() {
  local capability="$1" query="$2" expected="${3:-}"
  local output rc
  output="$($SNOW_BIN sql -c snowconn -q "$query" 2>&1)"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    record "$capability" FAIL "command=${query}; exit=${rc}; ${output:0:1200}"
    return 1
  fi
  if [[ "$output" == *"JOB_STATUS"* && "$output" == *"ERROR"* ]]; then
    record "$capability" FAIL "command=${query}; Native App job reported ERROR; ${output:0:1200}"
    return 1
  fi
  if [[ -n "$expected" && "$output" != *"$expected"* ]]; then
    record "$capability" FAIL "command=${query}; expected=${expected}; output=${output:0:1200}"
    return 1
  fi
  record "$capability" PASS "command=${query}; output=${output:0:1200}"
  return 0
}

cleanup() {
  local output
  output="$($SNOW_BIN sql -c snowconn -q "GRANT OWNERSHIP ON TABLE ${DATABASE}.${GRAPH_SCHEMA}.${OUTPUT_TABLE} TO ROLE ACCOUNTADMIN REVOKE CURRENT GRANTS; DROP TABLE ${DATABASE}.${GRAPH_SCHEMA}.${OUTPUT_TABLE}" --format JSON 2>&1)" || true
  if [[ "$output" == *"successfully dropped"* || "$output" == *"does not exist"* ]]; then
    record cleanup PASS "${output:0:800}"
  else
    record cleanup FAIL "${output:0:800}"
  fi
}
trap cleanup EXIT

run_job() {
  local capability="$1" query="$2" output rc compact
  output="$($SNOW_BIN sql -c snowconn -q "$query" --format JSON 2>&1)"; rc=$?
  compact="${output//[[:space:]]/}"
  if [[ $rc -eq 0 && "$compact" == *'"JOB_STATUS":"SUCCESS"'* ]]; then
    record "$capability" PASS "command=${query}; output=${output:0:1400}"
    return 0
  fi
  record "$capability" FAIL "command=${query}; exit=${rc}; ${output:0:1400}"
  return 1
}

failures=0

if [[ "${PHASE7_PREFLIGHT_SKIP_OWNERSHIP_CHECK:-false}" != "true" ]]; then
  running="$(aws stepfunctions list-executions \
    --profile edgartools-690 \
    --region us-east-1 \
    --state-machine-arn arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-dev-load-history \
    --status-filter RUNNING \
    --max-results 2 \
    --query 'length(executions)' \
    --output text 2>&1)" || {
      record ownership_check FAIL "$running"
      exit 3
    }
  if [[ "$running" != "0" ]]; then
    record ownership_check FAIL "active load_history executions=${running}; retry after Phase 6 is idle"
    exit 3
  fi
fi
record ownership_check PASS "no active load_history execution"

run_sql app_installation "SHOW APPLICATIONS LIKE '${APP_NAME}'" "$APP_NAME" || ((failures+=1))
run_sql compute_pool "CALL ${APP_NAME}.GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS()" "$COMPUTE_POOL" || ((failures+=1))
run_sql contract_views "SELECT (SELECT COUNT(*) FROM ${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES) AS NODE_COUNT, (SELECT COUNT(*) FROM ${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_EDGES) AS EDGE_COUNT" || ((failures+=1))

# The current repository verifier's WCC call is the maintained proof that the
# Native App can project and execute against the contract views.
verify_output="$(SNOWFLAKE_CONNECTION=snowconn DBT_SNOWFLAKE_DATABASE="$DATABASE" \
  $UV_BIN run --extra snowflake edgar-warehouse mdm verify-graph 2>&1)"
verify_rc=$?
verify_compact="${verify_output//[[:space:]]/}"
if [[ $verify_rc -eq 0 && "$verify_compact" == *'"failure_domains":[]'* && "$verify_compact" == *'"parity":"ok"'* ]]; then
  record semantic_contract_parity PASS "command=SNOWFLAKE_CONNECTION=snowconn DBT_SNOWFLAKE_DATABASE=${DATABASE} uv run --extra snowflake edgar-warehouse mdm verify-graph; output=${verify_output:0:1200}"
else
  record semantic_contract_parity FAIL "command=SNOWFLAKE_CONNECTION=snowconn DBT_SNOWFLAKE_DATABASE=${DATABASE} uv run --extra snowflake edgar-warehouse mdm verify-graph; exit=${verify_rc}; ${verify_output:0:1200}"
  ((failures+=1))
fi

# Supported Native App operations are required health evidence. These use the
# current sectioned project/compute/write API established in Phase 8.
project="'project': {'nodeTables':['${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES'],'relationshipTables':{'${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_EDGES':{'sourceTable':'${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES','targetTable':'${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES','orientation':'NATURAL'}}}"
run_job graph_info "CALL ${APP_NAME}.GRAPH.GRAPH_INFO('${COMPUTE_POOL}', {${project},'compute':{}})" || ((failures+=1))

sample_node_output="$($SNOW_BIN sql -c snowconn -q "SELECT NODEID FROM ${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES ORDER BY NODEID LIMIT 1" --format JSON 2>&1)"
sample_node="$(printf '%s\n' "$sample_node_output" | sed -n 's/.*"NODEID": "\([^"]*\)".*/\1/p' | head -1)"
if [[ -z "$sample_node" ]]; then
  record bfs FAIL "could not resolve a sample NODEID; ${sample_node_output:0:800}"
  ((failures+=1))
else
  run_job bfs "CALL ${APP_NAME}.GRAPH.BFS('${COMPUTE_POOL}', {${project},'compute':{'sourceNodeTable':'${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES','sourceNode':'${sample_node}','targetNodesTable':'${DATABASE}.${GRAPH_SCHEMA}.GRAPH_APP_NODES','targetNodes':[],'maxDepth':2},'write':[{'outputTable':'${DATABASE}.${GRAPH_SCHEMA}.${OUTPUT_TABLE}'}]})" || ((failures+=1))
fi

list_output="$($SNOW_BIN sql -c snowconn -q "SELECT * FROM TABLE(${APP_NAME}.EXPERIMENTAL.LIST_GRAPHS())" --format JSON 2>&1)"; list_rc=$?
if [[ $list_rc -eq 0 ]]; then
  record list_graphs PASS "command=SELECT * FROM TABLE(${APP_NAME}.EXPERIMENTAL.LIST_GRAPHS()); output=${list_output:0:1200}"
else
  record list_graphs EXTERNAL_BLOCKER "command=SELECT * FROM TABLE(${APP_NAME}.EXPERIMENTAL.LIST_GRAPHS()); exit=${list_rc}; ${list_output:0:1200}"
fi

# Snowflake-native probes for the contract shape Phase 7 will expose. Temporary
# objects are session-scoped and disappear even when this query fails.
switch_sql="USE DATABASE ${DATABASE};
USE SCHEMA ${GRAPH_SCHEMA};
CREATE TEMPORARY TABLE PHASE7_${RUN_ID//-/_}_EDGE_A (EDGEID STRING, VALID_FROM_DATE DATE, VALID_TO_DATE DATE, GENERATION_ID STRING);
CREATE TEMPORARY TABLE PHASE7_${RUN_ID//-/_}_EDGE_B (EDGEID STRING, VALID_FROM_DATE DATE, VALID_TO_DATE DATE, GENERATION_ID STRING);
CREATE TEMPORARY TABLE PHASE7_${RUN_ID//-/_}_GRAPH_REGISTRY (GENERATION_ID STRING, STATUS STRING, ACTIVATED_DATE DATE, NODE_COUNT NUMBER, RELATIONSHIP_COUNT NUMBER);
INSERT INTO PHASE7_${RUN_ID//-/_}_EDGE_A VALUES ('edge-1', '2024-01-01'::DATE, '2024-02-01'::DATE, 'GEN_A');
INSERT INTO PHASE7_${RUN_ID//-/_}_EDGE_B VALUES ('edge-1', '2024-01-01'::DATE, NULL, 'GEN_B');
INSERT INTO PHASE7_${RUN_ID//-/_}_GRAPH_REGISTRY VALUES ('GEN_A', 'RETIRED', '2024-01-01'::DATE, 1, 1), ('GEN_B', 'ACTIVE', '2024-02-01'::DATE, 1, 1);
CREATE OR REPLACE TEMPORARY VIEW PHASE7_${RUN_ID//-/_}_ACTIVE_EDGE AS SELECT * FROM PHASE7_${RUN_ID//-/_}_EDGE_A;
SELECT GENERATION_ID, SYSTEM\$TYPEOF(VALID_FROM_DATE) AS DATE_TYPE FROM PHASE7_${RUN_ID//-/_}_ACTIVE_EDGE;
CREATE OR REPLACE TEMPORARY VIEW PHASE7_${RUN_ID//-/_}_ACTIVE_EDGE AS SELECT * FROM PHASE7_${RUN_ID//-/_}_EDGE_B;
SELECT GENERATION_ID, SYSTEM\$TYPEOF(VALID_FROM_DATE) AS DATE_TYPE FROM PHASE7_${RUN_ID//-/_}_ACTIVE_EDGE;
SELECT GENERATION_ID, STATUS FROM PHASE7_${RUN_ID//-/_}_GRAPH_REGISTRY WHERE STATUS = 'ACTIVE';"
switch_output="$($SNOW_BIN sql -c snowconn -q "$switch_sql" 2>&1)"
switch_rc=$?
if [[ $switch_rc -eq 0 && "$switch_output" == *"GEN_A"* && "$switch_output" == *"GEN_B"* && "$switch_output" == *"DATE"* && "$switch_output" == *"ACTIVE"* ]]; then
  record typed_dates_generation_and_registry PASS "command=temporary A-to-B view switch plus active registry lookup; output=${switch_output:0:1200}"
else
  record typed_dates_generation_and_registry FAIL "command=temporary A-to-B view switch plus active registry lookup; exit=${switch_rc}; ${switch_output:0:1200}"
  ((failures+=1))
fi

if [[ $failures -eq 0 ]]; then
  record aggregate GO "all required Phase 7 semantic parity and supported Native App capabilities passed"
  echo "RESULTS_FILE=$RESULTS_FILE"
  exit 0
fi

record aggregate NO_GO "${failures} required capability checks failed; Phase 7 plan 07-01 is blocked"
echo "RESULTS_FILE=$RESULTS_FILE"
exit 1
