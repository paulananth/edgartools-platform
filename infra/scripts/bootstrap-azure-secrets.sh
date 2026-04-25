#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-azure-secrets.sh --key-vault-name <name> --edgar-identity <user-agent> [options]

Options:
  --databricks-host <url>
  --databricks-http-path <path>
  --databricks-token <token>
  --databricks-client-id <client-id>
  --databricks-client-secret <client-secret>
  --databricks-catalog <catalog>
  --dbt-source-schema <schema>
  --dbt-gold-schema <schema>

Stores runtime and dbt secrets in Azure Key Vault using Azure CLI. Secret values are
not written to Terraform state or repo-tracked files.
USAGE
}

KEY_VAULT_NAME=""
EDGAR_IDENTITY=""
OPTIONAL_SECRET_NAMES=()
OPTIONAL_SECRET_VALUES=()

add_optional_secret() {
  OPTIONAL_SECRET_NAMES+=("$1")
  OPTIONAL_SECRET_VALUES+=("$2")
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key-vault-name) KEY_VAULT_NAME="${2:?}"; shift 2 ;;
    --edgar-identity) EDGAR_IDENTITY="${2:?}"; shift 2 ;;
    --databricks-host) add_optional_secret "databricks-host" "${2:?}"; shift 2 ;;
    --databricks-http-path) add_optional_secret "databricks-http-path" "${2:?}"; shift 2 ;;
    --databricks-token) add_optional_secret "databricks-token" "${2:?}"; shift 2 ;;
    --databricks-client-id) add_optional_secret "databricks-client-id" "${2:?}"; shift 2 ;;
    --databricks-client-secret) add_optional_secret "databricks-client-secret" "${2:?}"; shift 2 ;;
    --databricks-catalog) add_optional_secret "databricks-catalog" "${2:?}"; shift 2 ;;
    --dbt-source-schema) add_optional_secret "dbt-source-schema" "${2:?}"; shift 2 ;;
    --dbt-gold-schema) add_optional_secret "dbt-gold-schema" "${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$KEY_VAULT_NAME" || -z "$EDGAR_IDENTITY" ]]; then
  usage >&2
  exit 2
fi

if [[ "$EDGAR_IDENTITY" != *"@"* ]]; then
  echo "ERROR: --edgar-identity must include a contact email for the SEC User-Agent header." >&2
  exit 2
fi

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name edgar-identity \
  --value "$EDGAR_IDENTITY" \
  --only-show-errors \
  >/dev/null

for index in "${!OPTIONAL_SECRET_NAMES[@]}"; do
  secret_name="${OPTIONAL_SECRET_NAMES[$index]}"
  az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name "$secret_name" \
    --value "${OPTIONAL_SECRET_VALUES[$index]}" \
    --only-show-errors \
    >/dev/null
done

echo "Stored secrets in Key Vault: $KEY_VAULT_NAME"
