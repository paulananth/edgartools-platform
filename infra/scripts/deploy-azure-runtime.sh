#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  deploy-azure-runtime.sh --env <dev|prod> [options]

Deploys Azure runtime workloads outside Terraform:
  - optional ACR image builds
  - Container Apps environment
  - warehouse Container Apps Jobs
  - Neo4j Container App
  - MDM API Container App
  - MDM Container Apps Jobs

Terraform outputs are used only for passive infrastructure discovery. Pass
--no-terraform-discovery and explicit resource flags to avoid Terraform CLI use.

Options:
  --env <dev|prod>                  Environment name. Required.
  --name-prefix <prefix>            Resource prefix. Default: edgartools-<env>.
  --resource-group <name>           Azure resource group.
  --location <region>               Azure region. Defaults to the resource group location.
  --acr-name <name>                 Azure Container Registry name.
  --acr-login-server <server>       ACR login server.
  --key-vault-name <name>           Azure Key Vault name for runtime secrets.
  --log-analytics-workspace-id <id> Log Analytics workspace resource ID.
  --runtime-identity-id <id>        User-assigned managed identity resource ID.
  --runtime-identity-client-id <id> User-assigned managed identity client ID.
  --warehouse-bronze-root <uri>     WAREHOUSE_BRONZE_ROOT.
  --warehouse-storage-root <uri>    WAREHOUSE_STORAGE_ROOT.
  --serving-export-root <uri>       SERVING_EXPORT_ROOT.
  --image-tag <tag>                 Mutable image tag. Default: <env>.
  --pipelines-image <image>         Full warehouse pipelines image reference.
  --mdm-image <image>               Full MDM image reference.
  --warehouse-runtime-mode <mode>   bronze_capture or infrastructure_validation. Default: bronze_capture.
  --build-images                    Build and push both Azure images before deployment.
  --daily-cron <expr>               Deploy daily incremental job as a scheduled job.
  --full-reconcile-cron <expr>      Deploy full reconcile job as a scheduled job.
  --skip-warehouse-jobs             Do not deploy warehouse jobs.
  --skip-daily-job                  Do not deploy the daily incremental job.
  --skip-full-reconcile-job         Do not deploy the full reconcile job.
  --skip-mdm                        Do not deploy Neo4j, MDM API, or MDM jobs.
  --skip-neo4j                      Do not deploy Neo4j.
  --skip-mdm-api                    Do not deploy MDM API.
  --skip-mdm-jobs                   Do not deploy MDM jobs.
  --mdm-neo4j-storage-account <n>   Azure Files storage account for Neo4j.
  --mdm-neo4j-storage-share <n>     Azure Files share for Neo4j. Default from Terraform or neo4j-data.
  --neo4j-image <image>             Neo4j image. Default: neo4j:5-community.
  --neo4j-external                  Expose Neo4j TCP ingress externally.
  --mdm-api-external                Expose MDM API ingress externally.
  --mdm-silver-duckdb <uri>         MDM_SILVER_DUCKDB. Default: <warehouse-storage-root>/silver/sec/silver.duckdb.
  --mdm-run-limit <n>               Default limit for the mdm-run job. 0 means no limit.
  --graph-limit <n>                 Default graph job limit. Default: 100.
  --run-schema                     Run the MDM schema migration job after deployment.
  --schema-no-seed                  Pass --no-seed to mdm migrate when --run-schema is set.
  --access-terraform-root <path>    Azure access Terraform root. Default: infra/terraform/access/azure/accounts/<env>.
  --no-terraform-discovery          Require explicit flags; do not run terraform output.
USAGE
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

is_empty() {
  [[ -z "${1:-}" || "${1:-}" == "null" ]]
}

ENVIRONMENT=""
NAME_PREFIX=""
RESOURCE_GROUP=""
LOCATION=""
ACR_NAME=""
ACR_LOGIN_SERVER=""
KEY_VAULT_NAME=""
LOG_ANALYTICS_WORKSPACE_ID=""
RUNTIME_IDENTITY_ID=""
RUNTIME_IDENTITY_CLIENT_ID=""
WAREHOUSE_BRONZE_ROOT=""
WAREHOUSE_STORAGE_ROOT=""
SERVING_EXPORT_ROOT=""
IMAGE_TAG=""
PIPELINES_IMAGE=""
MDM_IMAGE=""
WAREHOUSE_RUNTIME_MODE="bronze_capture"
BUILD_IMAGES=false
USE_TERRAFORM_DISCOVERY=true
ACCESS_TF_ROOT=""
DAILY_CRON=""
FULL_RECONCILE_CRON=""
SKIP_WAREHOUSE_JOBS=false
SKIP_DAILY_JOB=false
SKIP_FULL_RECONCILE_JOB=false
SKIP_MDM=false
SKIP_NEO4J=false
SKIP_MDM_API=false
SKIP_MDM_JOBS=false
MDM_NEO4J_STORAGE_ACCOUNT=""
MDM_NEO4J_STORAGE_SHARE=""
NEO4J_IMAGE="neo4j:5-community"
NEO4J_EXTERNAL=false
MDM_API_EXTERNAL=false
MDM_SILVER_DUCKDB=""
MDM_RUN_LIMIT=0
GRAPH_LIMIT=100
RUN_SCHEMA=false
SCHEMA_NO_SEED=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="${2:?}"; shift 2 ;;
    --name-prefix) NAME_PREFIX="${2:?}"; shift 2 ;;
    --resource-group) RESOURCE_GROUP="${2:?}"; shift 2 ;;
    --location) LOCATION="${2:?}"; shift 2 ;;
    --acr-name) ACR_NAME="${2:?}"; shift 2 ;;
    --acr-login-server) ACR_LOGIN_SERVER="${2:?}"; shift 2 ;;
    --key-vault-name) KEY_VAULT_NAME="${2:?}"; shift 2 ;;
    --log-analytics-workspace-id) LOG_ANALYTICS_WORKSPACE_ID="${2:?}"; shift 2 ;;
    --runtime-identity-id) RUNTIME_IDENTITY_ID="${2:?}"; shift 2 ;;
    --runtime-identity-client-id) RUNTIME_IDENTITY_CLIENT_ID="${2:?}"; shift 2 ;;
    --warehouse-bronze-root) WAREHOUSE_BRONZE_ROOT="${2:?}"; shift 2 ;;
    --warehouse-storage-root) WAREHOUSE_STORAGE_ROOT="${2:?}"; shift 2 ;;
    --serving-export-root) SERVING_EXPORT_ROOT="${2:?}"; shift 2 ;;
    --image-tag) IMAGE_TAG="${2:?}"; shift 2 ;;
    --pipelines-image) PIPELINES_IMAGE="${2:?}"; shift 2 ;;
    --mdm-image) MDM_IMAGE="${2:?}"; shift 2 ;;
    --warehouse-runtime-mode) WAREHOUSE_RUNTIME_MODE="${2:?}"; shift 2 ;;
    --build-images) BUILD_IMAGES=true; shift ;;
    --daily-cron) DAILY_CRON="${2:?}"; shift 2 ;;
    --full-reconcile-cron) FULL_RECONCILE_CRON="${2:?}"; shift 2 ;;
    --skip-warehouse-jobs) SKIP_WAREHOUSE_JOBS=true; shift ;;
    --skip-daily-job) SKIP_DAILY_JOB=true; shift ;;
    --skip-full-reconcile-job) SKIP_FULL_RECONCILE_JOB=true; shift ;;
    --skip-mdm) SKIP_MDM=true; shift ;;
    --skip-neo4j) SKIP_NEO4J=true; shift ;;
    --skip-mdm-api|--skip-api) SKIP_MDM_API=true; shift ;;
    --skip-mdm-jobs) SKIP_MDM_JOBS=true; shift ;;
    --mdm-neo4j-storage-account) MDM_NEO4J_STORAGE_ACCOUNT="${2:?}"; shift 2 ;;
    --mdm-neo4j-storage-share) MDM_NEO4J_STORAGE_SHARE="${2:?}"; shift 2 ;;
    --neo4j-image) NEO4J_IMAGE="${2:?}"; shift 2 ;;
    --neo4j-external) NEO4J_EXTERNAL=true; shift ;;
    --mdm-api-external) MDM_API_EXTERNAL=true; shift ;;
    --mdm-silver-duckdb) MDM_SILVER_DUCKDB="${2:?}"; shift 2 ;;
    --mdm-run-limit) MDM_RUN_LIMIT="${2:?}"; shift 2 ;;
    --graph-limit) GRAPH_LIMIT="${2:?}"; shift 2 ;;
    --run-schema) RUN_SCHEMA=true; shift ;;
    --schema-no-seed) SCHEMA_NO_SEED=true; shift ;;
    --access-terraform-root) ACCESS_TF_ROOT="${2:?}"; shift 2 ;;
    --no-terraform-discovery) USE_TERRAFORM_DISCOVERY=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$ENVIRONMENT" == "dev" || "$ENVIRONMENT" == "prod" ]] || { usage >&2; exit 2; }
[[ "$WAREHOUSE_RUNTIME_MODE" == "bronze_capture" || "$WAREHOUSE_RUNTIME_MODE" == "infrastructure_validation" ]] || fail "--warehouse-runtime-mode must be bronze_capture or infrastructure_validation"
[[ "$MDM_RUN_LIMIT" =~ ^[0-9]+$ ]] || fail "--mdm-run-limit must be a non-negative integer"
[[ "$GRAPH_LIMIT" =~ ^[0-9]+$ ]] || fail "--graph-limit must be a non-negative integer"

require_command az
require_command python3

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_DIR="${REPO_ROOT}/infra/scripts"
TF_ROOT="${REPO_ROOT}/infra/terraform/azure/accounts/${ENVIRONMENT}"
ACCESS_TF_ROOT="${ACCESS_TF_ROOT:-${REPO_ROOT}/infra/terraform/access/azure/accounts/${ENVIRONMENT}}"
NAME_PREFIX="${NAME_PREFIX:-edgartools-${ENVIRONMENT}}"
IMAGE_TAG="${IMAGE_TAG:-$ENVIRONMENT}"

tf_out() {
  if [[ "$USE_TERRAFORM_DISCOVERY" != "true" || ! -d "$TF_ROOT" ]]; then
    return 0
  fi
  terraform -chdir="$TF_ROOT" output -raw "$1" 2>/dev/null || true
}

tf_access_out() {
  if [[ "$USE_TERRAFORM_DISCOVERY" != "true" || ! -d "$ACCESS_TF_ROOT" ]]; then
    return 0
  fi
  terraform -chdir="$ACCESS_TF_ROOT" output -raw "$1" 2>/dev/null || true
}

first_nonempty() {
  local value
  for value in "$@"; do
    if ! is_empty "$value"; then
      printf '%s\n' "$value"
      return 0
    fi
  done
  return 0
}

SUBSCRIPTION_ID="$(az account show --query id -o tsv --only-show-errors)"
RESOURCE_GROUP="$(first_nonempty "$RESOURCE_GROUP" "$(tf_out resource_group_name)" "${NAME_PREFIX}-rg")"
LOCATION="$(first_nonempty "$LOCATION" "$(az group show --name "$RESOURCE_GROUP" --query location -o tsv --only-show-errors 2>/dev/null || true)")"
ACR_LOGIN_SERVER="$(first_nonempty "$ACR_LOGIN_SERVER" "$(tf_out container_registry_login_server)")"
if is_empty "$ACR_NAME" && ! is_empty "$ACR_LOGIN_SERVER"; then
  ACR_NAME="${ACR_LOGIN_SERVER%%.*}"
fi
if ! is_empty "$ACR_NAME" && is_empty "$ACR_LOGIN_SERVER"; then
  ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv --only-show-errors 2>/dev/null || true)"
fi
KEY_VAULT_NAME="$(first_nonempty "$KEY_VAULT_NAME" "$(tf_out key_vault_name)")"
LOG_ANALYTICS_WORKSPACE_ID="$(first_nonempty "$LOG_ANALYTICS_WORKSPACE_ID" "$(tf_out log_analytics_workspace_id)")"
RUNTIME_IDENTITY_CLIENT_ID="$(first_nonempty "$RUNTIME_IDENTITY_CLIENT_ID" "$(tf_access_out runtime_identity_client_id)" "$(tf_out runtime_identity_client_id)")"
WAREHOUSE_BRONZE_ROOT="$(first_nonempty "$WAREHOUSE_BRONZE_ROOT" "$(tf_out warehouse_bronze_root)")"
WAREHOUSE_STORAGE_ROOT="$(first_nonempty "$WAREHOUSE_STORAGE_ROOT" "$(tf_out warehouse_storage_root)")"
SERVING_EXPORT_ROOT="$(first_nonempty "$SERVING_EXPORT_ROOT" "$(tf_out serving_export_root)")"
MDM_NEO4J_STORAGE_ACCOUNT="$(first_nonempty "$MDM_NEO4J_STORAGE_ACCOUNT" "$(tf_out mdm_neo4j_storage_account_name)")"
MDM_NEO4J_STORAGE_SHARE="$(first_nonempty "$MDM_NEO4J_STORAGE_SHARE" "$(tf_out mdm_neo4j_storage_share_name)" "neo4j-data")"

if is_empty "$RUNTIME_IDENTITY_ID" || is_empty "$RUNTIME_IDENTITY_CLIENT_ID"; then
  RUNTIME_IDENTITY_ID="$(first_nonempty "$RUNTIME_IDENTITY_ID" "$(tf_access_out runtime_identity_id)")"
  identity_json="$(az identity show --name "${NAME_PREFIX}-jobs" --resource-group "$RESOURCE_GROUP" -o json --only-show-errors 2>/dev/null || true)"
  if ! is_empty "$identity_json"; then
    RUNTIME_IDENTITY_ID="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("id",""))' <<<"$identity_json")"
    RUNTIME_IDENTITY_CLIENT_ID="$(first_nonempty "$RUNTIME_IDENTITY_CLIENT_ID" "$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("clientId",""))' <<<"$identity_json")")"
  fi
fi

is_empty "$LOCATION" && fail "could not resolve Azure location; pass --location"
is_empty "$ACR_LOGIN_SERVER" && fail "could not resolve ACR login server; pass --acr-name or --acr-login-server"
is_empty "$ACR_NAME" && fail "could not resolve ACR name; pass --acr-name"
is_empty "$KEY_VAULT_NAME" && fail "could not resolve Key Vault name; pass --key-vault-name"
is_empty "$RUNTIME_IDENTITY_ID" && fail "could not resolve runtime managed identity ID; pass --runtime-identity-id"
is_empty "$RUNTIME_IDENTITY_CLIENT_ID" && fail "could not resolve runtime managed identity client ID; pass --runtime-identity-client-id"

PIPELINES_IMAGE="${PIPELINES_IMAGE:-${ACR_LOGIN_SERVER}/edgar-warehouse-pipelines:${IMAGE_TAG}}"
MDM_IMAGE="${MDM_IMAGE:-${ACR_LOGIN_SERVER}/edgar-warehouse-mdm-neo4j:${IMAGE_TAG}}"
KEY_VAULT_URI="https://${KEY_VAULT_NAME}.vault.azure.net"
ENV_NAME="${NAME_PREFIX}-jobs"
ENV_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/managedEnvironments/${ENV_NAME}"
TAG_JSON="{\"Environment\":\"${ENVIRONMENT}\",\"ManagedBy\":\"operator-script\",\"Project\":\"edgartools\"}"

if [[ "$BUILD_IMAGES" == "true" ]]; then
  bash "${SCRIPT_DIR}/build-azure-images.sh" \
    --env "$ENVIRONMENT" \
    --acr-name "$ACR_NAME" \
    --image-tag "$IMAGE_TAG" \
    --role all
fi

if [[ "$SKIP_WAREHOUSE_JOBS" != "true" ]]; then
  is_empty "$WAREHOUSE_BRONZE_ROOT" && fail "warehouse jobs require --warehouse-bronze-root"
  is_empty "$WAREHOUSE_STORAGE_ROOT" && fail "warehouse jobs require --warehouse-storage-root"
  is_empty "$SERVING_EXPORT_ROOT" && fail "warehouse jobs require --serving-export-root"
fi

if [[ "$SKIP_MDM" != "true" ]]; then
  if [[ "$SKIP_NEO4J" != "true" ]]; then
    is_empty "$MDM_NEO4J_STORAGE_ACCOUNT" && fail "Neo4j deployment requires --mdm-neo4j-storage-account"
  fi
  if is_empty "$MDM_SILVER_DUCKDB" && ! is_empty "$WAREHOUSE_STORAGE_ROOT"; then
    MDM_SILVER_DUCKDB="${WAREHOUSE_STORAGE_ROOT}/silver/sec/silver.duckdb"
  fi
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/edgartools-azure-runtime-XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_file() {
  mktemp "${TMP_DIR}/$1-XXXXXX.json"
}

put_arm() {
  local label="$1" url="$2" body_file="$3"
  echo "==> Deploying ${label}"
  az rest \
    --method put \
    --url "$url" \
    --body @"$body_file" \
    --only-show-errors \
    -o none
}

ensure_containerapp_environment() {
  if az containerapp env show --name "$ENV_NAME" --resource-group "$RESOURCE_GROUP" --query id -o tsv --only-show-errors >/dev/null 2>&1; then
    echo "==> Container Apps environment exists: ${ENV_NAME}"
    return 0
  fi

  if is_empty "$LOG_ANALYTICS_WORKSPACE_ID"; then
    LOG_ANALYTICS_WORKSPACE_ID="$(
      az monitor log-analytics workspace show \
        --resource-group "$RESOURCE_GROUP" \
        --workspace-name "${NAME_PREFIX}-logs" \
        --query id -o tsv --only-show-errors 2>/dev/null || true
    )"
  fi
  is_empty "$LOG_ANALYTICS_WORKSPACE_ID" && fail "Container Apps environment creation requires --log-analytics-workspace-id"

  local workspace_name workspace_rg workspace_customer_id workspace_key
  workspace_name="$(basename "$LOG_ANALYTICS_WORKSPACE_ID")"
  workspace_rg="$(python3 - "$LOG_ANALYTICS_WORKSPACE_ID" <<'PY'
import sys
parts = [p for p in sys.argv[1].split("/") if p]
try:
    print(parts[parts.index("resourceGroups") + 1])
except Exception:
    print("")
PY
)"
  is_empty "$workspace_rg" && workspace_rg="$RESOURCE_GROUP"
  workspace_customer_id="$(az monitor log-analytics workspace show --ids "$LOG_ANALYTICS_WORKSPACE_ID" --query customerId -o tsv --only-show-errors)"
  workspace_key="$(
    az monitor log-analytics workspace get-shared-keys \
      --resource-group "$workspace_rg" \
      --workspace-name "$workspace_name" \
      --query primarySharedKey -o tsv --only-show-errors
  )"

  echo "==> Creating Container Apps environment: ${ENV_NAME}"
  az containerapp env create \
    --name "$ENV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --logs-workspace-id "$workspace_customer_id" \
    --logs-workspace-key "$workspace_key" \
    --environment-mode ConsumptionOnly \
    --tags Environment="$ENVIRONMENT" ManagedBy=operator-script Project=edgartools \
    --only-show-errors \
    -o none
}

write_job_body() {
  local output_file="$1" container_name="$2" image="$3" cpu="$4" memory="$5" timeout_seconds="$6" retry_limit="$7" cron_expression="$8" secret_mode="$9"
  shift 9
  python3 - "$output_file" "$LOCATION" "$ENV_ID" "$RUNTIME_IDENTITY_ID" "$RUNTIME_IDENTITY_CLIENT_ID" \
    "$ACR_LOGIN_SERVER" "$ENVIRONMENT" "$TAG_JSON" "$container_name" "$image" "$cpu" "$memory" \
    "$timeout_seconds" "$retry_limit" "$cron_expression" "$secret_mode" "$KEY_VAULT_URI" \
    "$WAREHOUSE_RUNTIME_MODE" "$WAREHOUSE_BRONZE_ROOT" "$WAREHOUSE_STORAGE_ROOT" "$SERVING_EXPORT_ROOT" \
    "$MDM_SILVER_DUCKDB" "$@" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    location,
    env_id,
    identity_id,
    identity_client_id,
    acr_login_server,
    environment,
    tag_json,
    container_name,
    image,
    cpu,
    memory,
    timeout_seconds,
    retry_limit,
    cron_expression,
    secret_mode,
    key_vault_uri,
    warehouse_runtime_mode,
    warehouse_bronze_root,
    warehouse_storage_root,
    serving_export_root,
    mdm_silver_duckdb,
    *args,
) = sys.argv[1:]

tags = json.loads(tag_json)
cpu_value = float(cpu)
secrets = []
env = [{"name": "AZURE_CLIENT_ID", "value": identity_client_id}]

if secret_mode == "warehouse":
    secrets.append({
        "name": "edgar-identity",
        "keyVaultUrl": f"{key_vault_uri}/secrets/edgar-identity",
        "identity": identity_id,
    })
    env.insert(0, {"name": "EDGAR_IDENTITY", "secretRef": "edgar-identity"})
    env.extend([
        {"name": "WAREHOUSE_ENVIRONMENT", "value": environment},
        {"name": "WAREHOUSE_RUNTIME_MODE", "value": warehouse_runtime_mode},
        {"name": "WAREHOUSE_BRONZE_ROOT", "value": warehouse_bronze_root},
        {"name": "WAREHOUSE_STORAGE_ROOT", "value": warehouse_storage_root},
        {"name": "SERVING_EXPORT_ROOT", "value": serving_export_root},
    ])
elif secret_mode == "mdm":
    for name in (
        "mdm-database-url",
        "mdm-neo4j-uri",
        "mdm-neo4j-user",
        "mdm-neo4j-password",
        "mdm-api-keys-csv",
    ):
        secrets.append({
            "name": name,
            "keyVaultUrl": f"{key_vault_uri}/secrets/{name}",
            "identity": identity_id,
        })
    env.extend([
        {"name": "MDM_DATABASE_URL", "secretRef": "mdm-database-url"},
        {"name": "NEO4J_URI", "secretRef": "mdm-neo4j-uri"},
        {"name": "NEO4J_USER", "secretRef": "mdm-neo4j-user"},
        {"name": "NEO4J_PASSWORD", "secretRef": "mdm-neo4j-password"},
        {"name": "MDM_API_KEYS", "secretRef": "mdm-api-keys-csv"},
    ])
    if mdm_silver_duckdb:
        env.append({"name": "MDM_SILVER_DUCKDB", "value": mdm_silver_duckdb})
else:
    raise SystemExit(f"unknown secret mode: {secret_mode}")

configuration = {
    "triggerType": "Schedule" if cron_expression else "Manual",
    "replicaTimeout": int(timeout_seconds),
    "replicaRetryLimit": int(retry_limit),
    "registries": [{"server": acr_login_server, "identity": identity_id}],
    "secrets": secrets,
}
if cron_expression:
    configuration["scheduleTriggerConfig"] = {
        "cronExpression": cron_expression,
        "parallelism": 1,
        "replicaCompletionCount": 1,
    }
else:
    configuration["manualTriggerConfig"] = {
        "parallelism": 1,
        "replicaCompletionCount": 1,
    }

body = {
    "location": location,
    "tags": tags,
    "identity": {
        "type": "UserAssigned",
        "userAssignedIdentities": {identity_id: {}},
    },
    "properties": {
        "environmentId": env_id,
        "configuration": configuration,
        "template": {
            "containers": [{
                "name": container_name,
                "image": image,
                "args": args,
                "env": env,
                "resources": {"cpu": cpu_value, "memory": memory},
            }],
        },
    },
}
pathlib.Path(output_file).write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
PY
}

deploy_job() {
  local job_name="$1" container_name="$2" image="$3" cpu="$4" memory="$5" timeout_seconds="$6" retry_limit="$7" cron_expression="$8" secret_mode="$9"
  shift 9
  local body_file url
  body_file="$(json_file "$job_name")"
  write_job_body "$body_file" "$container_name" "$image" "$cpu" "$memory" "$timeout_seconds" "$retry_limit" "$cron_expression" "$secret_mode" "$@"
  url="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/jobs/${job_name}?api-version=2024-03-01"
  put_arm "job ${job_name}" "$url" "$body_file"
}

write_container_app_body() {
  local output_file="$1" app_kind="$2"
  python3 - "$output_file" "$app_kind" "$LOCATION" "$ENV_ID" "$RUNTIME_IDENTITY_ID" "$RUNTIME_IDENTITY_CLIENT_ID" \
    "$ACR_LOGIN_SERVER" "$ENVIRONMENT" "$TAG_JSON" "$KEY_VAULT_URI" "$MDM_IMAGE" "$NEO4J_IMAGE" \
    "$NEO4J_EXTERNAL" "$MDM_API_EXTERNAL" "${NAME_PREFIX}-neo4j-data" <<'PY'
import json
import pathlib
import sys

(
    output_file,
    app_kind,
    location,
    env_id,
    identity_id,
    identity_client_id,
    acr_login_server,
    environment,
    tag_json,
    key_vault_uri,
    mdm_image,
    neo4j_image,
    neo4j_external,
    mdm_api_external,
    neo4j_storage_name,
) = sys.argv[1:]

tags = json.loads(tag_json)
external_neo4j = neo4j_external == "true"
external_api = mdm_api_external == "true"

base = {
    "location": location,
    "tags": tags,
    "properties": {"environmentId": env_id},
}

if app_kind == "neo4j":
    base["identity"] = {
        "type": "UserAssigned",
        "userAssignedIdentities": {identity_id: {}},
    }
    base["properties"].update({
        "configuration": {
            "activeRevisionsMode": "Single",
            "secrets": [{
                "name": "neo4j-auth",
                "keyVaultUrl": f"{key_vault_uri}/secrets/mdm-neo4j-auth",
                "identity": identity_id,
            }],
            "ingress": {
                "external": external_neo4j,
                "targetPort": 7687,
                "exposedPort": 7687,
                "transport": "tcp",
                "traffic": [{"latestRevision": True, "weight": 100}],
            },
        },
        "template": {
            "scale": {"minReplicas": 1, "maxReplicas": 1},
            "containers": [{
                "name": "neo4j",
                "image": neo4j_image,
                "env": [
                    {"name": "NEO4J_AUTH", "secretRef": "neo4j-auth"},
                    {"name": "NEO4J_server_default__listen__address", "value": "0.0.0.0"},
                    {"name": "NEO4J_server_bolt_listen__address", "value": "0.0.0.0:7687"},
                    {"name": "NEO4J_dbms_security_auth__enabled", "value": "true"},
                ],
                "resources": {"cpu": 2.0, "memory": "4Gi"},
                "volumeMounts": [{"volumeName": "neo4j-data", "mountPath": "/data"}],
            }],
            "volumes": [{
                "name": "neo4j-data",
                "storageType": "AzureFile",
                "storageName": neo4j_storage_name,
            }],
        },
    })
elif app_kind == "mdm-api":
    secrets = []
    for name in (
        "mdm-database-url",
        "mdm-neo4j-uri",
        "mdm-neo4j-user",
        "mdm-neo4j-password",
        "mdm-api-keys-csv",
    ):
        secrets.append({
            "name": name,
            "keyVaultUrl": f"{key_vault_uri}/secrets/{name}",
            "identity": identity_id,
        })
    base["identity"] = {
        "type": "UserAssigned",
        "userAssignedIdentities": {identity_id: {}},
    }
    base["properties"].update({
        "configuration": {
            "activeRevisionsMode": "Single",
            "registries": [{"server": acr_login_server, "identity": identity_id}],
            "secrets": secrets,
            "ingress": {
                "external": external_api,
                "targetPort": 8080,
                "transport": "auto",
                "traffic": [{"latestRevision": True, "weight": 100}],
            },
        },
        "template": {
            "scale": {"minReplicas": 1, "maxReplicas": 3},
            "containers": [{
                "name": "mdm-api",
                "image": mdm_image,
                "args": ["mdm", "api", "--host", "0.0.0.0", "--port", "8080"],
                "env": [
                    {"name": "AZURE_CLIENT_ID", "value": identity_client_id},
                    {"name": "MDM_DATABASE_URL", "secretRef": "mdm-database-url"},
                    {"name": "NEO4J_URI", "secretRef": "mdm-neo4j-uri"},
                    {"name": "NEO4J_USER", "secretRef": "mdm-neo4j-user"},
                    {"name": "NEO4J_PASSWORD", "secretRef": "mdm-neo4j-password"},
                    {"name": "MDM_API_KEYS", "secretRef": "mdm-api-keys-csv"},
                ],
                "resources": {"cpu": 1.0, "memory": "2Gi"},
            }],
        },
    })
else:
    raise SystemExit(f"unknown app kind: {app_kind}")

pathlib.Path(output_file).write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
PY
}

deploy_container_app() {
  local app_name="$1" app_kind="$2" body_file url
  body_file="$(json_file "$app_name")"
  write_container_app_body "$body_file" "$app_kind"
  url="https://management.azure.com/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.App/containerApps/${app_name}?api-version=2024-03-01"
  put_arm "container app ${app_name}" "$url" "$body_file"
}

ensure_containerapp_environment

echo "==> Runtime deployment settings"
echo "    environment      : ${ENVIRONMENT}"
echo "    resource group   : ${RESOURCE_GROUP}"
echo "    container env    : ${ENV_NAME}"
echo "    ACR              : ${ACR_LOGIN_SERVER}"
echo "    pipelines image  : ${PIPELINES_IMAGE}"
echo "    MDM image        : ${MDM_IMAGE}"

if [[ "$SKIP_WAREHOUSE_JOBS" != "true" ]]; then
  deploy_job "${NAME_PREFIX}-seed-universe" "edgar-warehouse" "$PIPELINES_IMAGE" 1 "2Gi" 3600 0 "" "warehouse" \
    seed-universe
  deploy_job "${NAME_PREFIX}-boot-recent-10" "edgar-warehouse" "$PIPELINES_IMAGE" 2 "4Gi" 21600 0 "" "warehouse" \
    bootstrap-recent-10 --no-include-reference-refresh
  if [[ "$SKIP_DAILY_JOB" != "true" ]]; then
    deploy_job "${NAME_PREFIX}-daily-incr" "edgar-warehouse" "$PIPELINES_IMAGE" 1 "2Gi" 7200 1 "$DAILY_CRON" "warehouse" \
      daily-incremental
  fi
  if [[ "$SKIP_FULL_RECONCILE_JOB" != "true" ]]; then
    deploy_job "${NAME_PREFIX}-full-reconcile" "edgar-warehouse" "$PIPELINES_IMAGE" 2 "4Gi" 21600 1 "$FULL_RECONCILE_CRON" "warehouse" \
      full-reconcile
  fi
fi

if [[ "$SKIP_MDM" != "true" ]]; then
  if [[ "$SKIP_NEO4J" != "true" ]]; then
    account_key="$(
      az storage account keys list \
        --resource-group "$RESOURCE_GROUP" \
        --account-name "$MDM_NEO4J_STORAGE_ACCOUNT" \
        --query '[0].value' -o tsv --only-show-errors
    )"
    echo "==> Binding Neo4j Azure Files storage to Container Apps environment"
    az containerapp env storage set \
      --name "$ENV_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --storage-name "${NAME_PREFIX}-neo4j-data" \
      --access-mode ReadWrite \
      --azure-file-account-name "$MDM_NEO4J_STORAGE_ACCOUNT" \
      --azure-file-account-key "$account_key" \
      --azure-file-share-name "$MDM_NEO4J_STORAGE_SHARE" \
      --only-show-errors \
      -o none
    deploy_container_app "${NAME_PREFIX}-neo4j" "neo4j"
  fi

  if [[ "$SKIP_MDM_API" != "true" ]]; then
    deploy_container_app "${NAME_PREFIX}-mdm-api" "mdm-api"
  fi

  if [[ "$SKIP_MDM_JOBS" != "true" ]]; then
    run_args=(mdm run --entity-type all)
    if [[ "$MDM_RUN_LIMIT" -gt 0 ]]; then
      run_args+=(--limit "$MDM_RUN_LIMIT")
    fi
    deploy_job "${NAME_PREFIX}-mdm-migrate" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      mdm migrate
    deploy_job "${NAME_PREFIX}-mdm-run" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      "${run_args[@]}"
    deploy_job "${NAME_PREFIX}-mdm-counts" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      mdm counts
    deploy_job "${NAME_PREFIX}-mdm-graph-load" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      mdm backfill-relationships --limit "$GRAPH_LIMIT"
    deploy_job "${NAME_PREFIX}-mdm-graph-sync" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      mdm sync-graph --limit "$GRAPH_LIMIT"
    deploy_job "${NAME_PREFIX}-mdm-graph-verify" "mdm" "$MDM_IMAGE" 1 "2Gi" 7200 1 "" "mdm" \
      mdm verify-graph
  fi
fi

if [[ "$RUN_SCHEMA" == "true" ]]; then
  schema_args=(--env "$ENVIRONMENT" --resource-group "$RESOURCE_GROUP" --name-prefix "$NAME_PREFIX")
  if [[ "$SCHEMA_NO_SEED" == "true" ]]; then
    schema_args+=(--no-seed)
  fi
  bash "${SCRIPT_DIR}/run-azure-mdm-schema.sh" "${schema_args[@]}"
fi

echo "==> Azure runtime deployment complete"
