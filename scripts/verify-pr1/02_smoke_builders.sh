#!/usr/bin/env bash
# Stage 2 — PyArrow builder smoke test (no Snowflake creds required).
#
# Spins up an in-memory DuckDB with the silver schemas, inserts realistic
# AAPL/Berkshire fixtures, runs each of the 6 build functions, and asserts:
#   - row counts match what was inserted
#   - PyArrow schemas equal the declared schemas
#   - PK columns are marked nullable=False
#   - dimensional builders produce non-zero fact_keys (idempotent hash)
#
# Independent of Snowflake.  This is the gate that the warehouse Python side
# of PR-1 will produce Parquet conforming to the Snowflake CREATE TABLE shape.

# shellcheck disable=SC1091
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_lib.sh"

step "Stage 2 — PyArrow builder smoke test"

require_command python3

if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
    fatal "venv not found at ${REPO_ROOT}/.venv (run \`uv sync\` first)"
fi

# Run the smoke test in a Python script that uses pytest-style assertions.
# Each assertion failure prints a line, and we count results from exit code.
log "Running in-memory DuckDB → PyArrow build round-trip"

# shellcheck disable=SC1091
source "${REPO_ROOT}/.venv/bin/activate"

SMOKE_OUTPUT="$(cd "${REPO_ROOT}" && python3 - <<'PY' 2>&1
import sys
import duckdb
from edgar_warehouse.silver_store import _DDL
from edgar_warehouse.serving.gold_models import (
    _build_sec_financial_fact, _build_sec_thirteenf_holding, _build_sec_financial_derived,
    _build_fact_earnings_release, _build_fact_executive_record, _build_fact_accounting_flag,
    _SEC_FINANCIAL_FACT_SCHEMA, _SEC_THIRTEENF_HOLDING_SCHEMA, _SEC_FINANCIAL_DERIVED_SCHEMA,
    _FACT_EARNINGS_RELEASE_SCHEMA, _FACT_EXECUTIVE_RECORD_SCHEMA, _FACT_ACCOUNTING_FLAG_SCHEMA,
)

conn = duckdb.connect(":memory:")
conn.execute(_DDL)

fixtures = [
    """INSERT INTO sec_financial_fact (cik, accession_number, fiscal_year, fiscal_period, period_end,
        form_type, concept, value, unit, decimals, segment, parser_version)
    VALUES (320193, '0001-test', 2023, 'FY', '2023-12-31', '10-K', 'Revenues',
            383285000000.0, 'USD', -6, 'consolidated', 'v1')""",

    """INSERT INTO sec_thirteenf_holding (cik, accession_number, holding_index, period_of_report,
        cusip, issuer_name, security_title, shares_held, market_value, security_class,
        put_call, discretion_type, voting_auth_sole, voting_auth_shared, voting_auth_none, parser_version)
    VALUES (1067983, '0002-test', 1, '2023-09-30', '037833100', 'APPLE INC', 'COM',
            915228308.0, 156751000000.0, 'equity', NULL, 'Sole', 915228308.0, 0.0, 0.0, 'v1')""",

    """INSERT INTO sec_financial_derived (cik, accession_number, fiscal_year, fiscal_period, period_end,
        form_type, revenue, ebitda, net_income, gross_margin, parser_version)
    VALUES (320193, '0001-test', 2023, 'FY', '2023-12-31', '10-K',
            383285000000.0, 130108000000.0, 96995000000.0, 0.4413, 'v1')""",

    """INSERT INTO sec_earnings_release (cik, accession_number, filing_date, fiscal_year, fiscal_quarter,
        period_end, revenue_gaap, net_income_gaap, eps_gaap_diluted, has_non_gaap, has_guidance, parser_version)
    VALUES (320193, '0003-test', '2023-11-02', 2023, 4, '2023-09-30',
            89498000000.0, 22956000000.0, 1.46, TRUE, FALSE, 'v2')""",

    """INSERT INTO sec_executive_record (cik, accession_number, fiscal_year, exec_name, exec_role,
        total_comp, base_salary, bonus, stock_awards, option_awards, non_equity_incentive, parser_version)
    VALUES (320193, '0004-test', 2023, 'Timothy D. Cook', 'CEO',
            63209845.0, 3000000.0, 0.0, 46968723.0, 0.0, 10713000.0, 'v1')""",

    """INSERT INTO sec_accounting_flag (cik, accession_number, fiscal_year, period_end, form_type,
        auditor_name, auditor_pcaob_id, auditor_location, icfr_attestation, auditor_changed, parser_version)
    VALUES (320193, '0001-test', 2023, '2023-12-31', '10-K',
            'Ernst & Young LLP', '42', 'San Jose, CA', TRUE, FALSE, 'v1')""",
]
for sql in fixtures:
    conn.execute(sql)

failures = []

def assert_(cond, msg):
    if not cond:
        failures.append(msg)
        return False
    print(f"PASS::{msg}")
    return True

cases = [
    ("sec_financial_fact",      _build_sec_financial_fact,      _SEC_FINANCIAL_FACT_SCHEMA,    {"cik", "accession_number", "concept", "fiscal_period", "segment"}),
    ("sec_thirteenf_holding",   _build_sec_thirteenf_holding,   _SEC_THIRTEENF_HOLDING_SCHEMA, {"cik", "accession_number", "holding_index"}),
    ("sec_financial_derived",   _build_sec_financial_derived,   _SEC_FINANCIAL_DERIVED_SCHEMA, {"cik", "accession_number", "fiscal_period"}),
    ("fact_earnings_release",   _build_fact_earnings_release,   _FACT_EARNINGS_RELEASE_SCHEMA, {"fact_key"}),
    ("fact_executive_record",   _build_fact_executive_record,   _FACT_EXECUTIVE_RECORD_SCHEMA, {"fact_key"}),
    ("fact_accounting_flag",    _build_fact_accounting_flag,    _FACT_ACCOUNTING_FLAG_SCHEMA,  {"fact_key"}),
]

for name, fn, expected_schema, pk_cols in cases:
    table = fn(conn)
    assert_(table.num_rows == 1, f"{name} produces 1 row from 1 fixture")
    assert_(table.schema.equals(expected_schema), f"{name} schema matches declared PyArrow schema")
    for field in table.schema:
        if field.name in pk_cols:
            assert_(not field.nullable, f"{name}.{field.name} is nullable=False (PK)")
    if "fact_" in name:
        row = table.to_pylist()[0]
        assert_(row["fact_key"] > 0, f"{name} fact_key is positive (hash & mask) = {row['fact_key']}")
        assert_(row["company_key"] == 320193, f"{name} company_key = cik (320193)")

if failures:
    print(f"\n{len(failures)} FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
PY
)"

if [[ $? -ne 0 ]]; then
    fail_check "Python smoke test exited non-zero"
fi

while IFS= read -r line; do
    if [[ "$line" == PASS::* ]]; then
        ok "${line#PASS::}"
    elif [[ "$line" =~ FAILURES ]] || [[ "$line" =~ ^[[:space:]]+-[[:space:]] ]]; then
        fail_check "${line}"
    fi
done <<< "$SMOKE_OUTPUT"

# The rich-fixture round-trip above (heredoc + $(...) capture) already
# exercises all 6 builders and asserts schema equality + PK nullability.
# An additional minimal-fixture pass is redundant — and the silver schema
# enforces NOT NULL on more columns than just the PKs (e.g. form_type on
# sec_accounting_flag), so "minimal" would have to repeat the rich case.

print_summary "2 builder-smoke-test"
