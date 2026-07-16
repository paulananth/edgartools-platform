#!/usr/bin/env bash
set -uo pipefail

# Phase 7 (07-07) bounded AWS-dev/Snowflake-dev rehearsal for the temporal MDM ->
# Snowflake-hosted Neo4j Graph Analytics generation lifecycle (EDGE-07, EDGE-08,
# ARTF-01, ARTF-02, RPRE-01, RSYNC-01..05, RTEMP-01..04, RCOV-01/02, RLINE-01).
#
# This script is the repeatable backbone for the dev rehearsal: it exercises the
# generation lifecycle (plan -> build -> fan-in -> activate -> sync -> verify ->
# graph-activate), publication watermark/alert state, coverage categories, hosted
# Neo4j identity/property/traversal parity, retry-of-failed-partitions, entity
# merge, and rollback -- all against Snowflake-hosted graph state (no NEO4J_*,
# Bolt, or Aura credentials anywhere in this file). Scenarios that require
# deliberately corrupting dev state (ambiguous silver conflicts, ETag/version
# concurrency races, stale exclusion fingerprints) are already covered by the
# unit/integration suites from 07-01..07-06; per 07-VALIDATION.md's "Live dev"
# row, this script's job is the generation/graph pipeline specifically.
#
# Every command in this script is dev-scoped and gated behind
# SNOW_CONNECTION=snowconn; the guard below runs before anything else executes.
#
# Usage:
#   SNOW_CONNECTION=snowconn bash scripts/ops/verify-relationship-generations.sh --all
#   SNOW_CONNECTION=snowconn bash scripts/ops/verify-relationship-generations.sh --stage watermark

if [[ "${SNOW_CONNECTION:-}" != "snowconn" ]]; then
  echo "ERROR: SNOW_CONNECTION must be exactly snowconn" >&2
  exit 2
fi

usage() {
  cat <<'USAGE'
Usage:
  verify-relationship-generations.sh --all [options]
  verify-relationship-generations.sh --stage <name> [options]

Stages (in --all order):
  preflight            Ownership guard: no overlapping runtime owns dev graph/silver.
  watermark            mdm publication-status (freshness, 5/15 minute alert state).
  plan                 mdm generation-plan (opens a generation, plans partitions).
  build-partitions     mdm generation-build-partition for every planned partition.
  fan-in               mdm generation-fan-in (coverage ledger, verified/failed).
  activate-generation  mdm generation-activate (MDM-side activation).
  sync-graph           mdm sync-graph (publish into the new generation; does not activate).
  verify-graph         mdm verify-graph (identity/property parity, Native App checks).
  graph-activate       mdm graph-activate (single Snowflake active-generation pointer).
  coverage-report      mdm coverage-report (EDGE-07/08 categories).
  hosted-e2e           neo4j-snowflake-migration.py --hosted-e2e (traversal + parity SQL).
  retry-failed         mdm generation-retry-failed-partitions (bounded retry rehearsal).
  entity-merge         mdm merge (only runs if --entity-merge-keep/--entity-merge-discard given).
  graph-rollback       mdm graph-rollback (only runs if --rollback-to-generation-id given).

Options:
  --aws-profile <p>                  AWS CLI profile. Default: sec_platform_deployer.
  --aws-region <r>                   AWS region. Default: us-east-1.
  --snowflake-database <db>          Default: DBT_SNOWFLAKE_DATABASE or EDGARTOOLS_DEV.
  --run-id <id>                      Correlates generation-plan's S3 partition manifest.
                                     Default: verify-rel-gen-<utc timestamp>-<pid>.
  --rule-version <v>                 Default: v1.
  --schema-version <v>               Default: v1.
  --evidence-dir <dir>                Default: ./evidence/relationship-generations/<run-id>.
  --entity-merge-keep <entity_id>     Optional: entity_id_keep for the entity-merge stage.
  --entity-merge-discard <entity_id>  Optional: entity_id_discard for the entity-merge stage.
  --entity-merge-reason <text>        Optional: --reason passed to mdm merge.
  --rollback-to-generation-id <id>    Optional: generation to roll back to.
  --skip-ownership-check              Bypass the load_history-running guard (documented risk only).
  -h, --help                          Show this help.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

AWS_PROFILE_NAME="${AWS_PROFILE:-sec_platform_deployer}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
SNOWFLAKE_DATABASE_NAME="${DBT_SNOWFLAKE_DATABASE:-EDGARTOOLS_DEV}"
RUN_ID="verify-rel-gen-$(date -u +%Y%m%d%H%M%S)-$$"
RULE_VERSION="v1"
SCHEMA_VERSION="v1"
EVIDENCE_DIR=""
ENTITY_MERGE_KEEP=""
ENTITY_MERGE_DISCARD=""
ENTITY_MERGE_REASON="07-07 dev rehearsal: entity-merge connectivity/lineage scenario"
ROLLBACK_TO_GENERATION_ID=""
SKIP_OWNERSHIP_CHECK=false
STAGE=""
RUN_ALL=false

STAGE_ORDER=(preflight watermark plan build-partitions fan-in activate-generation sync-graph verify-graph graph-activate coverage-report hosted-e2e retry-failed entity-merge graph-rollback)

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) RUN_ALL=true; shift ;;
    --stage) STAGE="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --snowflake-database) SNOWFLAKE_DATABASE_NAME="${2:?}"; shift 2 ;;
    --run-id) RUN_ID="${2:?}"; shift 2 ;;
    --rule-version) RULE_VERSION="${2:?}"; shift 2 ;;
    --schema-version) SCHEMA_VERSION="${2:?}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:?}"; shift 2 ;;
    --entity-merge-keep) ENTITY_MERGE_KEEP="${2:?}"; shift 2 ;;
    --entity-merge-discard) ENTITY_MERGE_DISCARD="${2:?}"; shift 2 ;;
    --entity-merge-reason) ENTITY_MERGE_REASON="${2:?}"; shift 2 ;;
    --rollback-to-generation-id) ROLLBACK_TO_GENERATION_ID="${2:?}"; shift 2 ;;
    --skip-ownership-check) SKIP_OWNERSHIP_CHECK=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$RUN_ALL" != "true" && -z "$STAGE" ]]; then
  usage >&2
  fail "either --all or --stage <name> is required"
fi

EVIDENCE_DIR="${EVIDENCE_DIR:-./evidence/relationship-generations/${RUN_ID}}"
mkdir -p "$EVIDENCE_DIR"
EVIDENCE_FILE="${EVIDENCE_DIR}/evidence.jsonl"
: > "$EVIDENCE_FILE"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Overridable so tests can substitute fake binaries; production runs use the
# real `aws`/`uv` on PATH (mirrors the SNOW_BIN/UV_BIN pattern already
# established by scripts/ops/verify-neo4j-phase7-capabilities.sh).
AWS_BIN="${AWS_BIN:-aws}"
UV_BIN="${UV_BIN:-uv}"

# Redact anything that looks like a credential/connection string before it is
# ever written to the evidence file (threat model: "evidence leaks credentials
# or sensitive generated JSON"). This runs in addition to, not instead of, each
# command's own masking.
redact() {
  sed -E \
    -e 's#(postgresql|postgres)://[^ "'"'"']+#\1://[REDACTED]#g' \
    -e 's/("?(DSN|PASSWORD|SECRET|TOKEN|ACCESS_KEY|SECRET_KEY)"?[[:space:]:=]+)"[^"]*"/\1"[REDACTED]"/gI' \
    -e 's/("?(DSN|PASSWORD|SECRET|TOKEN|ACCESS_KEY|SECRET_KEY)"?[[:space:]:=]+)[^ ",}]+/\1[REDACTED]/gI' \
    -e 's/(SecretString"?:[[:space:]]*")[^"]*(")/\1[REDACTED]\2/gI'
}

aws_cli() {
  "$AWS_BIN" --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
}

mdm_cli() {
  (cd "$REPO_ROOT" && SNOW_CONNECTION=snowconn SNOWFLAKE_CONNECTION=snowconn \
    DBT_SNOWFLAKE_DATABASE="$SNOWFLAKE_DATABASE_NAME" MDM_SNOWFLAKE_DATABASE="$SNOWFLAKE_DATABASE_NAME" \
    "$UV_BIN" run --extra snowflake --extra mdm-runtime edgar-warehouse mdm "$@")
}

# Writes one JSONL evidence record. $4 is expected to already be redacted by
# the caller -- redaction happens before recording, never after, so a secret
# never reaches disk (or this function's own argv) in the first place.
record() {
  local stage="$1" command="$2" exit_code="$3" output="$4"
  local truncated encoded
  truncated="${output:0:6000}"
  encoded="$(printf '%s' "$truncated" | base64 | tr -d '\n')"
  python3 - "$stage" "$command" "$exit_code" "$EVIDENCE_FILE" "$encoded" <<'PYEOF'
import base64
import datetime
import json
import sys

stage, command, exit_code, evidence_file, encoded_output = sys.argv[1:6]
output = base64.b64decode(encoded_output).decode("utf-8", errors="replace")
entry = {
    "stage": stage,
    "command": command,
    "exit_code": int(exit_code),
    "output": output[:4000],
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(evidence_file, "a") as fh:
    fh.write(json.dumps(entry, sort_keys=True) + "\n")
PYEOF
}

run_stage_command() {
  local stage="$1" command_desc="$2"
  shift 2
  local output rc redacted_output
  output="$("$@" 2>&1)"
  rc=$?
  redacted_output="$(printf '%s' "$output" | redact)"
  record "$stage" "$command_desc" "$rc" "$redacted_output"
  printf '%s\n' "$redacted_output"
  echo "[$stage] exit=${rc} (evidence: ${EVIDENCE_FILE})"
  return "$rc"
}

# -- stage implementations ---------------------------------------------------

stage_preflight() {
  if [[ "$SKIP_OWNERSHIP_CHECK" == "true" ]]; then
    record preflight "skip-ownership-check" 0 "WARNING: ownership check bypassed by operator flag"
    echo "[preflight] SKIPPED ownership check (--skip-ownership-check)"
    return 0
  fi
  local running
  running="$(aws_cli stepfunctions list-executions \
    --state-machine-arn "arn:aws:states:${AWS_REGION_NAME}:690839588395:stateMachine:edgartools-dev-load-history" \
    --status-filter RUNNING \
    --max-results 2 \
    --query 'length(executions)' \
    --output text 2>&1)" || { record preflight "list-executions load_history" 1 "$running"; fail "could not query load_history executions: $running"; }
  record preflight "list-executions load_history" 0 "running=${running}"
  if [[ "$running" != "0" ]]; then
    fail "active load_history execution(s)=${running}; another runtime owns the dev silver/graph surface -- retry once idle"
  fi
  echo "[preflight] PASS: no active load_history execution owns the dev graph/silver surface"
}

stage_watermark() {
  run_stage_command watermark "mdm publication-status" mdm_cli publication-status
}

stage_plan() {
  run_stage_command plan "mdm generation-plan --run-id ${RUN_ID} --rule-version ${RULE_VERSION} --schema-version ${SCHEMA_VERSION}" \
    mdm_cli generation-plan --run-id "$RUN_ID" --rule-version "$RULE_VERSION" --schema-version "$SCHEMA_VERSION"
}

stage_build_partitions() {
  local manifest_json partition_ids partition_id rc=0
  manifest_json="$(cd "$REPO_ROOT" && "$UV_BIN" run --extra s3 python3 -c "
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes
import os, sys
location = StorageLocation(root=os.environ['WAREHOUSE_BRONZE_ROOT'])
path = location.join(f\"reference/mdm_generation/runs/${RUN_ID}/partitions.jsonl\")
sys.stdout.write(read_bytes(path).decode('utf-8'))
" 2>&1)" || { record build-partitions "read partitions.jsonl for run ${RUN_ID}" 1 "$manifest_json"; fail "could not read partition manifest: $manifest_json"; }
  record build-partitions "read partitions.jsonl for run ${RUN_ID}" 0 "$manifest_json"

  partition_ids="$(printf '%s\n' "$manifest_json" | python3 -c "
import json, sys
for line in sys.stdin:
    line = line.strip()
    if line:
        print(json.loads(line)['partition_id'])
")"
  if [[ -z "$partition_ids" ]]; then
    fail "no partitions found in manifest for run ${RUN_ID}"
  fi
  while IFS= read -r partition_id; do
    [[ -n "$partition_id" ]] || continue
    run_stage_command build-partitions "mdm generation-build-partition --partition-id ${partition_id}" \
      mdm_cli generation-build-partition --partition-id "$partition_id" || rc=1
  done <<< "$partition_ids"
  return "$rc"
}

stage_fan_in() {
  run_stage_command fan-in "mdm generation-fan-in --run-id ${RUN_ID}" \
    mdm_cli generation-fan-in --run-id "$RUN_ID"
}

stage_activate_generation() {
  run_stage_command activate-generation "mdm generation-activate --run-id ${RUN_ID}" \
    mdm_cli generation-activate --run-id "$RUN_ID"
}

stage_sync_graph() {
  local generation_id
  generation_id="$(cd "$REPO_ROOT" && "$UV_BIN" run --extra s3 python3 -c "
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes
import os, json
location = StorageLocation(root=os.environ['WAREHOUSE_BRONZE_ROOT'])
path = location.join(f\"reference/mdm_generation/runs/${RUN_ID}/generation.json\")
print(json.loads(read_bytes(path).decode('utf-8'))['generation_id'])
" 2>&1)" || fail "could not resolve generation_id for run ${RUN_ID}: $generation_id"
  run_stage_command sync-graph "mdm sync-graph --generation-id ${generation_id}" \
    mdm_cli sync-graph --generation-id "$generation_id" --target-database "$SNOWFLAKE_DATABASE_NAME"
}

stage_verify_graph() {
  run_stage_command verify-graph "mdm verify-graph" mdm_cli verify-graph
}

stage_graph_activate() {
  local generation_id
  generation_id="$(cd "$REPO_ROOT" && "$UV_BIN" run --extra s3 python3 -c "
from edgar_warehouse.infrastructure.object_storage import StorageLocation, read_bytes
import os, json
location = StorageLocation(root=os.environ['WAREHOUSE_BRONZE_ROOT'])
path = location.join(f\"reference/mdm_generation/runs/${RUN_ID}/generation.json\")
print(json.loads(read_bytes(path).decode('utf-8'))['generation_id'])
" 2>&1)" || fail "could not resolve generation_id for run ${RUN_ID}: $generation_id"
  run_stage_command graph-activate "mdm graph-activate --generation-id ${generation_id} --target-database ${SNOWFLAKE_DATABASE_NAME}" \
    mdm_cli graph-activate --generation-id "$generation_id" --target-database "$SNOWFLAKE_DATABASE_NAME"
}

stage_coverage_report() {
  run_stage_command coverage-report "mdm coverage-report" mdm_cli coverage-report
}

stage_hosted_e2e() {
  run_stage_command hosted-e2e "neo4j-snowflake-migration.py --env dev --snow-connection snowconn --hosted-e2e" \
    bash -c "cd '$REPO_ROOT' && '$UV_BIN' run --extra snowflake python3 scripts/ops/neo4j-snowflake-migration.py --env dev --snow-connection snowconn --output-dir '${EVIDENCE_DIR}/sql' --target-database '${SNOWFLAKE_DATABASE_NAME}' --hosted-e2e"
}

stage_retry_failed() {
  run_stage_command retry-failed "mdm generation-retry-failed-partitions --run-id ${RUN_ID}" \
    mdm_cli generation-retry-failed-partitions --run-id "$RUN_ID"
}

stage_entity_merge() {
  if [[ -z "$ENTITY_MERGE_KEEP" || -z "$ENTITY_MERGE_DISCARD" ]]; then
    record entity-merge "skipped" 0 "SKIPPED: --entity-merge-keep/--entity-merge-discard not provided"
    echo "[entity-merge] SKIPPED (no --entity-merge-keep/--entity-merge-discard given)"
    return 0
  fi
  run_stage_command entity-merge "mdm merge ${ENTITY_MERGE_KEEP} ${ENTITY_MERGE_DISCARD} --reason '${ENTITY_MERGE_REASON}'" \
    mdm_cli merge "$ENTITY_MERGE_KEEP" "$ENTITY_MERGE_DISCARD" --reason "$ENTITY_MERGE_REASON"
}

stage_graph_rollback() {
  if [[ -z "$ROLLBACK_TO_GENERATION_ID" ]]; then
    record graph-rollback "skipped" 0 "SKIPPED: --rollback-to-generation-id not provided"
    echo "[graph-rollback] SKIPPED (no --rollback-to-generation-id given)"
    return 0
  fi
  run_stage_command graph-rollback "mdm graph-rollback --generation-id ${ROLLBACK_TO_GENERATION_ID} --target-database ${SNOWFLAKE_DATABASE_NAME}" \
    mdm_cli graph-rollback --generation-id "$ROLLBACK_TO_GENERATION_ID" --target-database "$SNOWFLAKE_DATABASE_NAME"
}

dispatch_stage() {
  case "$1" in
    preflight) stage_preflight ;;
    watermark) stage_watermark ;;
    plan) stage_plan ;;
    build-partitions) stage_build_partitions ;;
    fan-in) stage_fan_in ;;
    activate-generation) stage_activate_generation ;;
    sync-graph) stage_sync_graph ;;
    verify-graph) stage_verify_graph ;;
    graph-activate) stage_graph_activate ;;
    coverage-report) stage_coverage_report ;;
    hosted-e2e) stage_hosted_e2e ;;
    retry-failed) stage_retry_failed ;;
    entity-merge) stage_entity_merge ;;
    graph-rollback) stage_graph_rollback ;;
    *) fail "unknown stage: $1 (see --help for the stage list)" ;;
  esac
}

if [[ "$RUN_ALL" == "true" ]]; then
  failures=0
  for stage in "${STAGE_ORDER[@]}"; do
    if ! dispatch_stage "$stage"; then
      failures=$((failures + 1))
      echo "ERROR: stage '$stage' failed; a failed generation must never change the active pointer -- inspect ${EVIDENCE_FILE} before retrying" >&2
      break
    fi
  done
  echo "RUN_ID=${RUN_ID}"
  echo "EVIDENCE_FILE=${EVIDENCE_FILE}"
  if [[ "$failures" -ne 0 ]]; then
    exit 1
  fi
  exit 0
fi

dispatch_stage "$STAGE"
rc=$?
echo "RUN_ID=${RUN_ID}"
echo "EVIDENCE_FILE=${EVIDENCE_FILE}"
exit "$rc"
