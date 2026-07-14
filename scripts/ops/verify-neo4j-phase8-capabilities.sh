#!/usr/bin/env bash
set -uo pipefail

if [[ "${SNOW_CONNECTION:-}" != "snowconn" ]]; then
  echo "ERROR: SNOW_CONNECTION must be exactly snowconn" >&2
  exit 2
fi

SNOW_BIN="${SNOW_BIN:-snow}"
DATABASE="${PHASE8_DATABASE:-EDGARTOOLS_DEV}"
SCHEMA="${PHASE8_GRAPH_SCHEMA:-NEO4J_GRAPH_MIGRATION}"
APP="${PHASE8_APP_NAME:-Neo4j_Graph_Analytics}"
POOL="${PHASE8_COMPUTE_POOL:-CPU_X64_XS}"
RUN_ID="${PHASE8_RUN_ID:-$(date -u +%Y%m%d%H%M%S)-$$}"
SAFE_ID="${RUN_ID//-/_}"
OUTPUT_TABLE="PHASE8_BFS_${SAFE_ID}"
RESULTS_DIR="${PHASE8_RESULTS_DIR:-${TMPDIR:-/tmp}}"
RESULTS_FILE="${RESULTS_DIR%/}/neo4j-phase8-${RUN_ID}.tsv"
mkdir -p "$RESULTS_DIR"
: > "$RESULTS_FILE"

record() {
  local capability="$1" status="$2" detail="$3"
  detail="${detail//$'\t'/ }"; detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\n' "$capability" "$status" "$detail" | tee -a "$RESULTS_FILE"
}

cleanup() {
  local output
  output="$($SNOW_BIN sql -c snowconn -q "GRANT OWNERSHIP ON TABLE ${DATABASE}.${SCHEMA}.${OUTPUT_TABLE} TO ROLE ACCOUNTADMIN REVOKE CURRENT GRANTS; DROP TABLE ${DATABASE}.${SCHEMA}.${OUTPUT_TABLE}" --format JSON 2>&1)" || true
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
    record "$capability" PASS "${output:0:1400}"; return 0
  fi
  record "$capability" FAIL "exit=${rc}; ${output:0:1400}"; return 1
}

failures=0
app_output="$($SNOW_BIN sql -c snowconn -q "SHOW APPLICATIONS LIKE '${APP}'" --format JSON 2>&1)"
if [[ "$app_output" == *"V1_0"* ]]; then record app_version PASS "${app_output:0:1000}"; else record app_version FAIL "${app_output:0:1000}"; ((failures+=1)); fi

sample_output="$($SNOW_BIN sql -c snowconn -q "SELECT NODEID FROM ${DATABASE}.${SCHEMA}.GRAPH_APP_NODES ORDER BY NODEID LIMIT 1" --format JSON 2>&1)"
sample_node="$(printf '%s\n' "$sample_output" | sed -n 's/.*"NODEID": "\([^"]*\)".*/\1/p' | head -1)"
if [[ -z "$sample_node" ]]; then record sample_node FAIL "$sample_output"; exit 1; fi
record sample_node PASS "$sample_node"

project="'project': {'nodeTables':['${DATABASE}.${SCHEMA}.GRAPH_APP_NODES'],'relationshipTables':{'${DATABASE}.${SCHEMA}.GRAPH_APP_EDGES':{'sourceTable':'${DATABASE}.${SCHEMA}.GRAPH_APP_NODES','targetTable':'${DATABASE}.${SCHEMA}.GRAPH_APP_NODES','orientation':'NATURAL'}}}"
run_job graph_info "CALL ${APP}.GRAPH.GRAPH_INFO('${POOL}', {${project},'compute':{}})" || ((failures+=1))
run_job bfs "CALL ${APP}.GRAPH.BFS('${POOL}', {${project},'compute':{'sourceNodeTable':'${DATABASE}.${SCHEMA}.GRAPH_APP_NODES','sourceNode':'${sample_node}','targetNodesTable':'${DATABASE}.${SCHEMA}.GRAPH_APP_NODES','targetNodes':[],'maxDepth':2},'write':[{'outputTable':'${DATABASE}.${SCHEMA}.${OUTPUT_TABLE}'}]})" || ((failures+=1))

list_output="$($SNOW_BIN sql -c snowconn -q "SELECT * FROM TABLE(${APP}.EXPERIMENTAL.LIST_GRAPHS())" --format JSON 2>&1)"; list_rc=$?
if [[ $list_rc -eq 0 ]]; then
  record list_graphs PASS "${list_output:0:1400}"
else
  record list_graphs EXTERNAL_BLOCKER "exit=${list_rc}; ${list_output:0:1400}"
fi

if [[ $failures -eq 0 ]]; then
  record aggregate PASS "platform-owned GRAPH_INFO and BFS compatibility checks passed"
  echo "RESULTS_FILE=$RESULTS_FILE"
  exit 0
fi
record aggregate FAIL "${failures} platform-owned checks failed"
echo "RESULTS_FILE=$RESULTS_FILE"
exit 1

