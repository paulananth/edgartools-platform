#!/usr/bin/env bash
# Stage 3 — Snowflake DDL deployment (REQUIRES Snowflake credentials).
#
# Deploys the PR-1 DDL + procedures to dev Snowflake and verifies they land.
# Idempotent: every CREATE uses IF NOT EXISTS or OR REPLACE, so safe to re-run.
#
# Prerequisites (one of these auth paths):
#   - snowsql with ~/.snowsql/config configured for $SNOWSQL_CONNECTION
#   - Env vars: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD,
#               SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE, SNOWFLAKE_DATABASE
#
# Required env vars for variable substitution:
#   SNOWFLAKE_DATABASE                 — e.g. EDGARTOOLS_DEV
#   SNOWFLAKE_DEPLOYER_ROLE            — e.g. EDGARTOOLS_DEV_DEPLOYER
#   SNOWFLAKE_STORAGE_ROLE_ARN         — IAM role ARN Snowflake assumes for S3 reads
#   SNOWFLAKE_EXPORT_ROOT_URL          — s3://edgartools-{env}-snowflake-export/warehouse/artifacts/snowflake_exports/
#   SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN   — arn:aws:sns:{region}:{acct}:edgartools-{env}-snowflake-manifest-events

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

step "Stage 3 — Snowflake DDL deployment"

require_command snowsql
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

# ── 1. Apply 01_source_stage.sql ────────────────────────────────────
log "Applying 01_source_stage.sql"
snowsql -q "
    SET database_name = '${SNOWFLAKE_DATABASE}';
    SET source_schema_name = '${SOURCE_SCHEMA}';
    SET deployer_role_name = '${SNOWFLAKE_DEPLOYER_ROLE}';
    SET storage_integration_name = '${STORAGE_INTEGRATION}';
    SET storage_role_arn = '${SNOWFLAKE_STORAGE_ROLE_ARN}';
    SET storage_external_id = NULL;
    SET export_root_url = '${SNOWFLAKE_EXPORT_ROOT_URL}';
    SET stage_name = '${STAGE_NAME}';
    SET parquet_file_format_name = '${PARQUET_FF}';
    SET manifest_file_format_name = '${MANIFEST_FF}';
    SET manifest_inbox_table_name = '${INBOX_TABLE}';
    SET manifest_pipe_name = '${MANIFEST_PIPE}';
    SET manifest_sns_topic_arn = '${SNOWFLAKE_MANIFEST_SNS_TOPIC_ARN}';
" -f "${REPO_ROOT}/infra/snowflake/sql/bootstrap/01_source_stage.sql" \
    -o output_format=plain -o friendly=false -o quiet=true \
    && ok "01_source_stage.sql applied" \
    || fail_check "01_source_stage.sql FAILED to apply (check snowsql output)"

# ── 2. Apply 03_source_load_wrapper.sql (extends existing proc with 3 dim entries) ──
log "Applying 03_source_load_wrapper.sql"
snowsql -q "
    SET database_name = '${SNOWFLAKE_DATABASE}';
    SET source_schema_name = '${SOURCE_SCHEMA}';
    SET deployer_role_name = '${SNOWFLAKE_DEPLOYER_ROLE}';
    SET source_load_procedure_name = '${SOURCE_LOAD_PROC}';
" -f "${REPO_ROOT}/infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql" \
    -o output_format=plain -o friendly=false -o quiet=true \
    && ok "03_source_load_wrapper.sql applied" \
    || fail_check "03_source_load_wrapper.sql FAILED to apply"

# ── 3. Apply 06_fundamentals_load_wrapper.sql (NEW) ─────────────────
log "Applying 06_fundamentals_load_wrapper.sql"
snowsql -q "
    SET database_name = '${SNOWFLAKE_DATABASE}';
    SET source_schema_name = '${SOURCE_SCHEMA}';
    SET deployer_role_name = '${SNOWFLAKE_DEPLOYER_ROLE}';
    SET fundamentals_load_procedure_name = '${FUNDAMENTALS_LOAD_PROC}';
" -f "${REPO_ROOT}/infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql" \
    -o output_format=plain -o friendly=false -o quiet=true \
    && ok "06_fundamentals_load_wrapper.sql applied" \
    || fail_check "06_fundamentals_load_wrapper.sql FAILED to apply"

# ── 4. Verify the 6 source tables exist ─────────────────────────────
log "Verifying source tables exist in ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}"

count_table() {
    local table_name="$1"
    snowsql -q "SELECT COUNT(*) FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='${SOURCE_SCHEMA}' AND TABLE_NAME='${table_name}';" \
        -o output_format=plain -o header=false -o friendly=false -o quiet=true 2>/dev/null | tr -d ' \r\n'
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
    result=$(snowsql -q "SELECT IS_NULLABLE FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='${SOURCE_SCHEMA}' AND TABLE_NAME='${table}' AND COLUMN_NAME='${col}';" \
        -o output_format=plain -o header=false -o friendly=false -o quiet=true 2>/dev/null | tr -d ' \r\n')
    [[ "$result" == "NO" ]]
}

# Use parallel arrays — bash 3.2 (macOS default) has no associative arrays.
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
    for col in $cols; do
        if ! check_not_null "$table" "$col"; then
            bad+="${col} "
        fi
    done
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
    snowsql -q "SELECT COUNT(*) FROM ${SNOWFLAKE_DATABASE}.INFORMATION_SCHEMA.PROCEDURES WHERE PROCEDURE_SCHEMA='${SOURCE_SCHEMA}' AND PROCEDURE_NAME='${proc}';" \
        -o output_format=plain -o header=false -o friendly=false -o quiet=true 2>/dev/null | tr -d ' \r\n'
}

for proc in "$SOURCE_LOAD_PROC" "$FUNDAMENTALS_LOAD_PROC"; do
    if [[ "$(check_procedure "$proc")" -ge "1" ]]; then
        ok "procedure ${proc} exists"
    else
        fail_check "procedure ${proc} NOT FOUND"
    fi
done

print_summary "3 snowflake-ddl-deployment"
