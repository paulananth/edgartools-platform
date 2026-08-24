#!/usr/bin/env bash
# bootstrap-dbt-snowflake-secret.sh
#
# Writes the dbt/snowflake Secrets Manager secret. Terraform has no resource
# for this one -- unlike mdm/postgres_dsn, mdm/snowflake, mdm/neo4j, and
# mdm/api_keys (see secrets-manifest.json), dbt/snowflake was populated
# in prod via an undocumented manual step with no reproducible path anywhere
# in this repo. This script closes that gap.
#
# bootstrap-prod-mdm.sh reads this secret and jq-transforms it into
# mdm/snowflake -- the JSON shape below (DBT_SNOWFLAKE_ACCOUNT/USER/PASSWORD/
# WAREHOUSE/DATABASE/ROLE) is that read side's exact contract; do not rename
# these keys without updating bootstrap-prod-mdm.sh's transform too.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/secrets-manifest.sh
source "${SCRIPT_DIR}/lib/secrets-manifest.sh"

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-dbt-snowflake-secret.sh --env-name <slug> --account <acct> \
    --user <user> --warehouse <wh> --password-stdin [options]

Writes the dbt/snowflake Secrets Manager secret: Snowflake connection
settings for dbt gold-layer runs, also read by bootstrap-prod-mdm.sh to
derive mdm/snowflake.

Options:
  --env-name <slug>        Environment slug (e.g. prod, eu-prod). Required.
  --account <acct>         Snowflake account identifier. Required.
  --user <user>            Snowflake user. Required.
  --warehouse <wh>         Snowflake warehouse. Required.
  --database <name>        Snowflake database. Default: EDGARTOOLS_<SLUG>
                            (hyphens become underscores, uppercased --
                            matches this repo's env-name-to-Snowflake-
                            identifier convention, generate-snowflake-env.py).
  --role <role>            Snowflake role. Optional -- written as an empty
                           string in the secret if not provided.
  --password-stdin         Read the Snowflake password from stdin. Required.
  --aws-profile <profile>  AWS CLI profile. Default: AWS_PROFILE env var or instance role.
  --aws-region <region>    AWS region. Default: us-east-1.
  --name-prefix <prefix>   Resource prefix. Default: edgartools-<env-name>.
  --secret-id <id-or-arn>  Secret to write. Default: <name-prefix>/<name>, where <name> is
                           the "dbt/snowflake" entry in secrets-manifest.json (the canonical
                           declaration -- this default is illustrative, not a second source
                           of truth).
  --dry-run                Validate and print the masked payload without writing.
  -h, --help                Show this help.

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
ACCOUNT=""
SNOWFLAKE_USER=""
WAREHOUSE=""
DATABASE=""
ROLE=""
PASSWORD_STDIN=false
AWS_PROFILE_NAME="${AWS_PROFILE:-}"
AWS_REGION_NAME="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
NAME_PREFIX=""
SECRET_ID=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-name) ENVIRONMENT="${2:?}"; shift 2 ;;
    --account) ACCOUNT="${2:?}"; shift 2 ;;
    --user) SNOWFLAKE_USER="${2:?}"; shift 2 ;;
    --warehouse) WAREHOUSE="${2:?}"; shift 2 ;;
    --database) DATABASE="${2:?}"; shift 2 ;;
    --role) ROLE="${2:?}"; shift 2 ;;
    --password-stdin) PASSWORD_STDIN=true; shift ;;
    --aws-profile) AWS_PROFILE_NAME="${2:?}"; shift 2 ;;
    --aws-region) AWS_REGION_NAME="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --secret-id) SECRET_ID="${2:?}"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$ENVIRONMENT" ]] || { echo "ERROR: --env-name is required" >&2; usage >&2; exit 2; }
# Environment identifier is a free-form operator-chosen slug (wayfinder ticket 01),
# not a closed dev|prod enum. Shape is validated here so a typo fails loudly
# rather than silently creating an oddly-named AWS secret.
[[ "$ENVIRONMENT" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || {
  echo "ERROR: --env-name '${ENVIRONMENT}' is not a valid environment slug: use lowercase" >&2
  echo "       letters and digits in hyphen-separated words, starting with a letter" >&2
  echo "       (e.g. 'prod', 'eu-prod')." >&2
  exit 2
}

[[ -n "$ACCOUNT" ]] || fail "--account is required"
[[ -n "$SNOWFLAKE_USER" ]] || fail "--user is required"
[[ -n "$WAREHOUSE" ]] || fail "--warehouse is required"
[[ "$PASSWORD_STDIN" == "true" ]] || fail "--password-stdin is required"

# Account/user/warehouse are identity-bearing -- deliberately no defaults for
# them (a wrong guess would populate a live production credential with the
# wrong identity). Database is the one field with a single, already-
# established, unambiguous convention (generate-snowflake-env.py's own
# DATABASE_NAME derivation) worth defaulting.
if [[ -z "$DATABASE" ]]; then
  DATABASE="EDGARTOOLS_$(echo "$ENVIRONMENT" | tr '[:lower:]-' '[:upper:]_')"
fi

NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
if [[ -z "$SECRET_ID" ]]; then
  MANIFEST_SECRET_NAME="$(secrets_manifest_name "dbt/snowflake")" || exit 1
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

PASSWORD="$(cat)"
[[ -n "$PASSWORD" ]] || fail "password read from stdin was empty"

SECRET_JSON="$(ACCOUNT="$ACCOUNT" SNOWFLAKE_USER="$SNOWFLAKE_USER" PASSWORD="$PASSWORD" \
    WAREHOUSE="$WAREHOUSE" DATABASE="$DATABASE" ROLE="$ROLE" python3 - <<'PY'
import json
import os

payload = {
    "DBT_SNOWFLAKE_ACCOUNT": os.environ["ACCOUNT"],
    "DBT_SNOWFLAKE_USER": os.environ["SNOWFLAKE_USER"],
    "DBT_SNOWFLAKE_PASSWORD": os.environ["PASSWORD"],
    "DBT_SNOWFLAKE_WAREHOUSE": os.environ["WAREHOUSE"],
    "DBT_SNOWFLAKE_DATABASE": os.environ["DATABASE"],
    # Always present, even when empty: bootstrap-prod-mdm.sh reads
    # .DBT_SNOWFLAKE_ROLE unconditionally in its jq transform -- an absent
    # key resolves to JSON null there, not an empty string, which would
    # propagate a literal null into mdm/snowflake instead of a key shape
    # matching every other field. Keeping the key present with "" avoids
    # that null-versus-absent split.
    "DBT_SNOWFLAKE_ROLE": os.environ.get("ROLE", ""),
}
print(json.dumps(payload))
PY
)"

MASKED_SUMMARY="account=${ACCOUNT} user=${SNOWFLAKE_USER} warehouse=${WAREHOUSE} database=${DATABASE} role=${ROLE:-<none>} password=***"

if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN - target secret: ${SECRET_ID}"
  log "DRY RUN - payload: ${MASKED_SUMMARY}"
  exit 0
fi

log "Writing dbt/snowflake secret to ${SECRET_ID} (${MASKED_SUMMARY})"
aws_cli secretsmanager put-secret-value \
  --secret-id "$SECRET_ID" \
  --secret-string "$SECRET_JSON" \
  --output text >/dev/null

log "Done. ${SECRET_ID} now holds: ${MASKED_SUMMARY}"
log "Next: bootstrap-prod-mdm.sh (unless --skip-snowflake-secret) reads this to derive mdm/snowflake."
