#!/usr/bin/env bash
# Stage 4 — Composite-key MERGE semantics smoke test (REQUIRES Snowflake creds).
#
# Verifies the new LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN proc's composite-key MERGE
# actually upserts (not duplicates) by direct INSERT+SELECT against the source
# tables.  Tests:
#   - Idempotency: insert same row twice, COUNT = 1
#   - Update on conflict: change a non-key column, observe the change
#   - NOT NULL enforcement: NULL PK column rejected by Snowflake
#
# This is a DIRECT-INSERT smoke test — it does NOT exercise the full Parquet
# COPY INTO + MERGE path (that requires PR-2's warehouse export to land a real
# Parquet file in S3).  Stage 5 covers the full roundtrip.
#
# Prerequisites
# -------------
#   - Snowflake CLI v3+ (snowflake-cli-labs): `pip install snowflake-cli-labs`
#   - A configured connection in ~/.snowflake/connections.toml.
#
# Required env vars
# -----------------
#   SNOW_CONNECTION       — name of the snow CLI connection (e.g. "edgartools-dev")
#   SNOWFLAKE_DATABASE    — e.g. EDGARTOOLS_DEV

# shellcheck disable=SC1091
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_lib.sh"

step "Stage 4 — Composite-key MERGE semantics smoke test"

require_command snow
require_env SNOW_CONNECTION
require_env SNOWFLAKE_DATABASE

SOURCE_SCHEMA="${SNOWFLAKE_SOURCE_SCHEMA:-EDGARTOOLS_SOURCE}"
TEST_CIK="999999991"
TEST_ACCESSION="0000-pr1-verify-${TEST_CIK}"

# Track whether the test ran (skip teardown if setup failed)
TEST_STARTED=false

cleanup() {
    if $TEST_STARTED; then
        log "Cleaning up test rows for CIK=${TEST_CIK}"
        snow_sql_exec "DELETE FROM ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT WHERE CIK = ${TEST_CIK};" || true
        snow_sql_exec "DROP TABLE IF EXISTS TMP_PR1_VERIFY;" || true
    fi
}
trap cleanup EXIT

# ── 1. Idempotency: INSERT then MERGE with same composite key → COUNT=1 ──
log "Test 1 — composite-key idempotency"
TEST_STARTED=true

if snow_sql_exec "
    INSERT INTO ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT
        (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, VALUE, PARSER_VERSION)
    VALUES
        (${TEST_CIK}, '${TEST_ACCESSION}', 'Revenues', 'FY', 'consolidated', 100.0, 'pr1-verify');
"; then
    ok "first INSERT succeeded"
else
    fail_check "first INSERT FAILED"
    print_summary "4 merge-proc-smoke"
    exit 1
fi

# Re-INSERT the same row via MERGE pattern (matches what the JS proc emits).
# IMPORTANT: each snow_sql_exec call opens a FRESH session, so a TEMPORARY
# table created in one call does not survive into the next.  We must bundle
# the temp-table create + insert + merge into a SINGLE invocation so they
# share one session.  snow_sql_file() does this — it tokenizes the file
# and submits each statement via a single Python connector cursor.
log "  (simulating proc's MERGE via a temp table to test idempotency)"

MERGE_SQL_FILE=$(mktemp -t pr1-merge-XXXXXX.sql)
cat > "$MERGE_SQL_FILE" <<EOSQL
CREATE OR REPLACE TEMPORARY TABLE ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.TMP_PR1_VERIFY
    LIKE ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT;

INSERT INTO ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.TMP_PR1_VERIFY
    (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, VALUE, PARSER_VERSION)
VALUES
    (${TEST_CIK}, '${TEST_ACCESSION}', 'Revenues', 'FY', 'consolidated', 200.0, 'pr1-verify-v2');

MERGE INTO ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT AS target
USING ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.TMP_PR1_VERIFY AS source
ON target.CIK = source.CIK
   AND target.ACCESSION_NUMBER = source.ACCESSION_NUMBER
   AND target.CONCEPT = source.CONCEPT
   AND target.FISCAL_PERIOD = source.FISCAL_PERIOD
   AND target.SEGMENT = source.SEGMENT
WHEN MATCHED THEN UPDATE SET
    VALUE = source.VALUE,
    PARSER_VERSION = source.PARSER_VERSION
WHEN NOT MATCHED THEN INSERT
    (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, VALUE, PARSER_VERSION)
    VALUES (source.CIK, source.ACCESSION_NUMBER, source.CONCEPT, source.FISCAL_PERIOD,
            source.SEGMENT, source.VALUE, source.PARSER_VERSION);
EOSQL

if snow_sql_file "$MERGE_SQL_FILE"; then
    ok "MERGE upsert succeeded"
else
    fail_check "MERGE upsert FAILED — re-run with: snow sql --connection ${SNOW_CONNECTION} --filename ${MERGE_SQL_FILE}"
fi
rm -f "$MERGE_SQL_FILE"

# After insert + merge: should be exactly 1 row, value should be the new value
count="$(snow_scalar "SELECT COUNT(*) FROM ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT WHERE CIK = ${TEST_CIK};")"
if [[ "$count" == "1" ]]; then
    ok "composite-key MERGE is idempotent (COUNT=1 after INSERT+MERGE)"
else
    fail_check "composite-key MERGE NOT idempotent — expected COUNT=1, got ${count}"
fi

value="$(snow_scalar "SELECT VALUE FROM ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT WHERE CIK = ${TEST_CIK};")"
if [[ "$value" == "200" ]] || [[ "$value" == "200.0" ]] || [[ "$value" == "200.000000" ]]; then
    ok "MERGE updated non-key column (VALUE: 100.0 → 200.0)"
else
    fail_check "MERGE did NOT update non-key column — expected 200.0, got ${value}"
fi

# ── 2. NOT NULL enforcement on PK columns (Q5-C invariant) ─────────
log "Test 2 — NOT NULL enforcement on PK columns (Q5-C)"

# Try INSERT with NULL CIK (PK column) — should fail
if snow_sql_exec "
    INSERT INTO ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT
        (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, VALUE)
    VALUES (NULL, 'bad', 'Revenues', 'FY', 'consolidated', 1.0);
"; then
    fail_check "NULL CIK INSERT was ACCEPTED (NOT NULL constraint not enforced!)"
else
    ok "NULL CIK INSERT was REJECTED (NOT NULL constraint enforced)"
fi

# Try INSERT with NULL CONCEPT (composite PK part) — should fail
if snow_sql_exec "
    INSERT INTO ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.SEC_FINANCIAL_FACT
        (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, VALUE)
    VALUES (${TEST_CIK}, 'bad', NULL, 'FY', 'consolidated', 1.0);
"; then
    fail_check "NULL CONCEPT INSERT was ACCEPTED (NOT NULL on composite PK part not enforced!)"
else
    ok "NULL CONCEPT INSERT was REJECTED (composite-PK NOT NULL enforced)"
fi

# ── 3. Procedure invocation smoke (proc exists and parses) ─────────
log "Test 3 — invoke LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN with a fake run id"

# Should fail with "No run manifest found" — that proves the proc parses and
# runs to its first SELECT.  It should NOT raise an "unknown procedure" error.
result="$(snow sql --connection "$SNOW_CONNECTION" --format json --query \
    "CALL ${SNOWFLAKE_DATABASE}.${SOURCE_SCHEMA}.LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN('pr1-verify-workflow', 'pr1-verify-${TEST_CIK}');" \
    2>&1 || true)"

if printf '%s' "$result" | grep -qiE "No run manifest|manifest"; then
    ok "proc invocation parses and runs (expected 'No run manifest' error received)"
elif printf '%s' "$result" | grep -qiE "does not exist|unknown procedure"; then
    fail_check "proc does NOT exist in Snowflake — re-run stage 3"
else
    warn "unexpected proc response: ${result%%$'\n'*}"
fi

print_summary "4 merge-proc-smoke"
