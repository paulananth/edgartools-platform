#!/usr/bin/env bash
# bootstrap-bookkeeping-postgres.sh
#
# One-click provisioning for the bookkeeping store's Postgres access on the
# *existing* Snowflake-hosted Postgres instance that already hosts MDM
# (DuckDB Retirement Cutover, Ticket 04). Creates the `bookkeeping` database,
# a dedicated `bookkeeping_app` LOGIN role with its own self-generated
# password (NOT MDM's `application` credential -- Snowflake's own docs
# confirm a Postgres admin role can create fully independent LOGIN roles
# with self-managed passwords, bypassing the `RESET ACCESS` mechanism
# entirely for that role), grants it schema privileges, provisions the 11
# bookkeeping tables via provision_bookkeeping_schema.py, populates
# `<prefix>/bookkeeping/postgres_dsn`, and verifies connectivity.
#
# Unlike bootstrap-prod-mdm.sh (the sibling script for MDM's own Postgres
# access), this script rotates `snowflake_admin` exactly ONCE, not twice:
# `bookkeeping_app`'s password is generated and set by this script directly
# via plain SQL (`CREATE ROLE ... WITH LOGIN PASSWORD` / `ALTER ROLE ...
# WITH PASSWORD`), which is not a Snowflake-managed `RESET ACCESS` rotation
# and does not by itself reopen the acquisition-ledger/registry REVOKE
# fencing (see CLAUDE.md's "snowflake_write RESET ACCESS re-grant" note --
# that platform behavior triggers specifically on rotating `snowflake_admin`
# or `application`). This script's own single `snowflake_admin` rotation
# still triggers it once, so the fence is re-closed via `mdm migrate` as the
# final database-mutating step, reusing the same rotation's password rather
# than rotating a second time (no `application` rotation happens in between
# to reopen it again, unlike bootstrap-prod-mdm.sh's shape).
#
# `bootstrap-prod-mdm.sh` itself needs no change for this: `bookkeeping_app`
# is a wholly independent credential from `application`, so nothing here
# couples the two stores' secrets together, and no dual-secret-write
# mechanism is needed.
#
# Every credential this script handles (snowflake_admin's rotated password,
# bookkeeping_app's self-generated password) is held only in-process for the
# duration of a single Python invocation and is never written to a file or to
# stdout/stderr other than the one deliberate stdout line that hands
# bookkeeping_app's password directly to the next process's stdin. The one
# exception, matching bootstrap-prod-mdm.sh's own final verification step
# exactly: the connectivity check briefly binds the written-back DSN to a
# shell variable for the single command substitution that reads it, then
# unsets it immediately after -- never logged, never exported further. Do
# not split these steps when editing this script, or a credential will
# surface in an intermediate log line.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-bookkeeping-postgres.sh --env-name <slug> --snow-connection <name> --instance-name <NAME> [options]

Required:
  --env-name <slug>             Environment slug (e.g. prod, eu-prod). Selects AWS secret/name prefix default.
  --snow-connection <name>      SnowCLI connection name (e.g. edgartools-prod).
  --instance-name <NAME>        Existing Snowflake Postgres instance name (the same instance MDM
                                 already provisioned, e.g. EDGARTOOLS_PROD_MDM) -- this script does
                                 not create a new instance.

Options:
  --aws-profile <profile>       AWS CLI profile. Default: AWS_PROFILE env var or instance role.
  --aws-region <region>         AWS region. Default: us-east-1.
  --name-prefix <prefix>        Resource prefix. Default: edgartools-<env>.
  --database <name>             Bookkeeping Postgres database name. Default: bookkeeping.
  --role-name <name>            Dedicated LOGIN role name. Default: bookkeeping_app.
  --mdm-database <name>         MDM's own database name, used only to re-run `mdm migrate` and
                                 re-close the acquisition-ledger fence this script's own
                                 snowflake_admin rotation reopens. Default: mdm.
  --dry-run                     Resolve host/instance state and print the plan; rotate/write nothing.
  -h, --help                    Show this help.

Reads (non-secret, informational only):
  - Postgres instance host via `snow sql --connection <name> -q "DESCRIBE POSTGRES INSTANCE <NAME>"`

Writes (name below is illustrative -- secrets-manifest.json is canonical):
  - <prefix>/bookkeeping/postgres_dsn   (always)

Requires on PATH: snow, aws, uv (with the mdm-runtime extra installed), python3.
USAGE
}

ENVIRONMENT=""
SNOW_CONNECTION=""
INSTANCE_NAME=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
NAME_PREFIX=""
DATABASE="bookkeeping"
ROLE_NAME="bookkeeping_app"
MDM_DATABASE="mdm"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-name) ENVIRONMENT="${2:?}"; shift 2 ;;
    --snow-connection) SNOW_CONNECTION="${2:?}"; shift 2 ;;
    --instance-name) INSTANCE_NAME="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --database) DATABASE="${2:?}"; shift 2 ;;
    --role-name) ROLE_NAME="${2:?}"; shift 2 ;;
    --mdm-database) MDM_DATABASE="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$ENVIRONMENT" ]] || { echo "ERROR: --env-name is required" >&2; usage >&2; exit 2; }
# Environment identifier is a free-form operator-chosen slug (wayfinder ticket 01),
# not a closed dev|prod enum -- a third independent environment fits neither bucket.
[[ "$ENVIRONMENT" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || {
  echo "ERROR: --env-name '${ENVIRONMENT}' is not a valid environment slug: use lowercase" >&2
  echo "       letters and digits in hyphen-separated words, starting with a letter" >&2
  echo "       (e.g. 'prod', 'eu-prod')." >&2
  exit 2
}
[[ -n "$SNOW_CONNECTION" ]] || { echo "ERROR: --snow-connection is required" >&2; exit 2; }
[[ -n "$INSTANCE_NAME" ]] || { echo "ERROR: --instance-name is required" >&2; exit 2; }
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"
# shellcheck source=lib/secrets-manifest.sh
source "${SCRIPT_DIR}/lib/secrets-manifest.sh"

log() { echo "==> $*" >&2; }
fail() { echo "ERROR: $*" >&2; exit 1; }

secret_id() { echo "${NAME_PREFIX}/$(secrets_manifest_name "$1")"; }

BOOKKEEPING_POSTGRES_DSN_SECRET_ID="$(secret_id "bookkeeping/postgres_dsn")" || exit 1

log "Resolving Postgres instance state for ${INSTANCE_NAME} via ${SNOW_CONNECTION}"
INSTANCE_JSON="$(snow sql --connection "$SNOW_CONNECTION" --format json -q "DESCRIBE POSTGRES INSTANCE ${INSTANCE_NAME}" 2>/dev/null)"
HOST="$(echo "$INSTANCE_JSON" | python3 -c "import json,sys; rows=json.load(sys.stdin); print(next(r['value'] for r in rows if r.get('property')=='host'))")"
STATE="$(echo "$INSTANCE_JSON" | python3 -c "import json,sys; rows=json.load(sys.stdin); print(next(r['value'] for r in rows if r.get('property')=='state'))")"
[[ "$STATE" == "READY" ]] || fail "Postgres instance ${INSTANCE_NAME} is not READY (state=${STATE})"
log "Instance READY. host=${HOST}"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN — would rotate snowflake_admin once, create database '${DATABASE}' + role '${ROLE_NAME}', provision 10 tables, write secret:"
  log "  ${BOOKKEEPING_POSTGRES_DSN_SECRET_ID}"
  exit 0
fi

PROVISION_PY="$(mktemp)"
VERIFY_PY="$(mktemp)"
trap 'rm -f "$PROVISION_PY" "$VERIFY_PY"' EXIT

cat > "$PROVISION_PY" <<'PYEOF'
import json, os, re, secrets, subprocess, sys, time
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
admin_pw = find_password(data)
if not admin_pw:
    sys.exit("NO_PASSWORD_FOUND_IN_ROTATION_OUTPUT")

host = os.environ["HOST"]
database = os.environ["DATABASE"]
role_name = os.environ["ROLE_NAME"]
mdm_database = os.environ["MDM_DATABASE"]
repo_root = os.environ["REPO_ROOT"]

def connect_admin(dbname, retries=8, delay=5):
    last_err = None
    for _ in range(retries):
        try:
            return psycopg2.connect(
                host=host, port=5432, dbname=dbname, user="snowflake_admin",
                password=admin_pw, sslmode="require", connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            last_err = e
            time.sleep(delay)
    raise SystemExit(f"CONNECT_FAILED_AFTER_RETRIES: {type(last_err).__name__}")

conn = connect_admin("postgres")
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

# bookkeeping_app is a fully independent Postgres LOGIN role, not one of
# Snowflake's two managed principals (snowflake_admin/application) -- its
# password is generated and set here directly, never via `RESET ACCESS`.
# There is no way to read back a previously-set Postgres password, so every
# run of this script mints and sets a fresh one unconditionally (matching
# this repo's existing "rotation is unconditional on every run" convention
# for the managed principals, applied here by necessity rather than choice).
app_pw = secrets.token_urlsafe(32)

conn = connect_admin(database)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role_name,))
role_exists = cur.fetchone() is not None
if role_exists:
    cur.execute(f'ALTER ROLE "{role_name}" WITH LOGIN PASSWORD %s', (app_pw,))
    print(f"ROLE_PASSWORD_ROTATED: {role_name}", file=sys.stderr)
else:
    cur.execute(f'CREATE ROLE "{role_name}" WITH LOGIN PASSWORD %s', (app_pw,))
    print(f"ROLE_CREATED: {role_name}", file=sys.stderr)
cur.execute(f'GRANT CONNECT ON DATABASE "{database}" TO "{role_name}"')
cur.execute(f'GRANT CREATE, USAGE ON SCHEMA public TO "{role_name}"')
cur.close()
conn.close()

bookkeeping_dsn = f"postgresql://{quote_plus(role_name)}:{quote_plus(app_pw)}@{host}:5432/{database}?sslmode=require"

# Provision the 10 bookkeeping tables as bookkeeping_app itself (it just
# received CREATE on schema public), so it owns what it creates -- no
# REASSIGN OWNED dance needed, unlike MDM's snowflake_admin-runs-DDL shape.
sys.path.insert(0, repo_root)
from sqlalchemy import create_engine
from infra.scripts.provision_bookkeeping_schema import provision

engine = create_engine(bookkeeping_dsn)
provision(engine, grant_role=None)
engine.dispose()
print("BOOKKEEPING_SCHEMA_PROVISIONED", file=sys.stderr)

# Re-close the acquisition-ledger/registry REVOKE fence this script's own
# snowflake_admin RESET ACCESS rotation (the only rotation this script
# performs) silently reopened -- same documented platform behavior
# bootstrap-prod-mdm.sh's own reapply step exists for, reusing this same
# rotation's admin password rather than rotating a second time (nothing
# else in this script reopens the fence again in between).
admin_mdm_dsn = f"postgresql://snowflake_admin:{quote_plus(admin_pw)}@{host}:5432/{mdm_database}?sslmode=require"
env = dict(os.environ)
env["MDM_DATABASE_URL"] = admin_mdm_dsn
result = subprocess.run(
    ["uv", "run", "--project", repo_root, "--extra", "mdm-runtime", "edgar-warehouse", "mdm", "migrate"],
    env=env, capture_output=True, text=True,
)
admin_mdm_dsn = None
env = None
out = re.sub(r"(postgresql://)[^@]+@", r"\1<redacted>@", result.stdout + result.stderr)
out = re.sub(r'"password"\s*:\s*"[^"]*"', '"password": "<redacted>"', out)
print(out[-1000:], file=sys.stderr)
if result.returncode != 0:
    sys.exit(f"REAPPLY_MIGRATE_FAILED_RC_{result.returncode}")
print("REAPPLY_COMPLETE", file=sys.stderr)

admin_pw = None
sys.stdout.write(app_pw)
app_pw = None
PYEOF

cat > "$VERIFY_PY" <<'PYEOF'
import os, sys
from sqlalchemy import create_engine, inspect

from edgar_warehouse.bookkeeping.models import BOOKKEEPING_TABLES

dsn = os.environ["BOOKKEEPING_DATABASE_URL"]
engine = create_engine(dsn)
inspector = inspect(engine)
existing = set(inspector.get_table_names())
missing = set(BOOKKEEPING_TABLES) - existing
engine.dispose()
if missing:
    sys.exit(f"MISSING_TABLES: {sorted(missing)}")
print(f"CONNECTED_OK: {len(BOOKKEEPING_TABLES)} tables present")
PYEOF

# Build args conditionally rather than passing --aws-profile "$AWS_PROFILE_NAME"
# unconditionally: bootstrap-aws-mdm-secrets.sh's arg parser uses ${2:?} for
# --aws-profile, which errors on an *empty* value, not just a missing flag.
# $AWS_PROFILE_NAME defaults to "" whenever the AWS_PROFILE env var isn't set
# (ambient/instance-role credentials), which is the common case -- mirrors
# bootstrap-prod-mdm.sh's own SECRETS_SCRIPT_ARGS pattern exactly.
SECRETS_SCRIPT_ARGS=(
  --env-name "$ENVIRONMENT" --aws-region "$AWS_REGION_NAME" --name-prefix "$NAME_PREFIX"
  --secret-id "$BOOKKEEPING_POSTGRES_DSN_SECRET_ID"
  --host "$HOST" --database "$DATABASE" --username "$ROLE_NAME" --password-stdin
)
[[ -n "$AWS_PROFILE_NAME" ]] && SECRETS_SCRIPT_ARGS+=(--aws-profile "$AWS_PROFILE_NAME")

log "Rotating snowflake_admin, provisioning '${DATABASE}' + role '${ROLE_NAME}', and re-closing the acquisition-ledger fence"
snow sql --connection "$SNOW_CONNECTION" --format json -q "ALTER POSTGRES INSTANCE ${INSTANCE_NAME} RESET ACCESS FOR 'snowflake_admin';" 2>/dev/null \
  | HOST="$HOST" DATABASE="$DATABASE" ROLE_NAME="$ROLE_NAME" MDM_DATABASE="$MDM_DATABASE" REPO_ROOT="$REPO_ROOT" \
    uv run --project "$REPO_ROOT" --extra mdm-runtime python "$PROVISION_PY" \
  | bash "$SCRIPT_DIR/bootstrap-aws-mdm-secrets.sh" "${SECRETS_SCRIPT_ARGS[@]}"

aws_cli() {
  local args=()
  [[ -n "$AWS_PROFILE_NAME" ]] && args+=(--profile "$AWS_PROFILE_NAME")
  aws ${args[@]+"${args[@]}"} --region "$AWS_REGION_NAME" "$@"
}

log "Verifying connectivity via the bookkeeping_app credential"
BOOKKEEPING_DATABASE_URL="$(aws_cli secretsmanager get-secret-value --secret-id "${BOOKKEEPING_POSTGRES_DSN_SECRET_ID}" --query SecretString --output text)" \
  uv run --project "$REPO_ROOT" --extra mdm-runtime python "$VERIFY_PY"
unset BOOKKEEPING_DATABASE_URL

log "Done. ${BOOKKEEPING_POSTGRES_DSN_SECRET_ID} is populated and verified."
