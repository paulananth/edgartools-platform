#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-azure-secrets.sh --key-vault-name <name> [options]

Options:
  --edgar-identity <user-agent>
  --mdm-database-url <url>
  --mdm-neo4j-uri <uri>
  --mdm-neo4j-user <user>
  --mdm-neo4j-password <password>
  --mdm-neo4j-auth <user/password>
  --mdm-api-key <key>              Repeatable.
  --mdm-api-keys-csv <keys>        Comma-delimited API keys.
  --databricks-host <url>
  --databricks-http-path <path>
  --databricks-token <token>
  --databricks-client-id <client-id>
  --databricks-client-secret <client-secret>
  --databricks-catalog <catalog>
  --dbt-source-schema <schema>
  --dbt-gold-schema <schema>

Stores runtime, MDM, and dbt secrets in Azure Key Vault using Azure CLI. Secret
values are not written to Terraform state or repo-tracked files.
USAGE
}

KEY_VAULT_NAME=""
EDGAR_IDENTITY=""
MDM_NEO4J_USER=""
MDM_NEO4J_PASSWORD=""
MDM_NEO4J_URI=""
MDM_NEO4J_AUTH=""
MDM_API_KEYS=()
MDM_API_KEYS_CSV=""
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
    --mdm-database-url) add_optional_secret "mdm-database-url" "${2:?}"; shift 2 ;;
    --mdm-neo4j-uri) MDM_NEO4J_URI="${2:?}"; shift 2 ;;
    --mdm-neo4j-user) MDM_NEO4J_USER="${2:?}"; shift 2 ;;
    --mdm-neo4j-password) MDM_NEO4J_PASSWORD="${2:?}"; shift 2 ;;
    --mdm-neo4j-auth) MDM_NEO4J_AUTH="${2:?}"; shift 2 ;;
    --mdm-api-key) MDM_API_KEYS+=("${2:?}"); shift 2 ;;
    --mdm-api-keys-csv) MDM_API_KEYS_CSV="${2:?}"; shift 2 ;;
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

if [[ -z "$KEY_VAULT_NAME" ]]; then
  usage >&2
  exit 2
fi

if [[ -n "$EDGAR_IDENTITY" && "$EDGAR_IDENTITY" != *"@"* ]]; then
  echo "ERROR: --edgar-identity must include a contact email for the SEC User-Agent header." >&2
  exit 2
fi

if [[ -n "$MDM_NEO4J_USER" ]]; then
  add_optional_secret "mdm-neo4j-user" "$MDM_NEO4J_USER"
fi

if [[ -n "$MDM_NEO4J_PASSWORD" ]]; then
  add_optional_secret "mdm-neo4j-password" "$MDM_NEO4J_PASSWORD"
fi

if [[ -n "$MDM_NEO4J_URI" ]]; then
  add_optional_secret "mdm-neo4j-uri" "$MDM_NEO4J_URI"
fi

if [[ -z "$MDM_NEO4J_AUTH" && -n "$MDM_NEO4J_USER" && -n "$MDM_NEO4J_PASSWORD" ]]; then
  MDM_NEO4J_AUTH="${MDM_NEO4J_USER}/${MDM_NEO4J_PASSWORD}"
fi

if [[ -n "$MDM_NEO4J_AUTH" ]]; then
  add_optional_secret "mdm-neo4j-auth" "$MDM_NEO4J_AUTH"
fi

if [[ -n "$MDM_NEO4J_URI" && -n "$MDM_NEO4J_USER" && -n "$MDM_NEO4J_PASSWORD" ]]; then
  neo4j_json="$(
    python3 - "$MDM_NEO4J_URI" "$MDM_NEO4J_USER" "$MDM_NEO4J_PASSWORD" <<'PY'
import json
import sys

uri, user, password = sys.argv[1:]
print(json.dumps({"uri": uri, "user": user, "password": password}))
PY
  )"
  add_optional_secret "mdm-neo4j" "$neo4j_json"
fi

if [[ ${#MDM_API_KEYS[@]} -gt 0 && -z "$MDM_API_KEYS_CSV" ]]; then
  old_ifs="$IFS"
  IFS=,
  MDM_API_KEYS_CSV="${MDM_API_KEYS[*]}"
  IFS="$old_ifs"
fi

if [[ -n "$MDM_API_KEYS_CSV" ]]; then
  add_optional_secret "mdm-api-keys-csv" "$MDM_API_KEYS_CSV"
  api_keys_json="$(
    python3 - "$MDM_API_KEYS_CSV" <<'PY'
import json
import sys

keys = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
print(json.dumps({"keys": keys}))
PY
  )"
  add_optional_secret "mdm-api-keys" "$api_keys_json"
fi

if [[ -z "$EDGAR_IDENTITY" && ${#OPTIONAL_SECRET_NAMES[@]} -eq 0 ]]; then
  usage >&2
  exit 2
fi

if [[ -n "$EDGAR_IDENTITY" ]]; then
  az keyvault secret set \
    --vault-name "$KEY_VAULT_NAME" \
    --name edgar-identity \
    --value "$EDGAR_IDENTITY" \
    --only-show-errors \
    >/dev/null
fi

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
