#!/usr/bin/env bash
# Full pipeline health check: bronze → silver → gold → MDM → Neo4j
#
# Covers every layer of the stack and emits a structured JSON report.
# Run this before/after any bootstrap or MDM deployment to understand
# what data is present at each layer and catch breaks early.
#
# Prerequisites:
#   az login  (authenticated)
#   uv sync --extra mdm  (or --extra s3,azure for pipeline checks only)
#   terraform state initialised for the target environment
#
# Usage:
#   ./check-pipeline-health.sh --env dev
#   ./check-pipeline-health.sh --env dev --skip-neo4j
#   ./check-pipeline-health.sh --env dev --skip-gold --skip-mdm

set -euo pipefail

ENVIRONMENT=""
SKIP_NEO4J=false
SKIP_GOLD=false
SKIP_MDM=false
SKIP_BRONZE=false
SKIP_SILVER=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)         ENVIRONMENT="${2:?}"; shift 2 ;;
    --skip-neo4j)  SKIP_NEO4J=true;  shift ;;
    --skip-gold)   SKIP_GOLD=true;   shift ;;
    --skip-mdm)    SKIP_MDM=true;    shift ;;
    --skip-bronze) SKIP_BRONZE=true; shift ;;
    --skip-silver) SKIP_SILVER=true; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "Unknown: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$ENVIRONMENT" ]]; then
  echo "ERROR: --env is required" >&2; exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"

tf_out()      { terraform -chdir="$TF_ROOT" output -raw  "$1" 2>/dev/null; }
tf_out_json() { terraform -chdir="$TF_ROOT" output -json "$1" 2>/dev/null; }

RESOURCE_GROUP="$(tf_out resource_group_name)"
STORAGE_ACCOUNT="$(tf_out storage_account_name 2>/dev/null || echo "")"
KEY_VAULT="$(tf_out key_vault_name 2>/dev/null || echo "")"

# Derive storage account name from storage_account output or warehouse_storage_root
if [[ -z "$STORAGE_ACCOUNT" ]]; then
  WAREHOUSE_ROOT="$(tf_out warehouse_storage_root 2>/dev/null || echo "")"
  STORAGE_ACCOUNT="$(echo "$WAREHOUSE_ROOT" | grep -oP '(?<=@)[^.]+' || echo "")"
fi

echo "=============================================="
echo " Pipeline Health Check — env=${ENVIRONMENT}"
echo " Resource group : ${RESOURCE_GROUP}"
echo " Storage account: ${STORAGE_ACCOUNT}"
echo "=============================================="

# ---------------------------------------------------------------------------
# 1. BRONZE LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_BRONZE" == "false" ]]; then
  echo ""
  echo "==> [1] BRONZE LAYER"

  echo "  Run manifests:"
  az storage blob list \
    --container-name bronze \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/bronze/runs/" \
    --query "[?ends_with(name,'manifest.json')].name" -o tsv 2>/dev/null | \
  while read -r path; do
    run=$(echo "$path" | awk -F'/' '{print $(NF-1)}' | cut -c1-8)
    echo "    ${run}  ${path##*/runs/}"
  done

  echo ""
  echo "  Submission CIKs by date written:"
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
print(f'    Distinct CIKs (first 5000 files): {len(ciks):,}')
for d in sorted(by_date): print(f'    {d}: {len(by_date[d]):,} CIKs written')
" 2>/dev/null

  echo ""
  echo "  Bootstrap job execution history:"
  BOOT_JOB="$(tf_out_json container_app_job_names 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bootstrap_recent_10',''))" 2>/dev/null || echo "")"
  if [[ -n "$BOOT_JOB" ]]; then
    az containerapp job execution list \
      --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
      --query "[].{name:name,status:properties.status,start:properties.startTime,end:properties.endTime}" \
      -o json 2>/dev/null | python3 -c "
import json,sys
from datetime import datetime
runs=json.load(sys.stdin)
print(f'    {\"Execution\":<14} {\"Status\":<12} {\"Duration\":>10}  End recorded?')
for r in runs[:10]:
    nm=r['name'][-8:]
    st=r.get('status','?')
    s=r.get('startTime',''); e=r.get('endTime','')
    if s and e:
        dur=str(int((datetime.fromisoformat(e.replace(\"Z\",\"+00:00\"))-datetime.fromisoformat(s.replace(\"Z\",\"+00:00\"))).total_seconds()))+'s'
        end_rec='yes'
    else:
        dur='(running)' if st=='Running' else '(no end)'
        end_rec='NO'
    print(f'    {nm:<14} {st:<12} {dur:>10}  {end_rec}')
" 2>/dev/null
  fi
fi

# ---------------------------------------------------------------------------
# 2. SILVER LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_SILVER" == "false" ]]; then
  echo ""
  echo "==> [2] SILVER LAYER"

  SILVER_PATH="warehouse/silver/sec/silver.duckdb"
  SIZE=$(az storage blob show \
    --container-name warehouse \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --name "${SILVER_PATH}" \
    --query "properties.contentLength" -o tsv 2>/dev/null || echo "0")
  MODIFIED=$(az storage blob show \
    --container-name warehouse \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --name "${SILVER_PATH}" \
    --query "properties.lastModified" -o tsv 2>/dev/null || echo "unknown")

  if [[ "${SIZE}" -gt 0 ]]; then
    echo "  silver.duckdb : ${SIZE} bytes  ($(echo "scale=1; ${SIZE}/1048576" | bc) MB)  last_modified=${MODIFIED}"
    echo "  Status        : POPULATED ✓"
  else
    echo "  silver.duckdb : 0 bytes  (EMPTY — MDM run will find no data)"
    echo "  Status        : EMPTY ✗  — run bootstrap-recent-10 in bronze_capture mode"
  fi

  echo ""
  echo "  Silver run manifests:"
  az storage blob list \
    --container-name warehouse \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/silver/sec/runs/" \
    --query "[?ends_with(name,'manifest.json')].name" -o tsv 2>/dev/null | \
  while read -r path; do
    BLOB_JSON=$(az storage blob download \
      --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
      --auth-mode login --name "$path" --file /tmp/_sm_tmp.json -o none 2>/dev/null && \
      cat /tmp/_sm_tmp.json 2>/dev/null || echo "{}")
    run=$(echo "$path" | awk -F'/' '{print $(NF-1)}' | cut -c1-8)
    mode=$(echo "$BLOB_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('runtime_mode','?'))" 2>/dev/null)
    created=$(echo "$BLOB_JSON" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('created_at','?')[:10])" 2>/dev/null)
    echo "    run=${run}  mode=${mode}  created=${created}"
  done
fi

# ---------------------------------------------------------------------------
# 3. GOLD LAYER
# ---------------------------------------------------------------------------
if [[ "$SKIP_GOLD" == "false" ]]; then
  echo ""
  echo "==> [3] GOLD LAYER"

  # Find the most recent gold run ID from dim_company
  GOLD_RUNS=$(az storage blob list \
    --container-name warehouse \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --prefix "warehouse/gold/dim_company/" \
    --query "[?ends_with(name,'.parquet')].name" -o tsv 2>/dev/null | \
    python3 -c "
import sys
runs=[]
for line in sys.stdin:
    if 'run_id=' in line:
        run=line.strip().split('run_id=')[1].split('/')[0]
        runs.append(run)
for r in runs: print(r)
" 2>/dev/null)

  if [[ -z "$GOLD_RUNS" ]]; then
    echo "  No gold parquet files found"
  else
    for RUN_ID in $GOLD_RUNS; do
      SHORT="${RUN_ID:0:8}"
      echo "  Run ${SHORT}:"
      for TABLE in dim_company dim_party dim_security fact_filing_activity \
                   fact_ownership_transaction fact_ownership_holding_snapshot \
                   fact_adv_private_fund; do
        BLOB="warehouse/gold/${TABLE}/run_id=${RUN_ID}/${TABLE}.parquet"
        az storage blob download \
          --container-name warehouse --account-name "${STORAGE_ACCOUNT}" \
          --auth-mode login --name "$BLOB" --file "/tmp/_gold_${TABLE}.parquet" \
          -o none 2>/dev/null && \
        ROWS=$(uv run python3 -c "
import duckdb
n=duckdb.connect(':memory:').execute(\"SELECT count(*) FROM read_parquet('/tmp/_gold_${TABLE}.parquet')\").fetchone()[0]
print(n)
" 2>/dev/null || echo "?") && \
        printf "    %-45s : %6s rows\n" "$TABLE" "$ROWS" || \
        printf "    %-45s : not found\n" "$TABLE"
      done
    done
  fi
fi

# ---------------------------------------------------------------------------
# 4. MDM LAYER (Azure SQL)
# ---------------------------------------------------------------------------
if [[ "$SKIP_MDM" == "false" ]]; then
  echo ""
  echo "==> [4] MDM LAYER (Azure SQL)"

  if [[ -z "$KEY_VAULT" ]]; then
    echo "  Skipping — key_vault_name not found in terraform outputs"
  else
    SQL_PASS=$(az keyvault secret show \
      --vault-name "${KEY_VAULT}" --name mdm-sql-admin-password \
      --query value -o tsv 2>/dev/null || echo "")
    SQL_HOST=$(tf_out mdm_sql_server_fqdn 2>/dev/null || echo "")
    SQL_DB=$(tf_out mdm_sql_database_name 2>/dev/null || echo "mdm")

    if [[ -z "$SQL_PASS" || -z "$SQL_HOST" ]]; then
      echo "  Skipping — could not retrieve SQL credentials from Key Vault"
      echo "  Falling back to mdm-counts Container App Job..."
      COUNTS_JOB=$(tf_out_json mdm_container_app_job_names 2>/dev/null | \
        python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('counts',''))" 2>/dev/null || echo "")
      if [[ -n "$COUNTS_JOB" ]]; then
        EXEC=$(az containerapp job start \
          --name "$COUNTS_JOB" --resource-group "${RESOURCE_GROUP}" \
          --query "name" -o tsv 2>/dev/null)
        echo "  Triggered ${COUNTS_JOB}: ${EXEC}"
        echo "  (check Log Analytics for output)"
      fi
    else
      uv run --with sqlalchemy-pytds --with python-tds --with pyopenssl --with certifi \
        python3 << PYEOF
import pytds, certifi

conn = pytds.connect(dsn='${SQL_HOST}', user='mdmadmin',
    password='${SQL_PASS}', database='${SQL_DB}',
    port=1433, as_dict=True, cafile=certifi.where())
cur = conn.cursor()

sections = {
    'Entity layer': ['mdm_entity','mdm_company','mdm_adviser','mdm_person','mdm_security','mdm_fund'],
    'Relationship layer': ['mdm_relationship_instance','mdm_source_ref'],
    'Graph registry': ['mdm_entity_type_definition','mdm_relationship_type','mdm_relationship_property_def','mdm_relationship_source_mapping'],
    'Rules / seed data': ['mdm_source_priority','mdm_field_survivorship','mdm_match_threshold','mdm_normalization_rule'],
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
print('  --- Relationship instances by type ---')
try:
    cur.execute("""
        SELECT rt.rel_type_name,
               count(ri.instance_id) as total,
               sum(case when ri.graph_synced_at is null then 1 else 0 end) as pending_sync
        FROM mdm_relationship_type rt
        LEFT JOIN mdm_relationship_instance ri ON ri.rel_type_id = rt.rel_type_id
        GROUP BY rt.rel_type_name ORDER BY rt.rel_type_name
    """)
    for r in cur.fetchall():
        print(f'    {r["rel_type_name"]:<20}: {r["total"]:>4,} total  {r["pending_sync"]:>4,} pending Neo4j sync')
except Exception as e:
    print(f'    ERROR: {e}')

conn.close()
PYEOF
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 5. NEO4J GRAPH
# ---------------------------------------------------------------------------
if [[ "$SKIP_NEO4J" == "false" ]]; then
  echo ""
  echo "==> [5] NEO4J GRAPH"

  VERIFY_JOB=$(tf_out_json mdm_container_app_job_names 2>/dev/null | \
    python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('verify_graph',''))" 2>/dev/null || echo "")

  if [[ -z "$VERIFY_JOB" ]]; then
    echo "  Skipping — mdm_container_app_job_names not found in terraform outputs"
  else
    echo "  Running ${VERIFY_JOB} ..."
    EXEC=$(az containerapp job start \
      --name "$VERIFY_JOB" --resource-group "${RESOURCE_GROUP}" \
      --query "name" -o tsv 2>/dev/null)

    until STATUS=$(az containerapp job execution show \
      --name "$VERIFY_JOB" --resource-group "${RESOURCE_GROUP}" \
      --job-execution-name "$EXEC" \
      --query "properties.status" -o tsv 2>/dev/null) && \
      [[ "$STATUS" =~ ^(Succeeded|Failed|Stopped)$ ]]; do
      sleep 8
    done

    if [[ "$STATUS" == "Succeeded" ]]; then
      az containerapp job logs show \
        --name "$VERIFY_JOB" --resource-group "${RESOURCE_GROUP}" \
        --execution "$EXEC" --container "mdm" 2>/dev/null | \
      python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d=json.loads(line.strip())
        log=d.get('Log','')
        if '{' in log:
            try:
                parsed=json.loads(log)
                for k,v in sorted(parsed.items()):
                    print(f'    {k:<40}: {v:>8,}')
            except: print(f'    {log}')
    except: pass
" 2>/dev/null
    else
      echo "  verify-graph job: ${STATUS}"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 6. BOOTSTRAP JOB STATUS (RUNTIME MODE CHECK)
# ---------------------------------------------------------------------------
echo ""
echo "==> [6] RUNTIME MODE CHECK"
BOOT_JOB="${BOOT_JOB:-$(tf_out_json container_app_job_names 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('bootstrap_recent_10',''))" 2>/dev/null || echo "")}"

if [[ -n "$BOOT_JOB" ]]; then
  RUNTIME_MODE=$(az containerapp job show \
    --name "$BOOT_JOB" --resource-group "${RESOURCE_GROUP}" \
    --query "properties.template.containers[0].env[?name=='WAREHOUSE_RUNTIME_MODE'].value" \
    -o tsv 2>/dev/null || echo "unknown")
  echo "  bootstrap-recent-10 WAREHOUSE_RUNTIME_MODE : ${RUNTIME_MODE}"
  if [[ "$RUNTIME_MODE" == "infrastructure_validation" ]]; then
    echo "  WARNING: Mode is infrastructure_validation — silver DuckDB will NOT be populated"
    echo "           Set warehouse_runtime_mode = \"bronze_capture\" in terraform.tfvars and apply"
  elif [[ "$RUNTIME_MODE" == "bronze_capture" ]]; then
    echo "  OK: Mode is bronze_capture — bootstrap will populate silver DuckDB"
  fi
fi

echo ""
echo "==> Health check complete."
