#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash infra/scripts/deploy-snowflake-stack.sh [options]

Options:
  --env <dev|prod>           Target environment. Default: dev
  --snow-connection <name>   SnowCLI connection used for validation and dashboard upload.
  --run-validation           Run SnowCLI-based native-pull validation artifact generation.
  --run-dbt                  Run dbt deps/run/test.
  --upload-dashboard         Upload dashboard artifacts.

This is an explicit post-infra Snowflake/database-object operator script. dbt,
dashboard upload, and validation are opt-in.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ENVIRONMENT="dev"
SNOW_CONNECTION=""
RUN_VALIDATION=0
RUN_DBT=0
UPLOAD_DASHBOARD=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
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

case "$ENVIRONMENT" in
  dev|prod) ;;
  *)
    die "--env must be dev or prod"
    ;;
esac

SNOW_CONNECTION="${SNOW_CONNECTION:-edgartools-${ENVIRONMENT}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
TMP_DIR="${REPO_ROOT}/.tmp"

AWS_ROOT="${REPO_ROOT}/infra/terraform/access/aws/accounts/${ENVIRONMENT}"
SNOWFLAKE_ROOT="${REPO_ROOT}/infra/terraform/snowflake/accounts/${ENVIRONMENT}"
SNOWFLAKE_ACCESS_ROOT="${REPO_ROOT}/infra/terraform/access/snowflake/accounts/${ENVIRONMENT}"
DBT_ROOT="${REPO_ROOT}/infra/snowflake/dbt/edgartools_gold"
VALIDATION_ARTIFACT="${REPO_ROOT}/infra/snowflake/sql/${ENVIRONMENT}_native_pull_handshake.json"

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

if [[ ${RUN_VALIDATION} -eq 1 || ${UPLOAD_DASHBOARD} -eq 1 ]]; then
  require_command snow
fi

if [[ ${RUN_DBT} -eq 1 ]]; then
  require_command dbt
  [[ -n "${DBT_SNOWFLAKE_ACCOUNT:-}" ]] || die "DBT_SNOWFLAKE_ACCOUNT must be set when dbt is enabled"
  [[ -n "${DBT_SNOWFLAKE_USER:-}" ]] || die "DBT_SNOWFLAKE_USER must be set when dbt is enabled"
  [[ -n "${DBT_SNOWFLAKE_PASSWORD:-}" ]] || die "DBT_SNOWFLAKE_PASSWORD must be set when dbt is enabled"
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

echo "Applying Snowflake native-pull module"
write_snowflake_overlay "${SNOWFLAKE_OVERLAY}" "${STORAGE_ROLE_ARN}" "${EXPORT_ROOT_URL}" "${MANIFEST_SNS_TOPIC_ARN}" "${EXTERNAL_ID}"
terraform_apply "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OVERLAY}"
terraform_output_json "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OUTPUTS_FILE}"

SUBSCRIBER_ARN="$(json_value "${SNOWFLAKE_OUTPUTS_FILE}" "snowflake_manifest_subscriber_arn")"
[[ -n "${SUBSCRIBER_ARN}" ]] || die "Snowflake apply did not produce snowflake_manifest_subscriber_arn"

echo "Reconciling AWS trust to the exact Snowflake principal"
write_aws_overlay "${AWS_RECONCILE_OVERLAY}" "false" "${SUBSCRIBER_ARN}" "${EXTERNAL_ID}"
terraform_apply "${AWS_ROOT}" "${AWS_RECONCILE_OVERLAY}"
terraform_output_json "${AWS_ROOT}" "${AWS_OUTPUTS_FILE}"

echo "Re-applying Snowflake after AWS trust reconciliation"
terraform_apply "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OVERLAY}"
terraform_output_json "${SNOWFLAKE_ROOT}" "${SNOWFLAKE_OUTPUTS_FILE}"

echo "Applying Snowflake access-control grants"
terraform_apply_root "${SNOWFLAKE_ACCESS_ROOT}"
terraform_output_json "${SNOWFLAKE_ACCESS_ROOT}" "${SNOWFLAKE_ACCESS_OUTPUTS_FILE}"

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
  export DBT_SNOWFLAKE_ROLE
  DBT_SNOWFLAKE_ROLE="$(json_map_value "${SNOWFLAKE_OUTPUTS_FILE}" "role_names" "deployer")"

  if [[ ! -f "${DBT_ROOT}/profiles.yml" ]]; then
    cp "${DBT_ROOT}/profiles.yml.example" "${DBT_ROOT}/profiles.yml"
  fi

  (
    cd "${DBT_ROOT}"
    dbt deps
    dbt run --target "${ENVIRONMENT}"
    dbt test --target "${ENVIRONMENT}"
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
