#!/usr/bin/env bash
# bootstrap-aws-mdm-secrets.sh
#
# Writes the Snowflake Postgres application DSN to the operator-facing
# MDM postgres_dsn Secrets Manager secret. Terraform manages only the empty
# secret container; the credential value stays out of Terraform state.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/secrets-manifest.sh
source "${SCRIPT_DIR}/lib/secrets-manifest.sh"

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-aws-mdm-secrets.sh --env-name <slug> [options]

Writes the MDM_DATABASE_URL secret for the Snowflake Postgres cutover.

Provide the DSN with one of:
  --dsn <postgresql://...>
  --dsn-stdin
  --host <host> --username <user> --password-stdin

Options:
  --env-name <slug>             Environment slug (e.g. prod, eu-prod). Required.
  --aws-profile <profile>       AWS CLI profile. Default: AWS_PROFILE env var or instance role.
  --aws-region <region>         AWS region. Default: us-east-1.
  --name-prefix <prefix>        Resource prefix. Default: edgartools-<env-name>.
  --secret-id <id-or-arn>       Secret to write. Default: <name-prefix>/<name>, where <name> is
                                 the "mdm/postgres_dsn" entry in secrets-manifest.json (the
                                 canonical declaration -- this default is illustrative, not a
                                 second source of truth).
  --dsn <dsn>                   Full PostgreSQL DSN. Prefer --dsn-stdin for credentials.
  --dsn-stdin                   Read the full PostgreSQL DSN from stdin.
  --host <host>                 Snowflake Postgres host when constructing a DSN.
  --port <port>                 PostgreSQL port. Default: 5432.
  --database <name>             PostgreSQL database. Default: mdm.
  --username <user>             Snowflake Postgres application role/user.
  --password-stdin              Read the application password from stdin when constructing a DSN.
  --expected-host-suffix <suf>  Required host suffix. Default: .snowflake.app.
  --dry-run                     Validate and print the masked DSN without writing.
  -h, --help                    Show this help.

Requires on PATH: aws, jq (to read secrets-manifest.json), python3.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  echo "==> $*" >&2
}

ENVIRONMENT=""
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
NAME_PREFIX=""
SECRET_ID=""
DSN=""
DSN_STDIN=false
HOST=""
PORT="5432"
DATABASE="mdm"
USERNAME=""
PASSWORD_STDIN=false
EXPECTED_HOST_SUFFIX=".snowflake.app"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-name) ENVIRONMENT="${2:?}"; shift 2 ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --secret-id) SECRET_ID="${2:?}"; shift 2 ;;
    --dsn) DSN="${2:?}"; shift 2 ;;
    --dsn-stdin) DSN_STDIN=true; shift ;;
    --host) HOST="${2:?}"; shift 2 ;;
    --port) PORT="${2:?}"; shift 2 ;;
    --database) DATABASE="${2:?}"; shift 2 ;;
    --username) USERNAME="${2:?}"; shift 2 ;;
    --password-stdin) PASSWORD_STDIN=true; shift ;;
    --expected-host-suffix) EXPECTED_HOST_SUFFIX="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$ENVIRONMENT" ]] || { echo "ERROR: --env-name is required" >&2; usage >&2; exit 2; }
# Environment identifier is a free-form operator-chosen slug (wayfinder ticket 01),
# not a closed dev|prod enum -- a third independent environment fits neither bucket.
# Shape is validated here so a typo fails loudly rather than silently creating
# oddly-named AWS secrets.
[[ "$ENVIRONMENT" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || {
  echo "ERROR: --env-name '${ENVIRONMENT}' is not a valid environment slug: use lowercase" >&2
  echo "       letters and digits in hyphen-separated words, starting with a letter" >&2
  echo "       (e.g. 'prod', 'eu-prod')." >&2
  exit 2
}
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
if [[ -z "$SECRET_ID" ]]; then
  MANIFEST_SECRET_NAME="$(secrets_manifest_name "mdm/postgres_dsn")" || exit 1
  SECRET_ID="${NAME_PREFIX}/${MANIFEST_SECRET_NAME}"
fi

aws_cli() {
  local args=()
  [[ -n "$AWS_PROFILE_NAME" ]] && args+=(--profile "$AWS_PROFILE_NAME")
  # macOS ships bash 3.2, which treats "${args[@]}" on a still-empty array as
  # an unbound variable under `set -u` (fixed in bash 4.4+) -- the
  # ${args[@]+"${args[@]}"} form expands to nothing instead of erroring when
  # args is empty, and to the normal array expansion otherwise.
  aws ${args[@]+"${args[@]}"} --region "$AWS_REGION_NAME" "$@"
}

if [[ "$DSN_STDIN" == "true" ]]; then
  [[ -z "$DSN" ]] || fail "use only one of --dsn or --dsn-stdin"
  DSN="$(cat)"
fi

if [[ -z "$DSN" ]]; then
  [[ -n "$HOST" ]] || fail "provide --dsn/--dsn-stdin or --host"
  [[ -n "$USERNAME" ]] || fail "--username is required when constructing a DSN"
  [[ "$PASSWORD_STDIN" == "true" ]] || fail "--password-stdin is required when constructing a DSN"
  PASSWORD="$(cat)"
  DSN="$(python3 - "$HOST" "$PORT" "$DATABASE" "$USERNAME" "$PASSWORD" <<'PY'
import sys
from urllib.parse import quote_plus

host, port, database, username, password = sys.argv[1:]
print(f"postgresql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}?sslmode=require")
PY
)"
fi

VALIDATED_JSON="$(python3 - "$DSN" "$DATABASE" "$EXPECTED_HOST_SUFFIX" <<'PY'
import json
import sys
from urllib.parse import parse_qs, urlsplit, urlunsplit

dsn, expected_database, expected_suffix = sys.argv[1:]
parts = urlsplit(dsn.strip())
if parts.scheme not in {"postgresql", "postgres", "postgresql+psycopg2"}:
    raise SystemExit("DSN scheme must be postgresql, postgres, or postgresql+psycopg2")
if not parts.hostname:
    raise SystemExit("DSN must include a host")
if not parts.hostname.endswith(expected_suffix):
    raise SystemExit(f"DSN host must end with {expected_suffix}")
database = parts.path.lstrip("/")
if database != expected_database:
    raise SystemExit(f"DSN database must be {expected_database}")
query = parse_qs(parts.query)
if query.get("sslmode", [""])[0] != "require":
    separator = "&" if parts.query else ""
    dsn = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query + f"{separator}sslmode=require", parts.fragment))
    parts = urlsplit(dsn)
redacted_netloc = parts.hostname
if parts.port:
    redacted_netloc = f"{redacted_netloc}:{parts.port}"
if parts.username:
    redacted_netloc = f"{parts.username}:***@{redacted_netloc}"
masked = urlunsplit((parts.scheme, redacted_netloc, parts.path, parts.query, parts.fragment))
print(json.dumps({"dsn": dsn, "masked": masked, "host": parts.hostname, "database": database}))
PY
)" || fail "invalid Snowflake Postgres DSN"

NORMALIZED_DSN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["dsn"])' <<< "$VALIDATED_JSON")"
MASKED_DSN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["masked"])' <<< "$VALIDATED_JSON")"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN - target secret: ${SECRET_ID}"
  log "DRY RUN - validated DSN:"
  echo "$MASKED_DSN"
  exit 0
fi

log "Writing Snowflake Postgres MDM DSN to ${SECRET_ID}"
aws_cli secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --secret-string "$NORMALIZED_DSN" \
  --output text >/dev/null

log "Done. MDM_DATABASE_URL secret now points at ${MASKED_DSN}"
log "Next: deploy with deploy-aws-application.sh --enable-mdm --mdm-database-source snowflake-postgres"
