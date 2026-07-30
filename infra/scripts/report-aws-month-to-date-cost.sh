#!/usr/bin/env bash
# Report AWS month-to-date charges, applied credits, and remaining credit balance.

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  report-aws-month-to-date-cost.sh [options]

Reports the authenticated AWS account's month-to-date usage charges, credits
applied, estimated net cost, and remaining promotional-credit balance.

Options:
  --aws-profile <profile>  AWS CLI profile. Default: AWS_PROFILE or normal AWS CLI resolution.
  --aws-region <region>    AWS Billing/Cost Explorer region. Default: us-east-1.
  -h, --help               Show this help.

The script is read-only. AWS Cost Explorer data is estimated and can lag by
approximately 24 hours. Querying the exact credit balance requires IAM access
to Billing to be activated by the AWS account root user.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile)
      [[ $# -ge 2 ]] || fail "--aws-profile requires a value"
      AWS_PROFILE_NAME="$2"
      shift 2
      ;;
    --aws-region)
      [[ $# -ge 2 ]] || fail "--aws-region requires a value"
      AWS_REGION_NAME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v aws >/dev/null 2>&1 || fail "AWS CLI is not installed or not on PATH"

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" "$@"
  else
    aws --region "$AWS_REGION_NAME" "$@"
  fi
}

month_start_utc() {
  if date -u -v1d '+%Y-%m-%d' >/dev/null 2>&1; then
    date -u -v1d '+%Y-%m-%d'
  else
    date -u -d "$(date -u '+%Y-%m-01')" '+%Y-%m-%d'
  fi
}

tomorrow_utc() {
  if date -u -v+1d '+%Y-%m-%d' >/dev/null 2>&1; then
    date -u -v+1d '+%Y-%m-%d'
  else
    date -u -d tomorrow '+%Y-%m-%d'
  fi
}

ACCOUNT_ID="$(
  aws_cli sts get-caller-identity \
    --query Account \
    --output text
)" || fail "AWS authentication failed"

[[ "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]] || fail "AWS returned an invalid account ID"

START_DATE="$(month_start_utc)"
END_DATE="$(tomorrow_utc)"

echo "AWS account: ${ACCOUNT_ID}"
if [[ -n "$AWS_PROFILE_NAME" ]]; then
  echo "AWS profile: ${AWS_PROFILE_NAME}"
fi
echo "Cost period: ${START_DATE} through today (UTC)"
echo

if ! COST_LINES="$(
  aws_cli ce get-cost-and-usage \
    --time-period "Start=${START_DATE},End=${END_DATE}" \
    --granularity MONTHLY \
    --metrics UnblendedCost \
    --group-by Type=DIMENSION,Key=RECORD_TYPE \
    --query 'ResultsByTime[0].Groups[].[Keys[0],Metrics.UnblendedCost.Amount]' \
    --output text
)"; then
  fail "Cost Explorer query failed; verify ce:GetCostAndUsage permission"
fi

read -r USAGE_COST CREDIT_AMOUNT NET_COST < <(
  awk '
    {
      record_type = $1
      amount = $2 + 0
      net += amount
      if (record_type == "Usage" || record_type == "DiscountedUsage") {
        usage += amount
      }
      if (record_type == "Credit") {
        credits += -amount
      }
    }
    END {
      printf "%.10f %.10f %.10f\n", usage, credits, net
    }
  ' <<<"$COST_LINES"
)

printf "Month-to-date usage:  USD %'.2f\n" "$USAGE_COST"
printf "Credits applied:      USD %'.2f\n" "$CREDIT_AMOUNT"
printf "Estimated net cost:   USD %'.2f\n" "$NET_COST"
echo

# AWS limits GetCredits start-date to no more than one year in the past.
CREDIT_QUERY_START_EPOCH="$(( $(date -u '+%s') - 31500000 ))"
CREDIT_ERROR_FILE="$(mktemp)"
trap 'rm -f "$CREDIT_ERROR_FILE"' EXIT

if CREDIT_LINES="$(
  aws_cli billing get-credits \
    --account-id "$ACCOUNT_ID" \
    --start-date "$CREDIT_QUERY_START_EPOCH" \
    --query "credits[?creditStatus == 'ENABLED'].[remainingAmount.currencyAmount,estimatedAmount.currencyAmount,endDate]" \
    --output text 2>"$CREDIT_ERROR_FILE"
)"; then
  if [[ -z "$CREDIT_LINES" || "$CREDIT_LINES" == "None" ]]; then
    echo "Remaining enabled credit: USD 0.00"
  else
    read -r REMAINING_CREDIT ESTIMATED_CREDIT < <(
      awk '
        {
          remaining = ($1 == "None" ? 0 : $1 + 0)
          estimated = ($2 == "None" ? remaining : $2 + 0)
          remaining_total += remaining
          estimated_total += estimated
        }
        END {
          printf "%.10f %.10f\n", remaining_total, estimated_total
        }
      ' <<<"$CREDIT_LINES"
    )
    printf "Remaining credit:           USD %'.2f\n" "$REMAINING_CREDIT"
    printf "Estimated available credit: USD %'.2f (includes in-flight charges)\n" "$ESTIMATED_CREDIT"
  fi
else
  if grep -q "IAM user access not activated" "$CREDIT_ERROR_FILE"; then
    echo "Remaining credit: unavailable"
    echo "AWS denied the credit-balance query because IAM access to Billing is not activated."
    echo "Sign in as the AWS account root user, activate IAM access to Billing, then rerun this script."
  else
    echo "Remaining credit: unavailable"
    echo "AWS Billing API error:" >&2
    sed 's/^/  /' "$CREDIT_ERROR_FILE" >&2
  fi
fi
