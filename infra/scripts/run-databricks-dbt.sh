#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  run-databricks-dbt.sh --target <databricks_dev|databricks_prod> [--key-vault-name <name>] [--skip-run] [--skip-test]

Requires dbt-databricks and DBT_DATABRICKS_HOST, DBT_DATABRICKS_HTTP_PATH,
DBT_DATABRICKS_TOKEN, and DBT_DATABRICKS_CATALOG. With --key-vault-name,
missing DBT_* values are read from Azure Key Vault secrets.
USAGE
}

TARGET=""
KEY_VAULT_NAME=""
SKIP_RUN="false"
SKIP_TEST="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:?}"; shift 2 ;;
    --key-vault-name) KEY_VAULT_NAME="${2:?}"; shift 2 ;;
    --skip-run) SKIP_RUN="true"; shift ;;
    --skip-test) SKIP_TEST="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ "$TARGET" != "databricks_dev" && "$TARGET" != "databricks_prod" ]]; then
  usage >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DBT_ROOT="${REPO_ROOT}/infra/snowflake/dbt/edgartools_gold"

kv_secret() {
  az keyvault secret show \
    --vault-name "$KEY_VAULT_NAME" \
    --name "$1" \
    --query value \
    -o tsv \
    --only-show-errors
}

hydrate_required_env_from_key_vault() {
  local env_name="$1"
  local secret_name="$2"
  if [[ -n "${!env_name:-}" || -z "$KEY_VAULT_NAME" ]]; then
    return
  fi
  export "$env_name=$(kv_secret "$secret_name")"
}

hydrate_optional_env_from_key_vault() {
  local env_name="$1"
  local secret_name="$2"
  if [[ -n "${!env_name:-}" || -z "$KEY_VAULT_NAME" ]]; then
    return
  fi
  local value
  if value="$(kv_secret "$secret_name" 2>/dev/null)" && [[ -n "$value" ]]; then
    export "$env_name=$value"
  fi
}

hydrate_required_env_from_key_vault DBT_DATABRICKS_HOST databricks-host
hydrate_required_env_from_key_vault DBT_DATABRICKS_HTTP_PATH databricks-http-path
hydrate_required_env_from_key_vault DBT_DATABRICKS_TOKEN databricks-token
hydrate_optional_env_from_key_vault DBT_DATABRICKS_CATALOG databricks-catalog
hydrate_optional_env_from_key_vault DBT_SOURCE_SCHEMA dbt-source-schema
hydrate_optional_env_from_key_vault DBT_GOLD_SCHEMA dbt-gold-schema

cd "$DBT_ROOT"
dbt deps
dbt parse --target "$TARGET"
dbt compile --target "$TARGET"

if [[ "$SKIP_RUN" == "false" ]]; then
  dbt run --target "$TARGET"
fi

if [[ "$SKIP_TEST" == "false" ]]; then
  dbt test --target "$TARGET"
fi
