#!/usr/bin/env bash
# Run the full phased bootstrap pipeline for the next batch of companies.
#
# Usage:
#   bash scripts/run-bootstrap.sh [--aws-profile <profile>] [--window-size N] [--watch] [--no-wait]
#
#   --aws-profile <profile>   AWS CLI named profile (SSO or key-based).
#                             If credentials have expired, sso login is attempted
#                             automatically for SSO profiles.
#   --window-size N           Number of CIKs per bootstrap-next window (default: 500).
#                             Passed as {"window_size": N} in the SM input JSON.
#   --watch                   Stream a spinner + elapsed time until completion.
#   --no-wait                 Fire the execution and exit immediately.
#
# What it does (4 stages, ~15 min for 100 companies):
#   1. seed-universe          — enrols bootstrap_pending CIKs into MDM
#   2. bootstrap-batch x10 concurrent — fetch SEC filings → bronze + silver
#   3. mdm run → backfill-relationships → sync-graph (Neo4j) → verify-graph
#   4. gold-refresh           — builds all gold tables + Snowflake export manifest
#
# Secrets required in AWS Secrets Manager before running:
#   edgartools-dev-edgar-identity   SEC API User-Agent email (plain string)
#   edgartools-dev/mdm/postgres_dsn MDM Postgres connection string
#   edgartools-dev/mdm/neo4j        {"uri":"...","user":"...","password":"..."}

set -euo pipefail

REGION="us-east-1"
NAME_PREFIX="edgartools-dev"

EDGAR_IDENTITY_SECRET="${NAME_PREFIX}-edgar-identity"
POSTGRES_DSN_SECRET="${NAME_PREFIX}/mdm/postgres_dsn"
NEO4J_SECRET="${NAME_PREFIX}/mdm/neo4j"

AWS_PROFILE_NAME=""
WINDOW_SIZE=500
WATCH=false
NO_WAIT=false

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-profile)  AWS_PROFILE_NAME="${2:?'--aws-profile requires a value'}"; shift 2 ;;
    --window-size)
      WINDOW_SIZE="${2:?'--window-size requires a value'}"
      if ! [[ "$WINDOW_SIZE" =~ ^[0-9]+$ ]] || [[ "$WINDOW_SIZE" -le 0 ]]; then
        echo "ERROR: --window-size must be a positive integer (got: $WINDOW_SIZE)" >&2
        exit 1
      fi
      shift 2 ;;
    --watch)        WATCH=true;  shift ;;
    --no-wait)      NO_WAIT=true; shift ;;
    -h|--help)
      sed -n '2,23p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) shift ;;
  esac
done

# ---------------------------------------------------------------------------
# AWS CLI wrapper
# ---------------------------------------------------------------------------
aws_cli() {
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    aws --profile "$AWS_PROFILE_NAME" --region "$REGION" "$@"
  else
    aws --region "$REGION" "$@"
  fi
}

# Resolve account ID — must come after aws_cli is defined so --profile is applied
ACCOUNT=$(aws_cli sts get-caller-identity --query 'Account' --output text 2>/dev/null || true)
STATE_MACHINE_ARN="arn:aws:states:${REGION}:${ACCOUNT}:stateMachine:${NAME_PREFIX}-load-history"

# ---------------------------------------------------------------------------
# PREFLIGHT: resolve all credentials before touching the pipeline
# ---------------------------------------------------------------------------
echo "━━━ PREFLIGHT ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
PREFLIGHT_ERRORS=0

# 1. AWS credentials
printf "  AWS credentials  ... "
if ! aws_cli sts get-caller-identity --query 'Account' --output text >/dev/null 2>&1; then
  if [[ -n "$AWS_PROFILE_NAME" ]]; then
    printf "expired — attempting SSO login\n"
    aws sso login --profile "$AWS_PROFILE_NAME"
    if ! aws_cli sts get-caller-identity --query 'Account' --output text >/dev/null 2>&1; then
      echo "  ERROR: credentials still unavailable after SSO login" >&2
      PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
    fi
  else
    printf "MISSING\n"
    echo "  ERROR: no active AWS credentials — use --aws-profile or configure default credentials" >&2
    PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
  fi
fi

if [[ $PREFLIGHT_ERRORS -eq 0 ]]; then
  ACCOUNT=$(aws_cli sts get-caller-identity --query 'Account' --output text)
  printf "OK (account %s)\n" "$ACCOUNT"
fi

# 2. EDGAR identity secret — needed by every bronze ECS task (User-Agent header)
printf "  EDGAR identity   ... "
EDGAR_VAL=$(aws_cli secretsmanager get-secret-value \
  --secret-id "$EDGAR_IDENTITY_SECRET" \
  --query 'SecretString' --output text 2>/dev/null || true)

if [[ -z "$EDGAR_VAL" || "$EDGAR_VAL" == "None" ]]; then
  printf "MISSING\n"
  echo "  ERROR: secret '$EDGAR_IDENTITY_SECRET' is empty." >&2
  echo "  Fix:   aws --region $REGION secretsmanager put-secret-value \\" >&2
  echo "           --secret-id $EDGAR_IDENTITY_SECRET \\" >&2
  echo "           --secret-string 'your.email@example.com'" >&2
  PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
elif [[ "$EDGAR_VAL" != *"@"* ]]; then
  printf "INVALID\n"
  echo "  ERROR: EDGAR identity must be an email address (got: $EDGAR_VAL)" >&2
  PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
else
  printf "OK (%s)\n" "$EDGAR_VAL"
fi

# 3. MDM Postgres DSN secret — needed by all MDM ECS tasks (stages 2-3)
printf "  MDM Postgres DSN ... "
PG_VAL=$(aws_cli secretsmanager get-secret-value \
  --secret-id "$POSTGRES_DSN_SECRET" \
  --query 'SecretString' --output text 2>/dev/null || true)

if [[ -z "$PG_VAL" || "$PG_VAL" == "None" ]]; then
  printf "MISSING\n"
  echo "  ERROR: secret '$POSTGRES_DSN_SECRET' is empty." >&2
  echo "  Fix:   aws --region $REGION secretsmanager put-secret-value \\" >&2
  echo "           --secret-id $POSTGRES_DSN_SECRET \\" >&2
  echo "           --secret-string 'postgresql://user:pass@host:5432/edgartools'" >&2
  PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
else
  # Show host only, not the password
  PG_HOST=$(echo "$PG_VAL" | sed 's|.*@||' | sed 's|/.*||')
  printf "OK (host: %s)\n" "$PG_HOST"
fi

# 4. Neo4j secret — needed by mdm-sync-graph (stage 3)
printf "  Neo4j            ... "
NEO4J_VAL=$(aws_cli secretsmanager get-secret-value \
  --secret-id "$NEO4J_SECRET" \
  --query 'SecretString' --output text 2>/dev/null || true)

if [[ -z "$NEO4J_VAL" || "$NEO4J_VAL" == "None" ]]; then
  printf "MISSING\n"
  echo "  ERROR: secret '$NEO4J_SECRET' is empty." >&2
  echo "  Fix:   aws --region $REGION secretsmanager put-secret-value \\" >&2
  echo "           --secret-id $NEO4J_SECRET \\" >&2
  echo "           --secret-string '{\"uri\":\"neo4j+s://<id>.databases.neo4j.io\",\"user\":\"<user>\",\"password\":\"<pass>\"}'" >&2
  echo "  See:   docs/neo4j.md" >&2
  PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
else
  NEO4J_MISSING_KEYS=()
  for key in uri user password; do
    echo "$NEO4J_VAL" | grep -q "\"$key\"" || NEO4J_MISSING_KEYS+=("$key")
  done
  if [[ ${#NEO4J_MISSING_KEYS[@]} -gt 0 ]]; then
    printf "INVALID\n"
    echo "  ERROR: Neo4j secret missing keys: ${NEO4J_MISSING_KEYS[*]}" >&2
    echo "  Expected: {\"uri\":\"...\",\"user\":\"...\",\"password\":\"...\"}" >&2
    PREFLIGHT_ERRORS=$(( PREFLIGHT_ERRORS + 1 ))
  else
    NEO4J_HOST=$(echo "$NEO4J_VAL" | grep -o '"uri":"[^"]*"' | sed 's/"uri":"//;s/"//')
    printf "OK (%s)\n" "$NEO4J_HOST"
  fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ $PREFLIGHT_ERRORS -gt 0 ]]; then
  echo ""
  echo "ABORTED: $PREFLIGHT_ERRORS preflight check(s) failed. Fix the issues above and re-run." >&2
  exit 1
fi

echo ""

# ---------------------------------------------------------------------------
# Fire the Step Function
# ---------------------------------------------------------------------------
RUN_NAME="${NAME_PREFIX}-bootstrap-$(date -u +%Y%m%d-%H%M%S)"
echo "Starting load-history: $RUN_NAME  (window_size=$WINDOW_SIZE)"

SM_INPUT="$(printf '{"window_size": %d}' "$WINDOW_SIZE")"
EXEC_ARN=$(aws_cli stepfunctions start-execution \
  --state-machine-arn "$STATE_MACHINE_ARN" \
  --name "$RUN_NAME" \
  --input "$SM_INPUT" \
  --query 'executionArn' --output text)

echo "Execution ARN: $EXEC_ARN"
echo ""
echo "Monitor in AWS console:"
echo "  https://$REGION.console.aws.amazon.com/states/home?region=$REGION#/executions/details/$EXEC_ARN"
echo ""

if $NO_WAIT; then
  echo "Fired. Check status with:"
  echo "  aws --region $REGION stepfunctions describe-execution --execution-arn '$EXEC_ARN' --query status --output text"
  exit 0
fi

echo "Waiting for completion (Ctrl-C to stop watching, pipeline continues in AWS)..."
echo ""

SPINNER=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
i=0
START=$(date +%s)

while true; do
  STATUS=$(aws_cli stepfunctions describe-execution \
    --execution-arn "$EXEC_ARN" \
    --query 'status' --output text 2>/dev/null || echo "UNKNOWN")

  ELAPSED=$(( $(date +%s) - START ))
  MINS=$(( ELAPSED / 60 ))
  SECS=$(( ELAPSED % 60 ))

  if $WATCH; then
    printf "\r${SPINNER[$i]} %s  elapsed: %dm%02ds  " "$STATUS" "$MINS" "$SECS"
    i=$(( (i+1) % ${#SPINNER[@]} ))
  fi

  case "$STATUS" in
    SUCCEEDED)
      echo ""
      echo "SUCCEEDED in ${MINS}m${SECS}s"
      echo "Snowflake gold tables will refresh within 1 minute."
      exit 0
      ;;
    FAILED|TIMED_OUT|ABORTED)
      echo ""
      echo "Pipeline $STATUS after ${MINS}m${SECS}s"
      echo ""
      CAUSE=$(aws_cli stepfunctions describe-execution \
        --execution-arn "$EXEC_ARN" \
        --query 'cause' --output text 2>/dev/null || true)
      [[ -n "$CAUSE" ]] && echo "Cause: $CAUSE"
      echo ""
      echo "Get full history:"
      echo "  aws --region $REGION stepfunctions get-execution-history --execution-arn '$EXEC_ARN' --query 'events[-20:]'"
      exit 1
      ;;
    RUNNING)
      if ! $WATCH; then
        echo "  [$STATUS]  ${MINS}m${SECS}s elapsed"
      fi
      ;;
  esac

  sleep 30
done
