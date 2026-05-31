#!/usr/bin/env bash
# Stage 3 — Snowflake DDL deployment (REQUIRES Snowflake credentials).
#
# Deploys the PR-1 DDL + procedures to dev Snowflake and verifies they land.
# Idempotent: every CREATE uses IF NOT EXISTS or OR REPLACE, so safe to re-run.
#
# Prerequisites
# -------------
#   - Snowflake CLI v3+ (snowflake-cli-labs): `pip install snowflake-cli-labs`
#   - A configured connection: `snow connection add` writes
#     ~/.snowflake/connections.toml.  Set SNOW_CONNECTION to its name.
#
# Required env vars
# -----------------
#   SNOW_CONNECTION                    — name of the snow CLI connection (e.g. "edgartools-dev")
#   SNOWFLAKE_DATABASE                 — e.g. EDGARTOOLS_DEV
#   SNOWFLAKE_DEPLOYER_ROLE            — e.g. EDGARTOOLS_DEV_DEPLOYER
#   SNOWFLAKE_STORAGE_ROLE_ARN         — IAM role ARN Snowflake assumes for S3 reads
#   SNOWFLAKE_EXPORT_ROOT_URL          — s3://edgartools-{env}-snowflake-export/warehouse/artifacts/snowflake_exports/
#   SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN   — arn:aws:sns:{region}:{acct}:edgartools-{env}-snowflake-manifest-events

# shellcheck disable=SC1091
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_lib.sh"

step "Stage 3 — Snowflake DDL deployment"

require_command snow
require_env SNOW_CONNECTION
require_env SNOWFLAKE_DATABASE
require_env SNOWFLAKE_DEPLOYER_ROLE
require_env SNOWFLAKE_STORAGE_ROLE_ARN
require_env SNOWFLAKE_EXPORT_ROOT_URL
require_env SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN

# Optional env vars with sensible defaults
SOURCE_SCHEMA="${SNOWFLAKE_SOURCE_SCHEMA:-EDGARTOOLS_SOURCE}"
STORAGE_INTEGRATION="${SNOWFLAKE_STORAGE_INTEGRATION:-${SNOWFLAKE_DATABASE}_EXPORT_INTEGRATION}"
STAGE_NAME="${SNOWFLAKE_STAGE_NAME:-EDGARTOOLS_SOURCE_EXPORT_STAGE}"
PARQUET_FF="${SNOWFLAKE_PARQUET_FF:-EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT}"
MANIFEST_FF="${SNOWFLAKE_MANIFEST_FF:-EDGARTOOLS_SOURCE_RUN_MANIFEST_FILE_FORMAT}"
INBOX_TABLE="${SNOWFLAKE_INBOX_TABLE:-SNOWFLAKE_RUN_MANIFEST_INBOX}"
MANIFEST_PIPE="${SNOWFLAKE_MANIFEST_PIPE:-SNOWFLAKE_RUN_MANIFEST_PIPE}"
SOURCE_LOAD_PROC="${SNOWFLAKE_SOURCE_LOAD_PROC:-LOAD_EXPORTS_FOR_RUN}"
FUNDAMENTALS_LOAD_PROC="${SNOWFLAKE_FUNDAMENTALS_LOAD_PROC:-LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN}"

# Build a temp SQL file that prepends SET-variable lines to a bootstrap file.
# The bootstrap SQL files use `IDENTIFIER($var)` references that need session
# vars set before the file is executed.
build_sql_with_vars() {
    local source_file="$1"
    shift  # remaining args are "var=value" pairs
    local tmp
    tmp=$(mktemp -t pr1-snow-XXXXXX.sql)
    {
        for kv in "$@"; do
            local k="${kv%%=*}"
            local v="${kv#*=}"
            if [[ "$v" == "NULL" ]]; then
                printf 'SET %s = NULL;\n' "$k"
            else
                printf "SET %s = '%s';\n" "$k" "${v//\'/\'\'}"
            fi
        done
        cat "$source_file"
    } > "$tmp"
    echo "$tmp"
}

# ── 1. Apply 01_source_stage.sql ────────────────────────────────────
log "Applying 01_source_stage.sql"
TMP_01="$(build_sql_with_vars \
    "${REPO_ROOT}/infra/snowflake/sql/bootstrap/01_source_stage.sql" \
    "database_name=${SNOWFLAKE_DATABASE}" \
    "source_schema_name=${SOURCE_SCHEMA}" \
    "deployer_role_name=${SNOWFLAKE_DEPLOYER_ROLE}" \
    "storage_integration_name=${STORAGE_INTEGRATION}" \
    "storage_role_arn=${SNOWFLAKE_STORAGE_ROLE_ARN}" \
    "storage_external_id=NULL" \
    "export_root_url=${SNOWFLAKE_EXPORT_ROOT_URL}" \
    "stage_name=${STAGE_NAME}" \
    "parquet_file_format_name=${PARQUET_FF}" \
    "manifest_file_format_name=${MANIFEST_FF}" \
    "manifest_inbox_table_name=${INBOX_TABLE}" \
    "manifest_pipe_name=${MANIFEST_PIPE}" \
    "manifest_sns_topic_arn=${SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN}" \
)"
trap 'rm -f "$TMP_01" "${TMP_03:-}" "${TMP_06:-}"' EXIT

if snow_sql_file "$TMP_01"; then
    ok "01_source_stage.sql applied"
else
    fail_check "01_source_stage.sql FAILED to apply"
    log "  re-run for details: snow sql --connection ${SNOW_CONNECTION} --filename ${TMP_01}"
fi

# ── 2. Apply 03_source_load_wrapper.sql (extends existing proc with 3 dim entries) ──
log "Applying 03_source_load_wrapper.sql"
TMP_03="$(build_sql_with_vars \
    "${REPO_ROOT}/infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql" \
    "database_name=${SNOWFLAKE_DATABASE}" \
    "source_schema_name=${SOURCE_SCHEMA}" \
    "deployer_role_name=${SNOWFLAKE_DEPLOYER_ROLE}" \
    "source_load_procedure_name=${SOURCE_LOAD_PROC}" \
)"

if snow_sql_file "$TMP_03"; then
    ok "03_source_load_wrapper.sql applied"
else
    fail_check "03_source_load_wrapper.sql FAILED to apply"
    log "  re-run for details: snow sql --connection ${SNOW_CONNECTION} --filename ${TMP_03}"
fi

# ── 3. Apply 06_fundamentals_load_wrapper.sql (NEW in PR-1) ─────────
log "Applying 06_fundamentals_load_wrapper.sql"
TMP_06="$(build_sql_with_vars \
    "${REPO_ROOT}/infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql" \
    "database_name=${SNOWFLAKE_DATABASE}" \
    "source_schema_name=${SOURCE_SCHEMA}" \
    "deployer_role_name=${SNOWFLAKE_DEPLOYER_ROLE}" \
    "fundamentals_load_procedure_name=${FUNDAMENTALS_LOAD_PROC}" \
)"

if snow_sql_file "$TMP_06"; then
    ok "06_fundamentals_load_wrapper.sql applied"
else
    fail_check "06_fundamentals_load_wrapper.sql FAILED to apply"
    log "  re-run for details: snow sql --connection ${SNOW_CONNECTION} --filename ${TMP_06}"
fi

# ── 4. Verify the 6 source tables exist ─────────────────────────────
log "Verifying source tables exist in ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}"

count_table() {
    local table_name="$1"
    snow_scalar "SELECT COUNT(*) FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '${SOURCE_SCHEMA}' AND TABLE_NAME = '${table_name}' AND TABLE_TYPE = 'BASE TABLE';"
}

for table in SEC_FINANCIAL_FACT SEC_THIRTEENF_HOLDING SEC_FINANCIAL_DERIVED \
             EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if [[ "$(count_table "$table")" == "1" ]]; then
        ok "${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.${table} exists"
    else
        fail_check "${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.${table} NOT FOUND"
    fi
done

# ── 5. Verify PK columns are NOT NULL in Snowflake metadata ─────────
log "Verifying NOT NULL constraints on PK columns"

check_not_null() {
    local table="$1" col="$2"
    local result
    result="$(snow_scalar "SELECT IS_NULLABLE FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '${SOURCE_SCHEMA}' AND TABLE_NAME = '${table}' AND COLUMN_NAME = '${col}';")"
    [[ "$result" == "NO" ]]
}

# Parallel arrays — bash 3.2 (macOS default) has no associative arrays.
pk_tables=(
    "SEC_FINANCIAL_FACT"
    "SEC_THIRTEENF_HOLDING"
    "SEC_FINANCIAL_DERIVED"
    "EARNINGS_RELEASE"
    "EXECUTIVE_RECORD"
    "ACCOUNTING_FLAG"
)
pk_columns_list=(
    "CIK ACCESSION_NUMBER CONCEPT FISCAL_PERIOD SEGMENT"
    "CIK ACCESSION_NUMBER HOLDING_INDEX"
    "CIK ACCESSION_NUMBER FISCAL_PERIOD"
    "FACT_KEY"
    "FACT_KEY"
    "FACT_KEY"
)

for i in "${!pk_tables[@]}"; do
    table="${pk_tables[$i]}"
    cols="${pk_columns_list[$i]}"
    bad=""
    # 00_lib.sh sets IFS=$'\n\t' to harden against filename-with-space bugs;
    # restore the default IFS just for the column-splitting loop so that
    # `for col in $cols` actually word-splits on spaces.
    OLDIFS="$IFS"
    IFS=$' \t\n'
    for col in $cols; do
        if ! check_not_null "$table" "$col"; then
            bad+="${col} "
        fi
    done
    IFS="$OLDIFS"
    if [[ -z "$bad" ]]; then
        ok "${table} PK columns are NOT NULL in Snowflake metadata"
    else
        fail_check "${table} columns NOT marked NOT NULL: ${bad}"
    fi
done

# ── 6. Verify both load procedures exist ────────────────────────────
log "Verifying load procedures"

check_procedure() {
    local proc="$1"
    snow_scalar "SELECT COUNT(*) FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.PROCEDURES WHERE PROCEDURE_SCHEMA = '${SOURCE_SCHEMA}' AND PROCEDURE_NAME = '${proc}';"
}

for proc in "$SOURCE_LOAD_PROC" "$FUNDAMENTALS_LOAD_PROC"; do
    count="$(check_procedure "$proc")"
    if [[ -n "$count" ]] && [[ "$count" -ge 1 ]]; then
        ok "procedure ${proc} exists"
    else
        fail_check "procedure ${proc} NOT FOUND (count=${count:-?})"
    fi
done

print_summary "3 snowflake-ddl-deployment"
