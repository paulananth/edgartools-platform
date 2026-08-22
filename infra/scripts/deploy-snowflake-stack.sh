#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash infra/scripts/deploy-snowflake-stack.sh [options]

Options:
  --env-name <slug>          Target environment slug (e.g. prod, eu-prod). Required.
  --snow-connection <name>   SnowCLI connection used for all snow sql operations. Required.
  --run-validation           Run SnowCLI-based native-pull validation artifact generation.
  --run-dbt                  Run dbt deps/run/test.
  --upload-dashboard         Upload dashboard artifacts.

This is an explicit post-infra Snowflake/database-object operator script. After
Terraform completes, SNOWFLAKE_RUN_MANIFEST_TASK is always created or replaced
and resumed (requires snow CLI). dbt, dashboard upload, and validation are opt-in.

Required env vars for warehouse bootstrap commands (set before running edgar-warehouse):
  EDGAR_IDENTITY               Operator email for SEC API user-agent.
  WAREHOUSE_RUNTIME_MODE       Set to bronze_capture to execute (default: infrastructure_validation).
  WAREHOUSE_BRONZE_ROOT        s3://edgartools-dev-bronze-<account>/warehouse/bronze
  WAREHOUSE_STORAGE_ROOT       s3://edgartools-dev-warehouse-<account>/warehouse
  SERVING_EXPORT_ROOT          s3://edgartools-dev-snowflake-export-<account>/warehouse/artifacts/snowflake_exports
  MDM_DATABASE_URL             PostgreSQL DSN for MDM (system of record for universe tracking).
                               Retrieve with: aws secretsmanager get-secret-value \
                                 --secret-id edgartools-dev/mdm/postgres_dsn --query SecretString --output text
  WAREHOUSE_BRONZE_CIK_LIMIT   Optional: cap number of CIKs processed (e.g. 100 for testing).
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ENVIRONMENT=""
SNOW_CONNECTION=""
RUN_VALIDATION=0
RUN_DBT=0
UPLOAD_DASHBOARD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-name)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --snow-connection)
      SNOW_CONNECTION="${2:-}"
      shift 2
      ;;
    --run-validation)
      RUN_VALIDATION=1
      shift
      ;;
    --run-dbt)
      RUN_DBT=1
      shift
      ;;
    --upload-dashboard)
      UPLOAD_DASHBOARD=1
      shift
      ;;
    --skip-validation|--skip-dbt|--skip-dashboard)
      echo "$1 is no longer needed; validation, dbt, and dashboard upload are opt-in." >&2
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$ENVIRONMENT" ]] || die "--env-name is required"
# Environment identifier is a free-form operator-chosen slug (wayfinder ticket 01),
# not a closed dev|prod enum. Shape is checked here; the Terraform roots this
# script actually reads are checked for existence below, once REPO_ROOT is known.
[[ "$ENVIRONMENT" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]] || die \
  "--env-name '${ENVIRONMENT}' is not a valid environment slug: use lowercase letters and digits in hyphen-separated words, starting with a letter (e.g. 'prod', 'eu-prod')."

# Required, never derived from the environment name. Deriving it is what let
# install.sh and this script disagree about the default connection for the same
# environment (CLAUDE.md, "SnowCLI connection naming").
[[ -n "$SNOW_CONNECTION" ]] || die "--snow-connection is required (no default is derived from --env-name)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TMP_DIR="${REPO_ROOT}/.tmp"

# Auto-source the Snowflake password from the SnowCLI connection named by
# --snow-connection when no password env var is set. This lets you run the
# deploy with just --snow-connection <name>; otherwise everything still works
# as before because env vars take precedence. Resolution itself is delegated
# to `edgar-warehouse resolve-snowflake-env` (edgar_warehouse/cli.py) --
# credential-isolation Ticket 1/2 -- rather than reimplemented here: this
# script previously read the password out of config.toml's own [connections]
# table directly, a layout no real SnowCLI config anywhere in this repo
# (including CI's own smoke-test.yml) actually produces, so that lookup
# always silently resolved empty against a real operator setup. The shared
# resolver reads ~/.snowflake/connections.toml, the layout SnowCLI actually
# uses, and is the same chain `mdm export`/`mdm sync-graph` already trust.
load_password_from_snow_config() {
  if [[ -n "${TF_VAR_snowflake_password:-}" ]]; then
    return 0
  fi
  # SNOWFLAKE_PASSWORD is a supported input (e.g. set in the operator's shell
  # profile for `snow`/dbt convenience) but Terraform's snowflake provider only
  # reads TF_VAR_snowflake_password -- without this branch, having only
  # SNOWFLAKE_PASSWORD set short-circuited the resolver lookup below
  # *without* ever populating TF_VAR_snowflake_password, so `terraform apply`
  # silently ran with a null password and failed with "Incorrect username or
  # password was specified."
  if [[ -n "${SNOWFLAKE_PASSWORD:-}" ]]; then
    export TF_VAR_snowflake_password="${SNOWFLAKE_PASSWORD}"
    export DBT_SNOWFLAKE_PASSWORD="${DBT_SNOWFLAKE_PASSWORD:-${SNOWFLAKE_PASSWORD}}"
    return 0
  fi

  # require_command uv is now unconditional here (previously uv was only
  # required when --run-dbt was set) -- a real, deliberate widening: calling
  # the shared resolver needs it. This matches require_command terraform/
  # python3 a few lines below, both already unconditional for this script,
  # and this repo's own "always use uv" convention (CLAUDE.md), so a plain
  # `--env-name`-only run now expects uv on PATH same as it already expected
  # terraform.
  #
  # Best-effort otherwise, matching the prior behaviour: a resolution
  # failure once uv itself is present is not fatal on its own -- downstream
  # validation (the DBT_SNOWFLAKE_PASSWORD check when --run-dbt is set, or
  # Terraform's own provider error otherwise) is what actually catches a
  # genuine miss. $(...) only captures stdout; the resolver's own stderr
  # (success confirmation or error detail) passes through to this script's
  # stderr untouched.
  require_command uv
  local resolver_exports
  if resolver_exports="$(uv run --project "${REPO_ROOT}" --extra mdm-runtime edgar-warehouse resolve-snowflake-env --connection "${SNOW_CONNECTION}")"; then
    eval "${resolver_exports}"
  else
    echo "WARNING: could not resolve a Snowflake password for connection '${SNOW_CONNECTION}' via edgar-warehouse resolve-snowflake-env (see error above). Set TF_VAR_snowflake_password or SNOWFLAKE_PASSWORD explicitly if this run needs one." >&2
  fi
}

load_password_from_snow_config

AWS_ROOT="${REPO_ROOT}/infra/terraform/access/aws/accounts/${ENVIRONMENT}"
SNOWFLAKE_ROOT="${REPO_ROOT}/infra/terraform/snowflake/accounts/${ENVIRONMENT}"
SNOWFLAKE_ACCESS_ROOT="${REPO_ROOT}/infra/terraform/access/snowflake/accounts/${ENVIRONMENT}"
DBT_ROOT="${REPO_ROOT}/infra/snowflake/dbt/edgartools_gold"
VALIDATION_ARTIFACT="${REPO_ROOT}/infra/snowflake/sql/${ENVIRONMENT}_native_pull_handshake.json"

# Replacing the dev|prod enum with a slug means the environment is valid iff the
# Terraform roots this script reads actually exist -- so adding environment N+1
# never requires editing this script again. Each root is checked separately and
# named in its own error: they do not all come from the same place.
#
# The two Snowflake roots are what infra/scripts/generate-snowflake-env.py emits
# (wayfinder ticket 01). The AWS access root is NOT -- it is the AWS-side
# precondition (wayfinder ticket 04), stood up separately. Checking it here, by
# name, is the point: a shared "Snowflake roots exist" check would pass and then
# die inside terraform with something far less obvious.
for _root_spec in \
  "${SNOWFLAKE_ROOT}|Snowflake provisioning root|generate-snowflake-env.py (wayfinder ticket 01)" \
  "${SNOWFLAKE_ACCESS_ROOT}|Snowflake access root|generate-snowflake-env.py (wayfinder ticket 01)" \
  "${AWS_ROOT}|AWS access root|the AWS side, which is a precondition this script does not create (wayfinder ticket 04)"
do
  _root_path="${_root_spec%%|*}"
  _root_rest="${_root_spec#*|}"
  _root_label="${_root_rest%%|*}"
  _root_source="${_root_rest#*|}"
  [[ -d "$_root_path" ]] || die \
    "${_root_label} for environment '${ENVIRONMENT}' does not exist: ${_root_path#${REPO_ROOT}/} -- create it with ${_root_source}"
done
unset _root_spec _root_path _root_rest _root_label _root_source

mkdir -p "${TMP_DIR}"
AWS_BOOTSTRAP_OVERLAY="$(mktemp "${TMP_DIR}/aws-bootstrap-${ENVIRONMENT}-XXXXXX.tfvars.json")"
AWS_RECONCILE_OVERLAY="$(mktemp "${TMP_DIR}/aws-reconcile-${ENVIRONMENT}-XXXXXX.tfvars.json")"
SNOWFLAKE_OVERLAY="$(mktemp "${TMP_DIR}/snowflake-native-pull-${ENVIRONMENT}-XXXXXX.tfvars.json")"
AWS_OUTPUTS_FILE="$(mktemp "${TMP_DIR}/aws-outputs-${ENVIRONMENT}-XXXXXX.json")"
SNOWFLAKE_OUTPUTS_FILE="$(mktemp "${TMP_DIR}/snowflake-outputs-${ENVIRONMENT}-XXXXXX.json")"
SNOWFLAKE_ACCESS_OUTPUTS_FILE="$(mktemp "${TMP_DIR}/snowflake-access-outputs-${ENVIRONMENT}-XXXXXX.json")"

cleanup() {
  rm -f \
    "${AWS_BOOTSTRAP_OVERLAY}" \
    "${AWS_RECONCILE_OVERLAY}" \
    "${SNOWFLAKE_OVERLAY}" \
    "${AWS_OUTPUTS_FILE}" \
    "${SNOWFLAKE_OUTPUTS_FILE}" \
    "${SNOWFLAKE_ACCESS_OUTPUTS_FILE}"
}
trap cleanup EXIT

require_command terraform
require_command python3

load_snowflake_provider_vars_from_tfvars() {
  local tfvars_path="${SNOWFLAKE_ROOT}/terraform.tfvars"
  [[ -f "${tfvars_path}" ]] || return 0

  local exports
  exports="$(TFVARS_PATH="${tfvars_path}" python3 - <<'PY'
import os
import pathlib
import re
import shlex

text = pathlib.Path(os.environ["TFVARS_PATH"]).read_text(encoding="utf-8")
keys = {
    "snowflake_organization_name": "TF_VAR_snowflake_organization_name",
    "snowflake_account_name": "TF_VAR_snowflake_account_name",
    "snowflake_user": "TF_VAR_snowflake_user",
}
for tf_key, env_key in keys.items():
    if os.environ.get(env_key):
        continue
    match = re.search(rf'^\s*{re.escape(tf_key)}\s*=\s*"([^"]*)"', text, flags=re.MULTILINE)
    if match:
        print(f"export {env_key}={shlex.quote(match.group(1))}")
PY
)"
  [[ -z "${exports}" ]] || eval "${exports}"
}

load_snowflake_provider_vars_from_tfvars

if [[ ${RUN_VALIDATION} -eq 1 || ${UPLOAD_DASHBOARD} -eq 1 ]]; then
  require_command snow
fi

if [[ ${RUN_DBT} -eq 1 ]]; then
  require_command uv
  # Auto-derive dbt connection inputs from the TF_VAR_snowflake_* values that
  # Terraform already requires. Lets the deploy run with one source of truth.
  if [[ -z "${DBT_SNOWFLAKE_ACCOUNT:-}" && -n "${TF_VAR_snowflake_organization_name:-}" && -n "${TF_VAR_snowflake_account_name:-}" ]]; then
    export DBT_SNOWFLAKE_ACCOUNT="${TF_VAR_snowflake_organization_name}-${TF_VAR_snowflake_account_name}"
  fi
  : "${DBT_SNOWFLAKE_USER:=${TF_VAR_snowflake_user:-}}"
  : "${DBT_SNOWFLAKE_PASSWORD:=${TF_VAR_snowflake_password:-}}"
  export DBT_SNOWFLAKE_USER DBT_SNOWFLAKE_PASSWORD
  [[ -n "${DBT_SNOWFLAKE_ACCOUNT:-}" ]] || die "DBT_SNOWFLAKE_ACCOUNT (or TF_VAR_snowflake_organization_name + TF_VAR_snowflake_account_name) must be set when dbt is enabled"
  [[ -n "${DBT_SNOWFLAKE_USER:-}" ]] || die "DBT_SNOWFLAKE_USER (or TF_VAR_snowflake_user) must be set when dbt is enabled"
  [[ -n "${DBT_SNOWFLAKE_PASSWORD:-}" ]] || die "DBT_SNOWFLAKE_PASSWORD (or TF_VAR_snowflake_password) must be set when dbt is enabled"
  export UV_CACHE_DIR="${UV_CACHE_DIR:-/private/tmp/uv-cache}"
fi

[[ -f "${AWS_ROOT}/backend.hcl" ]] || die "Missing backend.hcl in ${AWS_ROOT}"
[[ -f "${SNOWFLAKE_ROOT}/backend.hcl" ]] || die "Missing backend.hcl in ${SNOWFLAKE_ROOT}"
[[ -f "${SNOWFLAKE_ACCESS_ROOT}/backend.hcl" ]] || die "Missing backend.hcl in ${SNOWFLAKE_ACCESS_ROOT}"

terraform_init() {
  local dir="$1"
  terraform -chdir="${dir}" init -backend-config=backend.hcl -input=false -no-color >/dev/null
}

terraform_apply() {
  local dir="$1"
  local overlay="$2"
  terraform -chdir="${dir}" apply -auto-approve -input=false -no-color -var-file="${overlay}"
}

# Apply only the resources needed to emit the Snowflake-managed AWS principal,
# so the AWS trust can be reconciled before the manifest pipe is created.
# Pipe creation tests the IAM trust at CREATE time; without reconciliation, it
# fails with "Error assuming AWS_ROLE". Argument list mirrors terraform_apply.
terraform_apply_storage_integration_only() {
  local dir="$1"
  local overlay="$2"
  terraform -chdir="${dir}" apply -auto-approve -input=false -no-color -var-file="${overlay}" \
    -target='module.native_pull[0].snowflake_storage_integration_aws.native_pull'
}

terraform_apply_root() {
  local dir="$1"
  terraform -chdir="${dir}" apply -auto-approve -input=false -no-color
}

terraform_output_json() {
  local dir="$1"
  local file="$2"
  terraform -chdir="${dir}" output -json >"${file}"
}

json_value() {
  local file="$1"
  local key="$2"
  python3 - "$file" "$key" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data[sys.argv[2]]["value"]
if value is None:
    print("")
elif isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
}

json_map_value() {
  local file="$1"
  local key="$2"
  local nested_key="$3"
  python3 - "$file" "$key" "$nested_key" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data[sys.argv[2]]["value"][sys.argv[3]]
print(value)
PY
}

write_aws_overlay() {
  local path="$1"
  local bootstrap_enabled="$2"
  local subscriber_arn="$3"
  local external_id="$4"

  OVERLAY_PATH="${path}" \
  OVERLAY_BOOTSTRAP="${bootstrap_enabled}" \
  OVERLAY_SUBSCRIBER_ARN="${subscriber_arn}" \
  OVERLAY_EXTERNAL_ID="${external_id}" \
  python3 - <<'PY'
import json, os, pathlib

payload = {
    "snowflake_bootstrap_enabled": os.environ["OVERLAY_BOOTSTRAP"].lower() == "true",
    "snowflake_manifest_subscriber_arn": os.environ["OVERLAY_SUBSCRIBER_ARN"] or None,
    "snowflake_storage_external_id": os.environ["OVERLAY_EXTERNAL_ID"],
    # Force the access root's own terraform_remote_state read of the
    # Snowflake root (var.snowflake_state_bucket) off for both overlay
    # applies here. Without this, a stale snowflake_state_bucket/key left in
    # the access root's local terraform.tfvars (e.g. after swapping which
    # Snowflake account is live, per the snowflake-account-cutover map's
    # "second account swap" addendum) makes
    # local.subscriber_arn's coalesce() fall through to that OLD account's
    # already-applied output instead of "*"/the freshly-resolved ARN this
    # function is explicitly passing -- silently granting SNS trust to the
    # wrong Snowflake account instead of failing loudly. -var-file supports
    # a literal JSON null (a bare -var flag cannot express null), which is
    # required to actually disable the data source's count = ... != null
    # gate, not just leave the value looking empty.
    "snowflake_state_bucket": None,
}

pathlib.Path(os.environ["OVERLAY_PATH"]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

write_snowflake_overlay() {
  local path="$1"
  local storage_role_arn="$2"
  local export_root_url="$3"
  local manifest_sns_topic_arn="$4"
  local external_id="$5"

  OVERLAY_PATH="${path}" \
  OVERLAY_STORAGE_ROLE_ARN="${storage_role_arn}" \
  OVERLAY_EXPORT_ROOT_URL="${export_root_url}" \
  OVERLAY_MANIFEST_SNS_TOPIC_ARN="${manifest_sns_topic_arn}" \
  OVERLAY_EXTERNAL_ID="${external_id}" \
  python3 - <<'PY'
import json, os, pathlib

payload = {
    "snowflake_storage_role_arn": os.environ["OVERLAY_STORAGE_ROLE_ARN"],
    "snowflake_export_root_url": os.environ["OVERLAY_EXPORT_ROOT_URL"],
    "snowflake_manifest_sns_topic_arn": os.environ["OVERLAY_MANIFEST_SNS_TOPIC_ARN"],
    "snowflake_storage_external_id": os.environ["OVERLAY_EXTERNAL_ID"],
}

pathlib.Path(os.environ["OVERLAY_PATH"]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

echo "Initializing Terraform backends"
terraform_init "${AWS_ROOT}"
terraform_init "${SNOWFLAKE_ROOT}"
terraform_init "${SNOWFLAKE_ACCESS_ROOT}"

EXTERNAL_ID="edgartools-${ENVIRONMENT}-snowflake-native-pull"

echo "Applying AWS bootstrap trust"
write_aws_overlay "${AWS_BOOTSTRAP_OVERLAY}" "true" "" "${EXTERNAL_ID}"
terraform_apply "${AWS_ROOT}" "${AWS_BOOTSTRAP_OVERLAY}"
terraform_output_json "${AWS_ROOT}" "${AWS_OUTPUTS_FILE}"

STORAGE_ROLE_ARN="$(json_value "${AWS_OUTPUTS_FILE}" "snowflake_storage_role_arn")"
EXPORT_ROOT_URL="$(json_value "${AWS_OUTPUTS_FILE}" "snowflake_export_root_url")"
MANIFEST_SNS_TOPIC_ARN="$(json_value "${AWS_OUTPUTS_FILE}" "snowflake_manifest_sns_topic_arn")"

[[ -n "${STORAGE_ROLE_ARN}" ]] || die "AWS bootstrap apply did not produce snowflake_storage_role_arn"
[[ -n "${EXPORT_ROOT_URL}" ]] || die "AWS bootstrap apply did not produce snowflake_export_root_url"
[[ -n "${MANIFEST_SNS_TOPIC_ARN}" ]] || die "AWS bootstrap apply did not produce snowflake_manifest_sns_topic_arn"

echo "Applying Snowflake storage integration only (to emit AWS principal for trust reconciliation)"
write_snowflake_overlay "${SNOWFLAKE_OVERLAY}" "${STORAGE_ROLE_ARN}" "${EXPORT_ROOT_URL}" "${MANIFEST_SNS_TOPIC_ARN}" "${EXTERNAL_ID}"
terraform_apply_storage_integration_only "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OVERLAY}"
terraform_output_json "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OUTPUTS_FILE}"

SUBSCRIBER_ARN="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "snowflake_manifest_subscriber_arn")"
[[ -n "${SUBSCRIBER_ARN}" ]] || die "Snowflake storage-integration apply did not produce snowflake_manifest_subscriber_arn"

echo "Reconciling AWS trust to the exact Snowflake principal"
write_aws_overlay "${AWS_RECONCILE_OVERLAY}" "false" "${SUBSCRIBER_ARN}" "${EXTERNAL_ID}"
terraform_apply "${AWS_ROOT}" "${AWS_RECONCILE_OVERLAY}"
terraform_output_json "${AWS_ROOT}" "${AWS_OUTPUTS_FILE}"

echo "Applying full Snowflake stack with reconciled trust"
terraform_apply "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OVERLAY}"
terraform_output_json "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OUTPUTS_FILE}"

# 15_decision_schema.sql must run here, between the two applies above/below --
# not as its own later install.sh stage. infra/terraform/access/snowflake/
# modules/account_access/main.tf (applied by SNOWFLAKE_ACCESS_ROOT just below)
# grants reader privileges on EDGARTOOLS_<ENV>.EDGARTOOLS_DECISION
# unconditionally, but no Terraform root creates that schema -- confirmed via
# repo-wide search: account_baseline's schema_names local only has "source"
# and "gold". Without this, a brand-new account's access-root apply fails
# outright: "object does not exist or not authorized" for
# reader_decision_schema_usage/reader_decision_all_views/
# reader_decision_future_views. The database itself must already exist for
# this to succeed, which is why this can't run any earlier than immediately
# after the SNOWFLAKE_ROOT apply just above (account_baseline, part of that
# same root, is what creates the database).
DECISION_SCHEMA_DATABASE_NAME="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "database_name")"
[[ -n "${DECISION_SCHEMA_DATABASE_NAME}" ]] || die "Snowflake stack apply did not produce database_name (needed for 15_decision_schema.sql)"
echo "Applying Decision Contract schema (must precede access-control grants below)"
{
  printf '%s\n' \
    "SET database_name = '${DECISION_SCHEMA_DATABASE_NAME}';" \
    "SET decision_schema_name = 'EDGARTOOLS_DECISION';"
  cat "${REPO_ROOT}/infra/snowflake/sql/bootstrap/15_decision_schema.sql"
} | snow sql --connection "${SNOW_CONNECTION}" -i

echo "Applying Snowflake access-control grants"
terraform_apply_root "${SNOWFLAKE_ACCESS_ROOT}"
terraform_output_json "${SNOWFLAKE_ACCESS_ROOT}" "${SNOWFLAKE_ACCESS_OUTPUTS_FILE}"

# The stream processor task is not managed by Terraform — create or replace it
# here so it is always present and running after every deploy. Without this task
# the SNOWFLAKE_RUN_MANIFEST_STREAM is never consumed and gold tables are never
# refreshed automatically after a warehouse bootstrap run.
deploy_manifest_task() {
  local db wh
  db="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "database_name")"
  wh="$(json_map_value "${SNOWFLAKE_OUTPUTS_FILE}" "warehouse_names" "refresh")"
  snow sql --connection "${SNOW_CONNECTION}" -q "
CREATE OR REPLACE TASK ${db}.EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK
  WAREHOUSE = ${wh}
  SCHEDULE = '1 MINUTE'
  WHEN SYSTEM\$STREAM_HAS_DATA('${db}.EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM')
  AS
  CALL ${db}.EDGARTOOLS_GOLD.PROCESS_RUN_MANIFEST_STREAM();
ALTER TASK ${db}.EDGARTOOLS_GOLD.SNOWFLAKE_RUN_MANIFEST_TASK RESUME;
"
}

echo "Deploying Snowflake stream processor task"
require_command snow
deploy_manifest_task

if [[ ${RUN_VALIDATION} -eq 1 ]]; then
  echo "Validating Terraform-managed native-pull contract"
  python3 "${REPO_ROOT}/infra/snowflake/sql/bootstrap_native_pull.py" \
    --aws-root "${AWS_ROOT}" \
    --snowflake-root "${SNOWFLAKE_ROOT}" \
    --connection "${SNOW_CONNECTION}" \
    --artifact-path "${VALIDATION_ARTIFACT}" \
    --validate-native-pull
fi

if [[ ${RUN_DBT} -eq 1 ]]; then
  echo "Running dbt deps/run/test"
  export DBT_SNOWFLAKE_DATABASE
  DBT_SNOWFLAKE_DATABASE="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "database_name")"
  export DBT_SNOWFLAKE_WAREHOUSE
  DBT_SNOWFLAKE_WAREHOUSE="$(json_map_value "${SNOWFLAKE_OUTPUTS_FILE}" "warehouse_names" "refresh")"
  # KNOWN GAP (2026-07-27, see CLAUDE.md manifest-pipeline ownership 5-whys): this pulls the
  # Terraform-managed "deployer" role (EDGARTOOLS_PROD_DEPLOYER in prod), NOT the EDGARTOOLS_PROD_LOADER
  # role that now owns the EDGARTOOLS_GOLD dynamic tables (infra/snowflake/sql/bootstrap/08_loader_role.sql).
  # Running --run-dbt as-is will re-flip ownership of the dynamic tables back to the deployer role and
  # can silently re-break REFRESH_AFTER_LOAD the same way it did in that incident.
  #
  # FIX WRITTEN, NOT YET APPLIED (2026-07-27): account_baseline/account_access Terraform now define a
  # "loader" role (renamed from the pre-existing, never-fully-granted "refresher" role -- see
  # infra/terraform/access/snowflake/modules/account_access/main.tf) with the grants EDGARTOOLS_PROD_LOADER
  # actually needs. Once that's applied (needs the AWS-root cross-stack outputs --
  # snowflake_storage_role_arn/snowflake_export_root_url/snowflake_manifest_sns_topic_arn -- wired in via
  # this script's normal flow, PLUS a check that the native_pull module's tracked snowflake_execute
  # procedure resources aren't holding a stale pre-cursor-fix SQL body that `apply` would revert),
  # switch the line below from "deployer" to "loader". Do not `--run-dbt` against prod until that
  # Terraform is actually applied and this line is switched -- switching the line first, before applying,
  # would just fail (the "loader" key doesn't exist in role_names output yet).
  export DBT_SNOWFLAKE_ROLE
  DBT_SNOWFLAKE_ROLE="$(json_map_value "${SNOWFLAKE_OUTPUTS_FILE}" "role_names" "deployer")"

  if [[ ! -f "${DBT_ROOT}/profiles.yml" ]]; then
    cp "${DBT_ROOT}/profiles.yml.example" "${DBT_ROOT}/profiles.yml"
  fi

  (
    cd "${DBT_ROOT}"
    uv run --with dbt-snowflake dbt deps
    uv run --with dbt-snowflake dbt run --target "${ENVIRONMENT}"
    uv run --with dbt-snowflake dbt test --target "${ENVIRONMENT}"
  )
fi

if [[ ${UPLOAD_DASHBOARD} -eq 1 ]]; then
  echo "Uploading Streamlit dashboard artifacts"
  DASHBOARD_DATABASE="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "database_name")"
  SNOW_CONNECTION="${SNOW_CONNECTION}" \
  DASHBOARD_DATABASE="${DASHBOARD_DATABASE}" \
  bash "${REPO_ROOT}/infra/snowflake/streamlit/deploy.sh"
fi

echo "Snowflake deployment complete for ${ENVIRONMENT}"
