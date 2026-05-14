#!/usr/bin/env bash
# Download silver.duckdb from S3 and print row counts for all key tables.
# Confirms artifact pipeline populated sec_raw_object, sec_filing_attachment,
# sec_parse_run, sec_ownership_reporting_owner before triggering MDM.
#
# Usage:
#   ./scripts/ops/silver-counts.sh
#   ./scripts/ops/silver-counts.sh --env dev
#   ./scripts/ops/silver-counts.sh --local /tmp/silver.duckdb   # skip download

set -euo pipefail

ENVIRONMENT="dev"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_PROFILE_ARG=""
LOCAL_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)     ENVIRONMENT="${2:?}"; shift 2 ;;
    --region)  AWS_REGION="${2:?}"; shift 2 ;;
    --profile) AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --local)   LOCAL_PATH="${2:?}"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

NAME_PREFIX="edgartools-${ENVIRONMENT}"
aws_() { aws ${AWS_PROFILE_ARG} --region "$AWS_REGION" "$@"; }
hr() { printf '%.0s─' $(seq 1 60); echo; }

WAREHOUSE_BUCKET=$(python3 -c "
import json
m = json.load(open('infra/aws-${ENVIRONMENT}-application.json'))
print(m.get('warehouse_bucket_name',''))
" 2>/dev/null || echo "${NAME_PREFIX}-warehouse-$(aws_ sts get-caller-identity --query Account --output text 2>/dev/null)")

S3_URI="s3://${WAREHOUSE_BUCKET}/warehouse/silver/sec/silver.duckdb"

if [[ -z "$LOCAL_PATH" ]]; then
  LOCAL_PATH="/tmp/silver-${ENVIRONMENT}.duckdb"
  echo "Downloading silver.duckdb from ${S3_URI} ..."
  aws_ s3 cp "$S3_URI" "$LOCAL_PATH" 2>&1 | tail -1
fi

if [[ ! -f "$LOCAL_PATH" ]]; then
  echo "ERROR: file not found: $LOCAL_PATH" >&2
  exit 1
fi

SIZE=$(du -h "$LOCAL_PATH" | cut -f1)
echo "File: ${LOCAL_PATH}  (${SIZE})"
echo ""

uv run python3 - "$LOCAL_PATH" << 'EOF'
import sys
import duckdb

path = sys.argv[1]
conn = duckdb.connect(path, read_only=True)

hr = lambda: print("─" * 60)

def count(table):
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except Exception as e:
        return f"ERR: {e}"

# ── Bronze / raw layer ────────────────────────────────────────────────────────
hr()
print("  BRONZE / RAW")
hr()
for t in ["sec_raw_object", "sec_filing_attachment", "sec_parse_run"]:
    n = count(t)
    icon = "✓" if isinstance(n, int) and n > 0 else ("·" if n == 0 else "✗")
    print(f"  {icon}  {t:<40s} {n:>10}")

# ── Ownership ─────────────────────────────────────────────────────────────────
print()
hr()
print("  OWNERSHIP")
hr()
for t in [
    "sec_ownership_reporting_owner",
    "sec_ownership_non_derivative_txn",
    "sec_ownership_derivative_txn",
]:
    n = count(t)
    icon = "✓" if isinstance(n, int) and n > 0 else ("·" if n == 0 else "✗")
    print(f"  {icon}  {t:<40s} {n:>10}")

# ── ADV (Adviser) ─────────────────────────────────────────────────────────────
print()
hr()
print("  ADVISER (ADV)")
hr()
for t in ["sec_adv_filing", "sec_adv_office", "sec_adv_disclosure_event", "sec_adv_private_fund"]:
    n = count(t)
    icon = "✓" if isinstance(n, int) and n > 0 else ("·" if n == 0 else "✗")
    print(f"  {icon}  {t:<40s} {n:>10}")

# ── Company / filing ──────────────────────────────────────────────────────────
print()
hr()
print("  COMPANY / FILING")
hr()
for t in ["sec_company", "sec_company_filing", "sec_company_sync_state"]:
    n = count(t)
    icon = "✓" if isinstance(n, int) and n > 0 else "·"
    print(f"  {icon}  {t:<40s} {n:>10}")

# ── Sync runs ─────────────────────────────────────────────────────────────────
print()
hr()
print("  SYNC RUN HISTORY")
hr()
try:
    rows = conn.execute("""
        SELECT command, status, count(*) AS n
        FROM sec_sync_run
        GROUP BY command, status
        ORDER BY command, status
    """).fetchall()
    for r in rows:
        print(f"  {r[2]:>6}  {r[0]:<30s}  {r[1]}")
except Exception as e:
    print(f"  ERR: {e}")

# ── Company tracking status breakdown ─────────────────────────────────────────
print()
hr()
print("  TRACKING STATUS BREAKDOWN")
hr()
try:
    rows = conn.execute("""
        SELECT tracking_status, count(*) AS n
        FROM sec_company_sync_state
        GROUP BY tracking_status
        ORDER BY n DESC
    """).fetchall()
    for r in rows:
        print(f"  {r[1]:>8}  {r[0]}")
except Exception as e:
    print(f"  ERR: {e}")

print()
hr()
conn.close()
EOF
