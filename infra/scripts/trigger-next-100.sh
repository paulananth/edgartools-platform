#!/usr/bin/env bash
# Trigger bootstrap-recent-10 for the next 100 CIKs not yet loaded in Snowflake.
#
# Requirements:
#   - AWS credentials with stepfunctions:StartExecution on
#     edgartools-dev-bootstrap-recent-10
#   - Snowflake connector: pip install snowflake-connector-python
#   - Env vars: SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_ACCOUNT
#              (all three must be set; no defaults)
#   - EDGAR_USER_AGENT (e.g. "Your Name your.email@example.com")
#
# Usage (from Git Bash):
#   bash infra/scripts/trigger-next-100.sh
#
# Environment overrides:
#   SNOWFLAKE_DATABASE  (default EDGARTOOLS_DEV)
#   SNOWFLAKE_ROLE      (default ACCOUNTADMIN)
#   SNOWFLAKE_WAREHOUSE (default COMPUTE_WH)
#   STATE_MACHINE_ARN   (e.g. arn:aws:states:us-east-1:<your-aws-account-id>:stateMachine:edgartools-dev-bootstrap-recent-10)
#   BATCH_SIZE          (default 100)

set -euo pipefail

export SNOWFLAKE_ACCOUNT="${SNOWFLAKE_ACCOUNT:?SNOWFLAKE_ACCOUNT must be set (e.g. ORGNAME-ACCOUNTNAME)}"
export SNOWFLAKE_USER="${SNOWFLAKE_USER:?SNOWFLAKE_USER must be set}"
export SNOWFLAKE_PASSWORD="${SNOWFLAKE_PASSWORD:?SNOWFLAKE_PASSWORD must be set}"
export SNOWFLAKE_DATABASE="${SNOWFLAKE_DATABASE:=EDGARTOOLS_DEV}"
export SNOWFLAKE_ROLE="${SNOWFLAKE_ROLE:=ACCOUNTADMIN}"
export SNOWFLAKE_WAREHOUSE="${SNOWFLAKE_WAREHOUSE:=COMPUTE_WH}"
export STATE_MACHINE_ARN="${STATE_MACHINE_ARN:?STATE_MACHINE_ARN must be set (e.g. arn:aws:states:<region>:<account-id>:stateMachine:edgartools-<env>-bootstrap-recent-10)}"
export BATCH_SIZE="${BATCH_SIZE:=100}"
export EDGAR_USER_AGENT="${EDGAR_USER_AGENT:=EdgarTools dev@example.com}"

TMPDIR="${TEMP:-/tmp}"
CIK_FILE="$TMPDIR/next_ciks_$$.txt"
trap 'rm -f "$CIK_FILE"' EXIT

# Find a Python interpreter that has snowflake-connector-python installed.
PYTHON=""
for candidate in python python3 \
    "/c/Python314/python" "/c/Python313/python" "/c/Python312/python" \
    "$LOCALAPPDATA/Programs/Python/Python314/python" \
    "$LOCALAPPDATA/Programs/Python/Python313/python"; do
  if "$candidate" -c "import snowflake.connector" 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "ERROR: no Python with snowflake-connector-python found."
  echo "       Install with: pip install snowflake-connector-python"
  exit 1
fi
echo ">> Using Python: $PYTHON"

echo ">> Selecting next $BATCH_SIZE CIKs not yet loaded in $SNOWFLAKE_DATABASE.EDGARTOOLS_SOURCE.COMPANY"

"$PYTHON" - <<PY > "$CIK_FILE"
import os, json, urllib.request, snowflake.connector

conn = snowflake.connector.connect(
    account=os.environ['SNOWFLAKE_ACCOUNT'],
    user=os.environ['SNOWFLAKE_USER'],
    password=os.environ['SNOWFLAKE_PASSWORD'],
    role=os.environ['SNOWFLAKE_ROLE'],
    warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
)
cur = conn.cursor()
cur.execute(f"SELECT DISTINCT CIK FROM {os.environ['SNOWFLAKE_DATABASE']}.EDGARTOOLS_SOURCE.COMPANY")
loaded = {int(r[0]) for r in cur.fetchall()}
conn.close()

req = urllib.request.Request(
    'https://www.sec.gov/files/company_tickers_exchange.json',
    headers={'User-Agent': os.environ['EDGAR_USER_AGENT']},
)
data = json.loads(urllib.request.urlopen(req, timeout=30).read())
cik_idx = data['fields'].index('cik')
universe = sorted({int(r[cik_idx]) for r in data['data']})
batch_size = int(os.environ['BATCH_SIZE'])
new = [c for c in universe if c not in loaded][:batch_size]
if len(new) < batch_size:
    import sys
    print(f"WARNING: only {len(new)} unseeded CIKs remaining", file=sys.stderr)
print(','.join(str(c) for c in new))
PY

CIK_LIST="$(cat "$CIK_FILE")"
if [[ -z "$CIK_LIST" ]]; then
  echo "ERROR: no CIKs to load (universe may already be fully covered)"
  exit 1
fi

CIK_COUNT=$(awk -F',' '{print NF}' <<< "$CIK_LIST")
RUN_ID="next${CIK_COUNT}-$(date +%Y%m%d-%H%M%S)"

echo ">> Triggering $RUN_ID with $CIK_COUNT CIKs"
echo ">> First 3: $(cut -d',' -f1-3 <<< "$CIK_LIST")"
echo ">> Last 3:  $(awk -F',' '{print $(NF-2)","$(NF-1)","$NF}' <<< "$CIK_LIST")"

MSYS_NO_PATHCONV=1 aws stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name "$RUN_ID" \
  --input "{\"cik_list\":\"$CIK_LIST\"}"

_EXECUTION_ARN="${STATE_MACHINE_ARN/stateMachine:/execution:}:${RUN_ID}"
echo ""
echo ">> Monitor with:"
echo "   aws stepfunctions describe-execution \\"
echo "     --execution-arn ${_EXECUTION_ARN} \\"
echo "     --query 'status' --output text"
