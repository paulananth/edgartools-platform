#!/usr/bin/env bash
# Full pipeline health check: bronze → silver → gold → MDM (SQL) → Neo4j
#
# Checks every layer of the stack in order and prints a human-readable
# report.  Run before/after any bootstrap, MDM deploy, or debugging session.
#
# Prerequisites:
#   az login                    Azure CLI authenticated
#   uv sync --extra mdm         Python deps for the MDM SQL check
#   terraform state initialised for the target environment
#
# Usage:
#   ./check-pipeline-health.sh --env dev
#   ./check-pipeline-health.sh --env dev --skip-neo4j
#   ./check-pipeline-health.sh --env dev --skip-gold --skip-logs
#
# Sections:
#   1  Bronze        CIK counts by date, run manifests
#   2  Silver        silver.duckdb size + run manifests (populated = MDM can run)
#   3  Gold          parquet row counts per table per run_id
#   4  MDM SQL       all entity/relationship/registry table counts
#                    + relationship_instance breakdown by type + pending-sync
#   5  Neo4j         all 5 edge types + node total via verify-graph job
#   6  Bootstrap     execution history + WAREHOUSE_RUNTIME_MODE check
#   7  Failed logs   last log lines from the most recent failed run
#   8  ACR images    current :dev and :sha-* tags in the registry

set -euo pipefail

ENVIRONMENT=""
SKIP_NEO4J=false
SKIP_GOLD=false
SKIP_MDM=false
SKIP_BRONZE=false
SKIP_SILVER=false
SKIP_LOGS=false
SKIP_ACR=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)         ENVIRONMENT="${2:?}"; shift 2 ;;
    --skip-neo4j)  SKIP_NEO4J=true;  shift ;;
    --skip-gold)   SKIP_GOLD=true;   shift ;;
    --skip-mdm)    SKIP_MDM=true;    shift ;;
    --skip-bronze) SKIP_BRONZE=true; shift ;;
    --skip-silver) SKIP_SILVER=true; shift ;;
    --skip-logs)   SKIP_LOGS=true;   shift ;;
    --skip-acr)    SKIP_ACR=true;    shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ -z "$ENVIRONMENT" ]] && { echo "ERROR: --env is required" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"

tf_out()      { terraform -chdir="$TF_ROOT" output -raw  "$1" 2>/dev/null || true; }
tf_out_json() { terraform -chdir="$TF_ROOT" output -json "$1" 2>/dev/null || echo "{}"; }

# Resolve infra names from Terraform outputs
RESOURCE_GROUP="$(tf_out resource_group_name)"
KEY_VAULT="$(tf_out key_vault_name)"
ACR_NAME="$(tf_out container_registry_login_server 2>/dev/null | cut -d. -f1 || true)"
SQL_HOST="$(tf_out mdm_sql_server_fqdn)"
SQL_DB="$(tf_out mdm_sql_database_name)"; SQL_DB="${SQL_DB:-mdm}"

# Derive storage account from warehouse_storage_root (abfss://<container>@<acct>.dfs...)
WAREHOUSE_ROOT="$(tf_out warehouse_storage_root)"
BRONZE_ROOT="$(tf_out warehouse_bronze_root)"
STORAGE_ACCOUNT="$(echo "$WAREHOUSE_ROOT" | python3 -c \
  "import sys,re; m=re.search(r'@([^.]+)',sys.stdin.read()); print(m.group(1) if m else '')" 2>/dev/null || true)"

# Job names
BOOT_JOB="$(tf_out_json container_app_job_names | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bootstrap_recent_10',''))" 2>/dev/null || true)"
MDM_JOBS_JSON="$(tf_out_json mdm_container_app_job_names)"
get_mdm_job() { echo "$MDM_JOBS_JSON" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$1',''))" 2>/dev/null || true; }
COUNTS_JOB="$(get_mdm_job counts)"
VERIFY_JOB="$(get_mdm_job verify_graph)"
RUN_JOB="$(get_mdm_job run)"

# Helper: run a Container App Job and wait for completion; echoes execution name
run_job_wait() {
  local job="$1" rg="$2"
  local exec_name
  exec_name="$(az containerapp job start --name "$job" --resource-group "$rg" \
    --query "name" -o tsv 2>/dev/null)"
  until STATUS="$(az containerapp job execution show \
      --name "$job" --resource-group "$rg" \
      --job-execution-name "$exec_name" \
      --query "properties.status" -o tsv 2>/dev/null)" && \
      [[ "$STATUS" =~ ^(Succeeded|Failed|Stopped)$ ]]; do
    sleep 8
  done
  echo "$exec_name"          # callers use the last line as exec name
  echo "$STATUS" >&2         # status on stderr for caller to capture
}

# Helper: extract JSON from container job log stream and pretty-print it
parse_job_json_log() {
  local job="$1" rg="$2" exec_name="$3" container="$4"
  az containerapp job logs show \
    --name "$job" --resource-group "$rg" \
    --execution "$exec_name" --container "$container" \
    --tail 200 2>/dev/null | \
  python3 -c "
import sys, json
for raw in sys.stdin:
    raw = raw.strip()
    try:
        outer = json.loads(raw)
        log = outer.get('Log', '')
    except Exception:
        log = raw
    if not log or 'Connecting to' in log or 'Successfully Connected' in log:
        continue
    # Try to pretty-print embedded JSON (the actual edgar-warehouse output)
    try:
        inner = json.loads(log)
        for k, v in sorted(inner.items()):
            print(f'    {k:<42}: {v}')
    except Exception:
        print(f'    {log}')
" 2>/dev/null
}

divider() { echo ""; echo "==> [$1] $2"; }

echo "================================================"
echo " Pipeline Health Check   env=${ENVIRONMENT}"
echo " Resource group  : ${RESOURCE_GROUP}"
echo " Storage account : ${STORAGE_ACCOUNT}"
echo " Key Vault       : ${KEY_VAULT}"
echo " SQL host        : ${SQL_HOST}"
echo "================================================"

# ---------------------------------------------------------------------------
# 1. BRONZE LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_BRONZE" == "false" ]]; then
  divider 1 "BRONZE LAYER"

  echo "  Run manifests (warehouse/bronze/runs/):"
  az storage blob list \
    --container-name bronze \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/bronze/runs/" \
    --query "[?ends_with(name,'manifest.json')].name" -o tsv 2>/dev/null | \
  while read -r path; do
    TMP=/tmp/_bronze_manifest_$$.json
    az storage blob download \
      --container-name bronze --account-name "${STORAGE_ACCOUNT}" \
      --auth-mode login --name "$path" --file "$TMP" -o none 2>/dev/null || continue
    python3 -c "
import json
d=json.load(open('$TMP'))
run=d.get('run_id','?')[:8]
mode=d.get('runtime_mode','?')
created=d.get('created_at','?')[:10]
scope=d.get('scope',{})
print(f'    run={run}  mode={mode}  created={created}  cik_list={scope.get(\"cik_list\")}  filter={scope.get(\"tracking_status_filter\")}')
" 2>/dev/null
    rm -f "$TMP"
  done

  echo ""
  echo "  Submission CIKs in bronze (sample up to 5 000 files):"
  az storage blob list \
    --container-name bronze \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/bronze/submissions/sec/" \
    --num-results 5000 \
    --query "[?ends_with(name,'.json')].name" -o tsv 2>/dev/null | \
  python3 -c "
import sys, re
from collections import defaultdict
ciks=set(); by_date=defaultdict(set)
for line in sys.stdin:
    n=line.strip()
    m=re.search(r'cik=(\d+)',n); dm=re.search(r'/(\d{4}/\d{2}/\d{2})/',n)
    if m: ciks.add(m.group(1))
    if m and dm: by_date[dm.group(1)].add(m.group(1))
print(f'    Distinct CIKs in sample : {len(ciks):,}')
for d in sorted(by_date):
    print(f'    {d} : {len(by_date[d]):,} CIKs written that day')
" 2>/dev/null
fi

# ---------------------------------------------------------------------------
# 2. SILVER LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_SILVER" == "false" ]]; then
  divider 2 "SILVER LAYER"

  SILVER_BLOB="warehouse/silver/sec/silver.duckdb"
  SIZE=$(az storage blob show \
    --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login --name "${SILVER_BLOB}" \
    --query "properties.contentLength" -o tsv 2>/dev/null || echo "0")
  MODIFIED=$(az storage blob show \
    --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login --name "${SILVER_BLOB}" \
    --query "properties.lastModified" -o tsv 2>/dev/null || echo "unknown")

  SIZE="${SIZE:-0}"
  if [[ "${SIZE}" -gt 0 ]]; then
    MB=$(python3 -c "print(f'{${SIZE}/1048576:.1f}')")
    echo "  silver.duckdb : ${SIZE} bytes (${MB} MB)   last_modified=${MODIFIED}"
    echo "  Status        : POPULATED — MDM pipeline can run"
  else
    echo "  silver.duckdb : 0 bytes   last_modified=${MODIFIED}"
    echo "  Status        : EMPTY — MDM run will read no data"
    echo "  Fix           : ensure WAREHOUSE_RUNTIME_MODE=bronze_capture, then run bootstrap-recent-10"
  fi

  echo ""
  echo "  Silver run manifests:"
  az storage blob list \
    --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/silver/sec/runs/" \
    --query "[?ends_with(name,'manifest.json')].name" -o tsv 2>/dev/null | \
  while read -r path; do
    TMP=/tmp/_silver_manifest_$$.json
    az storage blob download \
      --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
      --auth-mode login --name "$path" --file "$TMP" -o none 2>/dev/null || continue
    python3 -c "
import json
d=json.load(open('$TMP'))
run=d.get('run_id','?')[:8]
mode=d.get('runtime_mode','?')
created=d.get('created_at','?')[:10]
print(f'    run={run}  mode={mode}  created={created}')
" 2>/dev/null
    rm -f "$TMP"
  done
fi

# ---------------------------------------------------------------------------
# 3. GOLD LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_GOLD" == "false" ]]; then
  divider 3 "GOLD LAYER (parquet row counts per run)"

  GOLD_TABLES="dim_company dim_party dim_security fact_filing_activity \
               fact_ownership_transaction fact_ownership_holding_snapshot \
               fact_adv_private_fund"

  GOLD_RUN_IDS=$(az storage blob list \
    --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/gold/dim_company/" \
    --query "[?ends_with(name,'.parquet')].name" -o tsv 2>/dev/null | \
    python3 -c "
import sys
seen=set()
for line in sys.stdin:
    if 'run_id=' in line:
        run=line.strip().split('run_id=')[1].split('/')[0]
        if run not in seen: seen.add(run); print(run)
" 2>/dev/null || true)

  if [[ -z "$GOLD_RUN_IDS" ]]; then
    echo "  No gold parquet files found"
  else
    while IFS= read -r RUN_ID; do
      echo "  Run ${RUN_ID:0:8}:"
      for TABLE in $GOLD_TABLES; do
        BLOB="warehouse/gold/${TABLE}/run_id=${RUN_ID}/${TABLE}.parquet"
        TMP="/tmp/_gold_${TABLE}_$$.parquet"
        az storage blob download \
          --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
          --auth-mode login --name "$BLOB" --file "$TMP" -o none 2>/dev/null || \
          { printf "    %-45s : not found\n" "$TABLE"; continue; }
        ROWS=$(uv run python3 -c "
import duckdb
n=duckdb.connect(':memory:').execute(\"SELECT count(*) FROM read_parquet('${TMP}')\").fetchone()[0]
print(n)
" 2>/dev/null || echo "?")
        printf "    %-45s : %6s rows\n" "$TABLE" "$ROWS"
        rm -f "$TMP"
      done
    done <<< "$GOLD_RUN_IDS"
  fi
fi

# ---------------------------------------------------------------------------
# 4. MDM LAYER (Azure SQL)
# ---------------------------------------------------------------------------
if [[ "$SKIP_MDM" == "false" ]]; then
  divider 4 "MDM LAYER (Azure SQL)"

  SQL_PASS=$(az keyvault secret show \
    --vault-name "${KEY_VAULT}" --name mdm-sql-admin-password \
    --query value -o tsv 2>/dev/null || echo "")

  if [[ -z "$SQL_PASS" || -z "$SQL_HOST" ]]; then
    echo "  Cannot reach Azure SQL directly — triggering mdm-counts job instead"
    if [[ -n "$COUNTS_JOB" ]]; then
      EXEC="$(run_job_wait "$COUNTS_JOB" "$RESOURCE_GROUP" 2>/tmp/_job_status_$$)"
      STATUS="$(cat /tmp/_job_status_$$ 2>/dev/null || echo '?')"; rm -f /tmp/_job_status_$$
      echo "  mdm-counts job: $STATUS"
      parse_job_json_log "$COUNTS_JOB" "$RESOURCE_GROUP" "$EXEC" "mdm"
    fi
  else
    uv run --with sqlalchemy-pytds --with python-tds --with pyopenssl --with certifi \
      python3 << PYEOF
import pytds, certifi

conn = pytds.connect(
    dsn='${SQL_HOST}', user='mdmadmin', password='${SQL_PASS}',
    database='${SQL_DB}', port=1433, as_dict=True, cafile=certifi.where())
cur = conn.cursor()

sections = {
    'Entity layer': ['mdm_entity','mdm_company','mdm_adviser',
                     'mdm_person','mdm_security','mdm_fund'],
    'Link layer':   ['mdm_source_ref','mdm_change_log','mdm_match_review'],
    'Relationship': ['mdm_relationship_instance'],
    'Graph registry': ['mdm_entity_type_definition','mdm_relationship_type',
                       'mdm_relationship_property_def','mdm_relationship_source_mapping'],
    'Rules / seed': ['mdm_source_priority','mdm_field_survivorship',
                     'mdm_match_threshold','mdm_normalization_rule'],
}

for section, tables in sections.items():
    print(f'  --- {section} ---')
    for t in tables:
        try:
            cur.execute(f'SELECT count(*) as n FROM {t}')
            print(f'    {t:<35}: {cur.fetchone()["n"]:>6,}')
        except Exception as e:
            print(f'    {t:<35}: ERROR {e}')

print()
print('  --- Relationship instances by type (total / pending Neo4j sync) ---')
cur.execute("""
    SELECT rt.rel_type_name,
           count(ri.instance_id) as total,
           sum(case when ri.graph_synced_at is null then 1 else 0 end) as pending
    FROM mdm_relationship_type rt
    LEFT JOIN mdm_relationship_instance ri ON ri.rel_type_id = rt.rel_type_id
    GROUP BY rt.rel_type_name ORDER BY total DESC, rt.rel_type_name
""")
for r in cur.fetchall():
    flag = ' <-- pending sync' if r['pending'] > 0 else ''
    print(f'    {r["rel_type_name"]:<22}: {r["total"]:>5} total  {r["pending"]:>5} pending{flag}')

conn.close()
PYEOF
  fi
fi

# ---------------------------------------------------------------------------
# 5. NEO4J GRAPH
# ---------------------------------------------------------------------------
if [[ "$SKIP_NEO4J" == "false" ]]; then
  divider 5 "NEO4J GRAPH"

  if [[ -z "$VERIFY_JOB" ]]; then
    echo "  Skipping — verify_graph job not found in terraform outputs"
  else
    echo "  Running ${VERIFY_JOB} ..."
    EXEC="$(run_job_wait "$VERIFY_JOB" "$RESOURCE_GROUP" 2>/tmp/_neo4j_status_$$)"
    STATUS="$(cat /tmp/_neo4j_status_$$ 2>/dev/null || echo '?')"; rm -f /tmp/_neo4j_status_$$
    echo "  Status: $STATUS"
    if [[ "$STATUS" == "Succeeded" ]]; then
      parse_job_json_log "$VERIFY_JOB" "$RESOURCE_GROUP" "$EXEC" "mdm"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 6. BOOTSTRAP JOB — EXECUTION HISTORY + RUNTIME MODE CHECK
# ---------------------------------------------------------------------------
divider 6 "BOOTSTRAP JOB — EXECUTION HISTORY + RUNTIME MODE"

if [[ -n "$BOOT_JOB" ]]; then
  RUNTIME_MODE=$(az containerapp job show \
    --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
    --query "properties.template.containers[0].env[?name=='WAREHOUSE_RUNTIME_MODE'].value" \
    -o tsv 2>/dev/null || echo "unknown")
  echo "  Job             : ${BOOT_JOB}"
  echo "  WAREHOUSE_RUNTIME_MODE : ${RUNTIME_MODE}"
  if [[ "$RUNTIME_MODE" == "infrastructure_validation" ]]; then
    echo "  !! WARNING: Mode is infrastructure_validation"
    echo "              ETL does NOT run — silver.duckdb will NOT be populated"
    echo "              Fix: set warehouse_runtime_mode = \"bronze_capture\" in terraform.tfvars and apply"
  elif [[ "$RUNTIME_MODE" == "bronze_capture" ]]; then
    echo "  OK: Mode is bronze_capture — bootstrap populates silver.duckdb"
  fi

  echo ""
  echo "  Recent executions (last 15):"
  # Use -o json without --query to get full timestamps; parse in Python
  az containerapp job execution list \
    --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
    -o json 2>/dev/null | python3 -c "
import json, sys
from datetime import datetime, timezone

def parse_dt(s):
    if not s: return None
    for fmt in ('%Y-%m-%dT%H:%M:%S+00:00','%Y-%m-%dT%H:%M:%SZ','%Y-%m-%dT%H:%M:%S.%f+00:00'):
        try: return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except: pass
    return None

runs = json.load(sys.stdin)
print(f'    {\"Run\":<10} {\"Status\":<12} {\"Started (UTC)\":<20} {\"Dur\":>7}  End?')
print('    ' + '-'*60)
for r in runs[:15]:
    props = r.get('properties', r)
    nm  = r.get('name','?')[-8:]
    st  = props.get('status','?')
    s   = parse_dt(props.get('startTime',''))
    e   = parse_dt(props.get('endTime',''))
    dt  = s.strftime('%Y-%m-%d %H:%M') if s else '?'
    if s and e:
        dur = str(int((e-s).total_seconds())) + 's'
        end = 'yes'
    else:
        dur = '(no end)' if st != 'Running' else '(running)'
        end = 'NO — abrupt exit'
    flag = ' ← last success' if st == 'Succeeded' and end == 'yes' else ''
    print(f'    {nm:<10} {st:<12} {dt:<20} {dur:>7}  {end}{flag}')
" 2>/dev/null
fi

# ---------------------------------------------------------------------------
# 7. FAILED RUN — LAST LOG LINES (ROOT CAUSE TRIAGE)
# ---------------------------------------------------------------------------
if [[ "$SKIP_LOGS" == "false" && -n "$BOOT_JOB" ]]; then
  divider 7 "FAILED RUN — LAST LOG LINES (MOST RECENT FAILURE)"

  # Find the most recent failed execution
  FAILED_EXEC=$(az containerapp job execution list \
    --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
    -o json 2>/dev/null | python3 -c "
import json, sys
runs = json.load(sys.stdin)
for r in runs:
    props = r.get('properties', r)
    if props.get('status') == 'Failed':
        print(r.get('name',''))
        break
" 2>/dev/null || true)

  if [[ -z "$FAILED_EXEC" ]]; then
    echo "  No failed executions found"
  else
    echo "  Execution: ${FAILED_EXEC}"
    echo "  Last log lines (up to 80):"
    az containerapp job logs show \
      --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
      --execution "$FAILED_EXEC" --container "edgar-warehouse" \
      --tail 500 2>/dev/null | python3 -c "
import sys, json
lines = []
for raw in sys.stdin:
    raw = raw.strip()
    try:
        d = json.loads(raw)
        log = d.get('Log','')
        ts  = d.get('TimeStamp','')[:19]
    except Exception:
        log = raw; ts = ''
    if not log or 'Connecting to' in log or 'Successfully Connected' in log:
        continue
    lines.append((ts, log))

# Print last 80 lines — most likely to contain the error
for ts, log in lines[-80:]:
    print(f'    {ts}  {log[:160]}')

if not lines:
    print('    (no log lines retrieved — replica may be gone)')
" 2>/dev/null
  fi
fi

# ---------------------------------------------------------------------------
# 8. ACR IMAGES — CURRENT TAGS
# ---------------------------------------------------------------------------
if [[ "$SKIP_ACR" == "false" && -n "$ACR_NAME" ]]; then
  divider 8 "ACR IMAGES"

  for REPO in edgar-warehouse-pipelines edgar-warehouse-mdm-neo4j; do
    echo "  ${REPO}:"
    az acr repository show-tags \
      --name "${ACR_NAME}" \
      --repository "${REPO}" \
      --orderby time_desc \
      --query "[0:6]" -o tsv 2>/dev/null | \
    while read -r tag; do
      echo "    :${tag}"
    done
  done
fi

echo ""
echo "==> Health check complete."
