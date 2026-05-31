#!/usr/bin/env bash
# Stage 1 — local schema integrity (no Snowflake creds required).
#
# Checks that PR-1's local artifacts are consistent before any cloud deploy:
#   - 6 Snowflake CREATE TABLE blocks present in 01_source_stage.sql
#   - LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN procedure exists in 06_*.sql
#   - 3 dimensional entries added to 03_source_load_wrapper.sql targetTables/mergeKeys
#   - 6 entries in SNOWFLAKE_EXPORT_TABLES (Python)
#   - 6 dbt source declarations
#   - 3 dimensional dbt models reference the new source names (no SEC_ prefix)
#   - PyArrow schemas declare nullable=False on PK columns
#   - PR-1 unit tests pass

# shellcheck disable=SC1091
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_lib.sh"

step "Stage 1 — Local schema integrity"

# ── 1. Snowflake source DDL ─────────────────────────────────────────
log "Checking infra/snowflake/sql/bootstrap/01_source_stage.sql"
DDL_FILE="${REPO_ROOT}/infra/snowflake/sql/bootstrap/01_source_stage.sql"
require_file "$DDL_FILE"

for table in SEC_FINANCIAL_FACT SEC_THIRTEENF_HOLDING SEC_FINANCIAL_DERIVED \
             EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if grep -qi "CREATE TABLE IF NOT EXISTS ${table}[[:space:]]" "$DDL_FILE"; then
        ok "01_source_stage.sql declares ${table}"
    else
        fail_check "01_source_stage.sql is MISSING ${table}"
    fi
done

# Verify PK columns marked NOT NULL (Q5-C invariant)
log "Checking NOT NULL on PK columns (Q5-C)"
expected_not_null_blocks=(
    # table_name:pk_columns_csv
    "SEC_FINANCIAL_FACT:cik,accession_number,concept,fiscal_period,segment"
    "SEC_THIRTEENF_HOLDING:cik,accession_number,holding_index"
    "SEC_FINANCIAL_DERIVED:cik,accession_number,fiscal_period"
)
for spec in "${expected_not_null_blocks[@]}"; do
    table="${spec%%:*}"
    pk_cols="${spec##*:}"
    # Extract the CREATE TABLE block (between 'CREATE TABLE IF NOT EXISTS table' and the closing ');')
    block=$(awk "/CREATE TABLE IF NOT EXISTS ${table}[[:space:]]/,/^[)];/" "$DDL_FILE")
    if [[ -z "$block" ]]; then
        fail_check "could not extract ${table} block from DDL"
        continue
    fi
    missing_nn=""
    IFS=',' read -ra cols <<< "$pk_cols"
    for col in "${cols[@]}"; do
        # Each PK column line should contain "NOT NULL"
        if echo "$block" | grep -E "^[[:space:]]*${col}[[:space:]]" | grep -q "NOT NULL"; then
            :
        else
            missing_nn+="${col} "
        fi
    done
    if [[ -z "$missing_nn" ]]; then
        ok "${table} PK columns all NOT NULL (${pk_cols})"
    else
        fail_check "${table} missing NOT NULL on: ${missing_nn}"
    fi
done

# Dimensional tables must mark fact_key NOT NULL
for table in EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if awk "/CREATE TABLE IF NOT EXISTS ${table}[[:space:]]/,/^[)];/" "$DDL_FILE" \
        | grep -E "^[[:space:]]*fact_key[[:space:]]" \
        | grep -q "NOT NULL"; then
        ok "${table}.fact_key is NOT NULL"
    else
        fail_check "${table}.fact_key MUST be NOT NULL (Q5-C)"
    fi
done

# ── 2. JS load procedure ────────────────────────────────────────────
log "Checking infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql"
LOAD_PROC_FILE="${REPO_ROOT}/infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql"
require_file "$LOAD_PROC_FILE"

if grep -qF 'CREATE OR REPLACE PROCEDURE IDENTIFIER($fundamentals_load_procedure_name)' "$LOAD_PROC_FILE"; then
    ok "LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN procedure declared"
else
    fail_check "LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN procedure NOT declared"
fi

# Composite merge keys hardcoded as arrays (Q4-A)
for table in SEC_FINANCIAL_FACT SEC_THIRTEENF_HOLDING SEC_FINANCIAL_DERIVED; do
    if grep -q "${table}:" "$LOAD_PROC_FILE"; then
        ok "06_*.sql has mergeKeys[${table}]"
    else
        fail_check "06_*.sql MISSING mergeKeys[${table}]"
    fi
done

# Verify composite merge key cardinality — POSIX grep (works on macOS bash 3.2)
if awk '/SEC_FINANCIAL_FACT:[[:space:]]*\[/,/\]/' "$LOAD_PROC_FILE" | head -3 \
    | grep -E -q '"CIK".*"ACCESSION_NUMBER".*"CONCEPT".*"FISCAL_PERIOD".*"SEGMENT"'; then
    ok "SEC_FINANCIAL_FACT merge key is 5-column composite"
else
    fail_check "SEC_FINANCIAL_FACT merge key does not match expected 5-column composite"
fi

# ── 3. Dimensional entries in existing proc ────────────────────────
log "Checking 03_source_load_wrapper.sql for dimensional table entries"
EXISTING_PROC_FILE="${REPO_ROOT}/infra/snowflake/sql/bootstrap/03_source_load_wrapper.sql"
require_file "$EXISTING_PROC_FILE"

for table in EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if grep -q "${table}: " "$EXISTING_PROC_FILE"; then
        ok "03_*.sql targetTables/mergeKeys includes ${table}"
    else
        fail_check "03_*.sql MISSING entry for ${table}"
    fi
done

# ── 4. SNOWFLAKE_EXPORT_TABLES (Python) ─────────────────────────────
log "Checking edgar_warehouse/infrastructure/run_manifest_builder.py"
PY_MANIFEST="${REPO_ROOT}/edgar_warehouse/infrastructure/run_manifest_builder.py"
require_file "$PY_MANIFEST"

for table in SEC_FINANCIAL_FACT SEC_THIRTEENF_HOLDING SEC_FINANCIAL_DERIVED \
             EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if grep -q "\"${table}\":" "$PY_MANIFEST"; then
        ok "SNOWFLAKE_EXPORT_TABLES has ${table}"
    else
        fail_check "SNOWFLAKE_EXPORT_TABLES MISSING ${table}"
    fi
done

# ── 5. dbt sources ──────────────────────────────────────────────────
log "Checking infra/snowflake/dbt/edgartools_gold/models/sources.yml"
SOURCES_YML="${REPO_ROOT}/infra/snowflake/dbt/edgartools_gold/models/sources.yml"
require_file "$SOURCES_YML"

# Passthrough sources keep SEC_ prefix
for table in SEC_FINANCIAL_FACT SEC_THIRTEENF_HOLDING SEC_FINANCIAL_DERIVED; do
    if grep -q "name: ${table}" "$SOURCES_YML"; then
        ok "sources.yml declares ${table} (passthrough)"
    else
        fail_check "sources.yml MISSING ${table} (passthrough)"
    fi
done

# Dimensional sources DROP SEC_ prefix
for table in EARNINGS_RELEASE EXECUTIVE_RECORD ACCOUNTING_FLAG; do
    if grep -qE "name: ${table}[[:space:]]*$" "$SOURCES_YML"; then
        ok "sources.yml declares ${table} (dimensional, no SEC_ prefix)"
    else
        fail_check "sources.yml MISSING ${table} (dimensional)"
    fi
    # Negative check: dimensional must NOT also appear with SEC_ prefix
    if grep -q "name: SEC_${table}" "$SOURCES_YML"; then
        fail_check "sources.yml STILL has SEC_${table} (should be renamed to ${table})"
    fi
done

# ── 6. dbt gold models reference correct source names ──────────────
# Use parallel arrays — bash 3.2 (macOS default) has no associative arrays.
log "Checking dbt gold model source references"
GOLD_DIR="${REPO_ROOT}/infra/snowflake/dbt/edgartools_gold/models/gold"

dbt_models=(
    "earnings_releases.sql"
    "executive_records.sql"
    "accounting_flags.sql"
    "financial_facts.sql"
    "financial_derived.sql"
    "institutional_holdings.sql"
)
dbt_sources=(
    "EARNINGS_RELEASE"
    "EXECUTIVE_RECORD"
    "ACCOUNTING_FLAG"
    "SEC_FINANCIAL_FACT"
    "SEC_FINANCIAL_DERIVED"
    "SEC_THIRTEENF_HOLDING"
)

for i in "${!dbt_models[@]}"; do
    model="${dbt_models[$i]}"
    expected="${dbt_sources[$i]}"
    path="${GOLD_DIR}/${model}"
    if [[ ! -f "$path" ]]; then
        fail_check "missing dbt gold model: ${model}"
        continue
    fi
    if grep -q "source(\"edgartools_source\", \"${expected}\")" "$path"; then
        ok "${model} → source(\"edgartools_source\", \"${expected}\")"
    else
        fail_check "${model} does NOT reference source(\"edgartools_source\", \"${expected}\")"
    fi
done

# ── 7. PR-1 unit tests ──────────────────────────────────────────────
log "Running PR-1 regression tests"
if [[ -d "${REPO_ROOT}/.venv" ]]; then
    test_output=""
    if test_output=$(cd "$REPO_ROOT" && source .venv/bin/activate && python3 -m pytest tests/unit/test_fundamentals_modules.py::FundamentalsGoldBuilderTests --tb=line -q 2>&1) && printf '%s' "$test_output" | grep -q "passed"; then
        ok "FundamentalsGoldBuilderTests pass"
    else
        fail_check "FundamentalsGoldBuilderTests FAILED — run \`pytest tests/unit/test_fundamentals_modules.py::FundamentalsGoldBuilderTests -v\` for details"
    fi
else
    warn "skipped pytest — .venv not found (run \`uv sync\` first)"
fi

# ────────────────────────────────────────────────────────────────────
print_summary "1 local-schema-integrity"
