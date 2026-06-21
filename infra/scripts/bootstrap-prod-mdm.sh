#!/usr/bin/env bash
# bootstrap-prod-mdm.sh
#
# One-click provisioning for the Snowflake-hosted Postgres MDM runtime: rotates
# both Postgres credentials, creates/migrates the `mdm` database, grants the
# application role its runtime privileges, populates the two AWS Secrets
# Manager secrets the warehouse runtime reads (`<prefix>/mdm/postgres_dsn` and
# `<prefix>/mdm/snowflake`), and verifies connectivity end to end.
#
# Every credential this script handles (snowflake_admin and application
# passwords) is held only in-process for the duration of a single Python
# invocation and is never written to a file, an environment variable that
# outlives that invocation, or stdout/stderr. Each step that emits a
# credential pipes directly into its consumer within one process — do not
# split these steps when editing this script, or a credential will surface
# in an intermediate log line.
#
# Rotation is unconditional on every run: a credential that is never displayed
# is still gone the moment a later rotation overwrites it (Snowflake-hosted
# Postgres has no credential-recovery path). Re-running this script is safe
# (each step is idempotent on the database/schema side) but always issues
# fresh Postgres passwords.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-prod-mdm.sh --env <dev|prod> --snow-connection <name> --instance-name <NAME> [options]

Required:
  --env <dev|prod>              Environment. Selects AWS secret/name prefix default.
  --snow-connection <name>      SnowCLI connection name (e.g. edgartools-prod).
  --instance-name <NAME>        Snowflake Postgres instance name (e.g. EDGARTOOLS_PROD_MDM).

Options:
  --aws-profile <profile>       AWS CLI profile. Default: AWS_PROFILE env var or instance role.
  --aws-region <region>         AWS region. Default: us-east-1.
  --name-prefix <prefix>        Resource prefix. Default: edgartools-<env>.
  --database <name>             MDM Postgres database name. Default: mdm.
  --gold-schema <name>          Snowflake schema for the mdm/snowflake secret. Default: EDGARTOOLS_GOLD.
  --skip-snowflake-secret       Do not touch <prefix>/mdm/snowflake (postgres_dsn only).
  --dry-run                    Resolve host/instance state and print the plan; rotate/write nothing.
  -h, --help                    Show this help.

Reads (non-secret, informational only):
  - Postgres instance host via `snow sql --connection <name> -q "DESCRIBE POSTGRES INSTANCE <NAME>"`

Writes:
  - <prefix>/mdm/postgres_dsn   (always)
  - <prefix>/mdm/snowflake      (unless --skip-snowflake-secret)

Requires on PATH: snow, aws, jq, uv (with the mdm-runtime extra installed), python3 with psycopg2.
USAGE
}

ENVIRONMENT=""
SNOW_CONNECTION=""
INSTANCE_NAME=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
NAME_PREFIX=""
DATABASE="mdm"
GOLD_SCHEMA="EDGARTOOLS_GOLD"
SKIP_SNOWFLAKE_SECRET=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --instance-name) INSTANCE_NAME="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --database) DATABASE="${2:?}"; shift 2 ;;
    --gold-schema) GOLD_SCHEMA="${2:?}"; shift 2 ;;
    --skip-snowflake-secret) SKIP_SNOWFLAKE_SECRET=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { echo "ERROR: --env must be dev or prod" >&2; usage >&2; exit 2; }
[[ -n "$SNOW_CONNECTION" ]] || { echo "ERROR: --snow-connection is required" >&2; exit 2; }
[[ -n "$INSTANCE_NAME" ]] || { echo "ERROR: --instance-name is required" >&2; exit 2; }
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"

log() { echo "==> $*" >&2; }
fail() { echo "ERROR: $*" >&2; exit 1; }

aws_cli() {
  local args=()
  [[ -n "$AWS_PROFILE_NAME" ]] && args+=(--profile "$AWS_PROFILE_NAME")
  aws "${args[@]}" --region "$AWS_REGION_NAME" "$@"
}

log "Resolving Postgres instance state for ${INSTANCE_NAME} via ${SNOW_CONNECTION}"
INSTANCE_JSON="$(snow sql --connection "$SNOW_CONNECTION" --format json -q "DESCRIBE POSTGRES INSTANCE ${INSTANCE_NAME}" 2>/dev/null)"
HOST="$(echo "$INSTANCE_JSON" | python3 -c "import json,sys; rows=json.load(sys.stdin); print(next(r['value'] for r in rows if r.get('property')=='host'))")"
STATE="$(echo "$INSTANCE_JSON" | python3 -c "import json,sys; rows=json.load(sys.stdin); print(next(r['value'] for r in rows if r.get('property')=='state'))")"
[[ "$STATE" == "READY" ]] || fail "Postgres instance ${INSTANCE_NAME} is not READY (state=${STATE})"
log "Instance READY. host=${HOST}"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN — would rotate snowflake_admin + application, create/migrate '${DATABASE}', write secrets:"
  log "  ${NAME_PREFIX}/mdm/postgres_dsn"
  [[ "$SKIP_SNOWFLAKE_SECRET" == "true" ]] || log "  ${NAME_PREFIX}/mdm/snowflake (schema=${GOLD_SCHEMA})"
  exit 0
fi

ADMIN_PY="$(mktemp)"
APP_PY="$(mktemp)"
trap 'rm -f "$ADMIN_PY" "$APP_PY"' EXIT

cat > "$ADMIN_PY" <<'PYEOF'
import json, os, re, subprocess, sys, time
from urllib.parse import quote_plus

import psycopg2

def find_password(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() == "password" and isinstance(v, str) and v:
                return v
            found = find_password(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_password(item)
            if found:
                return found
    return None

data = json.load(sys.stdin)
pw = find_password(data)
if not pw:
    sys.exit("NO_PASSWORD_FOUND_IN_ROTATION_OUTPUT")

host = os.environ["HOST"]
database = os.environ["DATABASE"]
repo_root = os.environ["REPO_ROOT"]

def connect(dbname, retries=8, delay=5):
    last_err = None
    for _ in range(retries):
        try:
            return psycopg2.connect(
                host=host, port=5432, dbname=dbname, user="snowflake_admin",
                password=pw, sslmode="require", connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(delay)
    raise SystemExit(f"CONNECT_FAILED_AFTER_RETRIES: {type(last_err).__name__}")

conn = connect("postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
if cur.fetchone() is None:
    cur.execute(f'CREATE DATABASE "{database}"')
    print(f"DATABASE_CREATED: {database}", file=sys.stderr)
else:
    print(f"DATABASE_ALREADY_EXISTS: {database}", file=sys.stderr)
cur.close()
conn.close()

admin_dsn = f"postgresql://snowflake_admin:{quote_plus(pw)}@{host}:5432/{database}?sslmode=require"
env = dict(os.environ)
env["MDM_DATABASE_URL"] = admin_dsn
result = subprocess.run(
    ["uv", "run", "--project", repo_root, "--extra", "mdm-runtime", "edgar-warehouse", "mdm", "migrate"],
    env=env, capture_output=True, text=True,
)
admin_dsn = None
env = None
out = re.sub(r"(postgresql://)[^@]+@", r"\1<redacted>@", result.stdout + result.stderr)
out = re.sub(r'"password"\s*:\s*"[^"]*"', '"password": "<redacted>"', out)
print(out[-2000:], file=sys.stderr)
if result.returncode != 0:
    sys.exit(f"MIGRATE_FAILED_RC_{result.returncode}")

conn = connect(database)
conn.autocommit = True
cur = conn.cursor()
for stmt in [
    "GRANT CONNECT ON DATABASE %s TO application;" % database,
    "GRANT USAGE ON SCHEMA public TO application;",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO application;",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO application;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO application;",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO application;",
]:
    cur.execute(stmt)
cur.close()
conn.close()
pw = None
print("ADMIN_PROVISIONING_COMPLETE", file=sys.stderr)
PYEOF

cat > "$APP_PY" <<'PYEOF'
import json, sys

def find_password(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() == "password" and isinstance(v, str) and v:
                return v
            found = find_password(v)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_password(item)
            if found:
                return found
    return None

data = json.load(sys.stdin)
pw = find_password(data)
if not pw:
    sys.exit("NO_PASSWORD_FOUND_IN_ROTATION_OUTPUT")
sys.stdout.write(pw)
PYEOF

log "Rotating snowflake_admin access and ensuring database '${DATABASE}' exists + is migrated"
snow sql --connection "$SNOW_CONNECTION" --format json -q "ALTER POSTGRES INSTANCE ${INSTANCE_NAME} RESET ACCESS FOR 'snowflake_admin';" 2>/dev/null \
  | DATABASE="$DATABASE" HOST="$HOST" REPO_ROOT="$REPO_ROOT" uv run --project "$REPO_ROOT" --extra mdm-runtime python3 "$ADMIN_PY"

log "Rotating application access and writing ${NAME_PREFIX}/mdm/postgres_dsn"
snow sql --connection "$SNOW_CONNECTION" --format json -q "ALTER POSTGRES INSTANCE ${INSTANCE_NAME} RESET ACCESS FOR 'application';" 2>/dev/null \
  | python3 "$APP_PY" \
  | bash "$SCRIPT_DIR/bootstrap-aws-mdm-secrets.sh" \
    --env "$ENVIRONMENT" \
    --aws-profile "$AWS_PROFILE_NAME" \
    --aws-region "$AWS_REGION_NAME" \
    --name-prefix "$NAME_PREFIX" \
    --host "$HOST" \
    --username application \
    --database "$DATABASE" \
    --password-stdin

if [[ "$SKIP_SNOWFLAKE_SECRET" != "true" ]]; then
  log "Populating ${NAME_PREFIX}/mdm/snowflake from ${NAME_PREFIX}/dbt/snowflake"
  aws_cli secretsmanager get-secret-value \
      --secret-id "${NAME_PREFIX}/dbt/snowflake" \
      --query SecretString --output text \
    | jq --arg schema "$GOLD_SCHEMA" '{
        MDM_SNOWFLAKE_ACCOUNT: .DBT_SNOWFLAKE_ACCOUNT,
        MDM_SNOWFLAKE_USER: .DBT_SNOWFLAKE_USER,
        MDM_SNOWFLAKE_PASSWORD: .DBT_SNOWFLAKE_PASSWORD,
        MDM_SNOWFLAKE_WAREHOUSE: .DBT_SNOWFLAKE_WAREHOUSE,
        MDM_SNOWFLAKE_DATABASE: .DBT_SNOWFLAKE_DATABASE,
        MDM_SNOWFLAKE_SCHEMA: $schema,
        MDM_SNOWFLAKE_ROLE: .DBT_SNOWFLAKE_ROLE
      }' \
    | aws_cli secretsmanager put-secret-value \
        --secret-id "${NAME_PREFIX}/mdm/snowflake" \
        --secret-string file:///dev/stdin >/dev/null
fi

log "Verifying connectivity via the application credential"
MDM_DATABASE_URL="$(aws_cli secretsmanager get-secret-value --secret-id "${NAME_PREFIX}/mdm/postgres_dsn" --query SecretString --output text)" \
  uv run --project "$REPO_ROOT" --extra mdm-runtime edgar-warehouse mdm check-connectivity \
  | python3 -c "
import json, sys
lines = sys.stdin.read().splitlines()
# The CLI emits one structured-log JSON object per line, then a final
# pretty-printed JSON summary block starting with a line containing only '{'.
start = max(i for i, line in enumerate(lines) if line.strip() == '{')
payload = json.loads('\n'.join(lines[start:]))
sql = payload.get('sql', {})
print(json.dumps({'connected': sql.get('connected'), 'missing_tables': sql.get('missing_tables')}))
"
unset MDM_DATABASE_URL

log "Done. ${NAME_PREFIX}/mdm/postgres_dsn and ${NAME_PREFIX}/mdm/snowflake (unless skipped) are populated and verified."
