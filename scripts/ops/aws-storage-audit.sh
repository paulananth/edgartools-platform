#!/usr/bin/env bash
# Report S3 storage usage and durability/cost-relevant controls.
#
# Usage:
#   ./scripts/ops/aws-storage-audit.sh
#   ./scripts/ops/aws-storage-audit.sh --profile aws-admin-prod --bucket-prefix edgartools-prod-
#   ./scripts/ops/aws-storage-audit.sh --json
#   ./scripts/ops/aws-storage-audit.sh --watch 3600
#
# The script is read-only. S3 BucketSizeBytes and NumberOfObjects metrics are
# updated by AWS approximately once per day, so the report is not a live byte
# count. Missing lifecycle or replication configuration is reported explicitly.

set -euo pipefail

AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
AWS_CLI_TIMEOUT="${AWS_CLI_TIMEOUT:-10}"
BUCKET_PREFIX=""
WATCH_SECONDS=0
JSON_OUTPUT=false

usage() {
  sed -n '2,13p' "$0" | sed 's/^# //; s/^#//'
}

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || fail "--profile requires a value"
      AWS_PROFILE_NAME="$2"
      shift 2
      ;;
    --region)
      [[ $# -ge 2 ]] || fail "--region requires a value"
      AWS_REGION_NAME="$2"
      shift 2
      ;;
    --bucket-prefix)
      [[ $# -ge 2 ]] || fail "--bucket-prefix requires a value"
      BUCKET_PREFIX="$2"
      shift 2
      ;;
    --watch)
      [[ $# -ge 2 ]] || fail "--watch requires a value"
      WATCH_SECONDS="$2"
      shift 2
      ;;
    --json)
      JSON_OUTPUT=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ "$WATCH_SECONDS" =~ ^[0-9]+$ ]] || fail "--watch must be a non-negative integer"
command -v aws >/dev/null 2>&1 || fail "AWS CLI is not installed or not on PATH"

aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$AWS_REGION_NAME" \
      --cli-connect-timeout "$AWS_CLI_TIMEOUT" --cli-read-timeout "$AWS_CLI_TIMEOUT" "$@"
  else
    aws --region "$AWS_REGION_NAME" \
      --cli-connect-timeout "$AWS_CLI_TIMEOUT" --cli-read-timeout "$AWS_CLI_TIMEOUT" "$@"
  fi
}

account_id="$(aws_cli sts get-caller-identity --query Account --output text)" \
  || fail "AWS authentication failed"
[[ "$account_id" =~ ^[0-9]{12}$ ]] || fail "AWS returned an invalid account ID"

bucket_list() {
  if [[ -n "$BUCKET_PREFIX" ]]; then
    aws_cli s3api list-buckets \
      --query "Buckets[?starts_with(Name, '${BUCKET_PREFIX}')].Name" \
      --output text
  else
    aws_cli s3api list-buckets --query 'Buckets[].Name' --output text
  fi
}

metric() {
  local bucket="$1" metric_name="$2" storage_type="$3"
  local start_date end_date
  if date -u -v-7d '+%Y-%m-%dT00:00:00Z' >/dev/null 2>&1; then
    start_date="$(date -u -v-7d '+%Y-%m-%dT00:00:00Z')"
    end_date="$(date -u -v+1d '+%Y-%m-%dT00:00:00Z')"
  else
    start_date="$(date -u -d '7 days ago' '+%Y-%m-%dT00:00:00Z')"
    end_date="$(date -u -d tomorrow '+%Y-%m-%dT00:00:00Z')"
  fi
  aws_cli cloudwatch get-metric-statistics \
    --namespace AWS/S3 \
    --metric-name "$metric_name" \
    --dimensions "Name=BucketName,Value=${bucket}" "Name=StorageType,Value=${storage_type}" \
    --statistics Average \
    --period 86400 \
    --start-time "$start_date" \
    --end-time "$end_date" \
    --query 'Datapoints | sort_by(@, &Timestamp)[-1].Average' \
    --output text 2>/dev/null || true
}

setting() {
  local command_name="$1" bucket="$2"
  aws_cli s3api "$command_name" --bucket "$bucket" --output json 2>/dev/null || true
}

run_once() {
  local generated
  generated="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  local buckets
  buckets="$(bucket_list)" || fail "could not list S3 buckets"

  if [[ "$JSON_OUTPUT" == true ]]; then
    printf '{"account":"%s","region":"%s","generated":"%s","buckets":[' \
      "$account_id" "$AWS_REGION_NAME" "$generated"
  else
    echo "AWS STORAGE AUDIT"
    echo "Account: ${account_id}"
    echo "Region: ${AWS_REGION_NAME}"
    echo "Generated: ${generated}"
    [[ -n "$AWS_PROFILE_NAME" ]] && echo "Profile: ${AWS_PROFILE_NAME}"
    [[ -n "$BUCKET_PREFIX" ]] && echo "Bucket prefix: ${BUCKET_PREFIX}"
    echo "S3 metrics: latest daily CloudWatch datapoint (typically delayed)"
    echo
  fi

  local first=true bucket location versioning replication lifecycle public encryption bytes objects
  while read -r bucket; do
    [[ -n "$bucket" ]] || continue
    location="$(aws_cli s3api get-bucket-location --bucket "$bucket" --query LocationConstraint --output text 2>/dev/null || echo unknown)"
    [[ "$location" == "None" ]] && location="us-east-1"
    versioning="$(setting get-bucket-versioning "$bucket" | tr -d '\n' | sed -n 's/.*"Status"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    [[ -n "$versioning" ]] || versioning="Disabled/unknown"
    replication="$(setting get-bucket-replication "$bucket" | tr -d '\n' | sed -n 's/.*"Rules"[[:space:]]*:[[:space:]]*\[.*/configured/p')"
    [[ -n "$replication" ]] || replication="none"
    lifecycle="$(setting get-bucket-lifecycle-configuration "$bucket" | tr -d '\n' | sed -n 's/.*"Rules"[[:space:]]*:[[:space:]]*\[.*/configured/p')"
    [[ -n "$lifecycle" ]] || lifecycle="none"
    public="$(setting get-public-access-block "$bucket" | tr -d '\n' | sed -n 's/.*"BlockPublicAcls"[[:space:]]*:[[:space:]]*true.*/blocked/p')"
    [[ -n "$public" ]] || public="not-confirmed"
    encryption="$(setting get-bucket-encryption "$bucket" | tr -d '\n' | sed -n 's/.*"SSEAlgorithm"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
    [[ -n "$encryption" ]] || encryption="not-confirmed"
    bytes="$(metric "$bucket" BucketSizeBytes StandardStorage)"
    objects="$(metric "$bucket" NumberOfObjects AllStorageTypes)"
    [[ "$bytes" == "None" || -z "$bytes" ]] && bytes="unknown"
    [[ "$objects" == "None" || -z "$objects" ]] && objects="unknown"

    if [[ "$JSON_OUTPUT" == true ]]; then
      [[ "$first" == true ]] || printf ','
      first=false
      printf '{"name":"%s","location":"%s","versioning":"%s","replication":"%s","lifecycle":"%s","public_access":"%s","encryption":"%s","bytes":"%s","objects":"%s"}' \
        "$bucket" "$location" "$versioning" "$replication" "$lifecycle" "$public" "$encryption" "$bytes" "$objects"
    else
      echo "Bucket: ${bucket}"
      echo "  location=${location} versioning=${versioning} replication=${replication} lifecycle=${lifecycle}"
      echo "  public_access=${public} encryption=${encryption} bytes=${bytes} objects=${objects}"
      echo
    fi
  done <<< "$buckets"

  if [[ "$JSON_OUTPUT" == true ]]; then
    echo ']}'
  fi
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
