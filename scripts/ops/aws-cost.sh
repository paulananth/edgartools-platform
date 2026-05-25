#!/usr/bin/env bash
# Show AWS cost from Cost Explorer for the current account.
#
# Usage:
#   ./scripts/ops/aws-cost.sh
#   ./scripts/ops/aws-cost.sh --days 14
#   ./scripts/ops/aws-cost.sh --month-to-date
#   ./scripts/ops/aws-cost.sh --group-by SERVICE
#   ./scripts/ops/aws-cost.sh --tag Environment=dev
#   ./scripts/ops/aws-cost.sh --watch 300
#
# Notes:
#   Cost Explorer data is usually delayed by several hours and may lag by a day.
#   This script is read-only. It calls ce:GetCostAndUsage.

set -euo pipefail

AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
CE_REGION="us-east-1"
AWS_PROFILE_ARG=""
DAYS=7
MONTH_TO_DATE=false
GROUP_BY="SERVICE"
METRIC="UnblendedCost"
WATCH_SECONDS=0
TAG_FILTER=""

usage() {
  sed -n '2,15p' "$0" | sed 's/^# //; s/^#//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)        AWS_REGION="${2:?}"; shift 2 ;;
    --ce-region)     CE_REGION="${2:?}"; shift 2 ;;
    --profile)       AWS_PROFILE_ARG="--profile ${2:?}"; shift 2 ;;
    --days)          DAYS="${2:?}"; shift 2 ;;
    --month-to-date) MONTH_TO_DATE=true; shift ;;
    --group-by)      GROUP_BY="${2:?}"; shift 2 ;;
    --metric)        METRIC="${2:?}"; shift 2 ;;
    --tag)           TAG_FILTER="${2:?}"; shift 2 ;;
    --watch)         WATCH_SECONDS="${2:?}"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! [[ "$DAYS" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: --days must be a positive integer" >&2
  exit 2
fi

if ! [[ "$WATCH_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "ERROR: --watch must be a non-negative integer" >&2
  exit 2
fi

case "$GROUP_BY" in
  SERVICE|LINKED_ACCOUNT|REGION|USAGE_TYPE|OPERATION|PURCHASE_TYPE|RECORD_TYPE|INSTANCE_TYPE|PLATFORM|TENANCY|LEGAL_ENTITY_NAME|DEPLOYMENT_OPTION|DATABASE_ENGINE|CACHE_ENGINE|INSTANCE_TYPE_FAMILY|BILLING_ENTITY|RESERVATION_ID|SAVINGS_PLANS_TYPE|SAVINGS_PLAN_ARN|OPERATING_SYSTEM)
    ;;
  NONE)
    ;;
  *)
    echo "ERROR: unsupported --group-by dimension: $GROUP_BY" >&2
    exit 2
    ;;
esac

aws_() { aws ${AWS_PROFILE_ARG} --region "$CE_REGION" "$@"; }
hr()   { printf '%.0s-' $(seq 1 72); echo; }

date_args() {
  python3 - "$DAYS" "$MONTH_TO_DATE" <<'PY'
from __future__ import annotations

from datetime import date, timedelta
import sys

days = int(sys.argv[1])
month_to_date = sys.argv[2].lower() == "true"

today = date.today()
end = today + timedelta(days=1)  # Cost Explorer end date is exclusive.
start = today.replace(day=1) if month_to_date else today - timedelta(days=days - 1)
label = "month-to-date" if month_to_date else f"last {days} days"

print(start.isoformat(), end.isoformat(), label)
PY
}

filter_arg() {
  if [[ -z "$TAG_FILTER" ]]; then
    return 0
  fi

  if [[ "$TAG_FILTER" != *=* ]]; then
    echo "ERROR: --tag must be KEY=VALUE" >&2
    exit 2
  fi

  local key="${TAG_FILTER%%=*}"
  local value="${TAG_FILTER#*=}"
  python3 - "$key" "$value" <<'PY'
import json
import sys

print(json.dumps({"Tags": {"Key": sys.argv[1], "Values": [sys.argv[2]]}}))
PY
}

cost_json() {
  local start_date="$1"
  local end_date="$2"
  local filter_json
  filter_json="$(filter_arg)"

  local args=(
    ce get-cost-and-usage
    --time-period "Start=${start_date},End=${end_date}"
    --granularity DAILY
    --metrics "$METRIC"
  )

  if [[ "$GROUP_BY" != "NONE" ]]; then
    args+=(--group-by "Type=DIMENSION,Key=${GROUP_BY}")
  fi

  if [[ -n "$filter_json" ]]; then
    args+=(--filter "$filter_json")
  fi

  aws_ "${args[@]}" --output json
}

render_costs() {
  local label="$1"
  local start_date="$2"
  local end_date="$3"
  local account_id="$4"
  local now_utc="$5"
  local cost_file="$6"

  python3 - "$label" "$start_date" "$end_date" "$account_id" "$now_utc" "$METRIC" "$GROUP_BY" "$TAG_FILTER" "$cost_file" <<'PY'
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
import json
import sys

label, start_date, end_date, account_id, now_utc, metric, group_by, tag_filter, cost_file = sys.argv[1:]
with open(cost_file, "r", encoding="utf-8") as fh:
    data = json.load(fh)

rows = data.get("ResultsByTime", [])
daily: list[tuple[str, Decimal, str]] = []
by_group: defaultdict[str, Decimal] = defaultdict(Decimal)
currency = "USD"

def money(value: str | None) -> Decimal:
    try:
        return Decimal(value or "0")
    except InvalidOperation:
        return Decimal("0")

for item in rows:
    day = item.get("TimePeriod", {}).get("Start", "?")
    groups = item.get("Groups") or []
    if groups:
        day_total = Decimal("0")
        for group in groups:
            key = ", ".join(group.get("Keys") or ["(none)"])
            amount_obj = group.get("Metrics", {}).get(metric, {})
            amount = money(amount_obj.get("Amount"))
            currency = amount_obj.get("Unit") or currency
            by_group[key] += amount
            day_total += amount
    else:
        amount_obj = item.get("Total", {}).get(metric, {})
        day_total = money(amount_obj.get("Amount"))
        currency = amount_obj.get("Unit") or currency
        by_group["TOTAL"] += day_total
    daily.append((day, day_total, currency))

total = sum((amount for _, amount, _ in daily), Decimal("0"))

print()
print("-" * 72)
print(f"  AWS COST  ·  account {account_id}  ·  {label}")
print("-" * 72)
print(f"  Generated : {now_utc}")
print(f"  Period    : {start_date} to {end_date} (end exclusive)")
print(f"  Metric    : {metric}")
if group_by != "NONE":
    print(f"  Group by  : {group_by}")
if tag_filter:
    print(f"  Filter    : tag {tag_filter}")
print()
print(f"  Total     : {total.quantize(Decimal('0.01'))} {currency}")
print()

print("DAILY")
for day, amount, unit in daily:
    print(f"  {day}  {amount.quantize(Decimal('0.01')):>10} {unit}")

if group_by != "NONE":
    print()
    print("TOP GROUPS")
    for key, amount in sorted(by_group.items(), key=lambda kv: kv[1], reverse=True)[:12]:
        print(f"  {amount.quantize(Decimal('0.01')):>10} {currency}  {key[:52]}")

print()
print("Note: Cost Explorer data is delayed and may not include the last several hours.")
PY
}

run_once() {
  local start_date end_date label account_id now_utc
  read -r start_date end_date label < <(date_args)
  account_id="$(aws_ sts get-caller-identity --query Account --output text)"
  now_utc="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local cost_file
  cost_file="$(mktemp "${TMPDIR:-/tmp}/aws-cost.XXXXXX.json")"
  if ! cost_json "$start_date" "$end_date" > "$cost_file"; then
    rm -f "$cost_file"
    echo "ERROR: Cost Explorer query failed. Confirm the account has Cost Explorer enabled and the caller has ce:GetCostAndUsage." >&2
    return 1
  fi
  render_costs "$label" "$start_date" "$end_date" "$account_id" "$now_utc" "$cost_file"
  rm -f "$cost_file"
}

if [[ "$WATCH_SECONDS" -eq 0 ]]; then
  run_once
else
  while true; do
    run_once
    echo "Refreshing every ${WATCH_SECONDS}s. Press Ctrl-C to stop."
    sleep "$WATCH_SECONDS"
  done
fi
