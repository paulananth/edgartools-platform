#!/usr/bin/env bash
# Stage 2 (PR-2) — end-to-end gold-refresh smoke test (no Snowflake creds).
#
# Simulates gold-refresh's full pipeline locally:
#   1. Create ownership silver.duckdb + fundamentals shard-0.duckdb with
#      realistic AAPL fixtures.
#   2. Construct a ShardedSilverReader over BOTH files.
#   3. Call build_gold(reader) → produces 16-table PyArrow dict.
#   4. Call write_gold_to_snowflake_export() against a fake storage root.
#   5. Verify all 14 mapped tables produce non-empty Parquet (counts > 0
#      for AAPL fixtures, 0 for tables we didn't insert fixtures for).

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

step "Stage 2 (PR-2) — end-to-end gold-refresh smoke"

require_command python3

if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
    fatal "venv not found at ${REPO_ROOT}/.venv"
fi

cd "$REPO_ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

SMOKE_OUTPUT="$(python3 - <<'PY' 2>&1
import sys
import os
import tempfile
import duckdb
from edgar_warehouse.silver_store import _DDL
from edgar_warehouse.silver_support.sharded_reader import ShardedSilverReader
from edgar_warehouse.serving.gold_models import build_gold
from edgar_warehouse.serving.targets.snowflake import write_gold_to_snowflake_export

failures = []
def assert_(cond, msg):
    if not cond:
        failures.append(msg)
        return False
    print(f"PASS::{msg}")
    return True

with tempfile.TemporaryDirectory() as tmpdir:
    ownership_path = os.path.join(tmpdir, "silver.duckdb")
    fundamentals_path = os.path.join(tmpdir, "fund_shard.duckdb")

    # Ownership silver — actual column names from silver schema
    c1 = duckdb.connect(ownership_path)
    c1.execute(_DDL)
    c1.execute("""
        INSERT INTO sec_company (cik, entity_name, entity_type, sic, sic_description,
                                 state_of_incorporation, fiscal_year_end)
        VALUES (320193, 'Apple Inc.', 'Operating Company', '3571', 'Electronic Computers',
                'CA', '0930')
    """)
    c1.execute("""
        INSERT INTO sec_company_filing (accession_number, cik, form, filing_date, report_date)
        VALUES ('0001-test', 320193, '10-K', '2023-11-03', '2023-09-30')
    """)
    c1.close()

    # Fundamentals shard — only fundamentals tables
    c2 = duckdb.connect(fundamentals_path)
    c2.execute(_DDL)  # same DDL — tables both namespaces declare exist; we fill only some
    c2.execute("""
        INSERT INTO sec_financial_fact (cik, accession_number, fiscal_year, fiscal_period,
            period_end, form_type, concept, value, unit, decimals, segment, parser_version)
        VALUES (320193, '0001-test', 2023, 'FY', '2023-12-31', '10-K', 'Revenues',
                383285000000.0, 'USD', -6, 'consolidated', 'v1')
    """)
    c2.execute("""
        INSERT INTO sec_financial_derived (cik, accession_number, fiscal_year, fiscal_period,
            period_end, form_type, revenue, ebitda, net_income, gross_margin, parser_version)
        VALUES (320193, '0001-test', 2023, 'FY', '2023-12-31', '10-K',
                383285000000.0, 130108000000.0, 96995000000.0, 0.4413, 'v1')
    """)
    c2.execute("""
        INSERT INTO sec_earnings_release (cik, accession_number, filing_date, fiscal_year,
            fiscal_quarter, period_end, revenue_gaap, has_non_gaap, has_guidance, parser_version)
        VALUES (320193, '0003-test', '2023-11-02', 2023, 4, '2023-09-30',
                89498000000.0, TRUE, FALSE, 'v2')
    """)
    c2.close()

    # Mixed-namespace reader
    reader = ShardedSilverReader([ownership_path, fundamentals_path])
    try:
        gold = build_gold(reader)

        # Existing ownership tables (1 row each from fixtures)
        assert_("dim_company" in gold, "build_gold() produced dim_company")
        assert_(gold["dim_company"].num_rows >= 1, "dim_company has rows from fixture")

        # Fundamentals tables (1 row each from fundamentals fixtures)
        assert_("sec_financial_fact" in gold, "build_gold() produced sec_financial_fact")
        assert_(gold["sec_financial_fact"].num_rows == 1,
                f"sec_financial_fact has 1 row, got {gold['sec_financial_fact'].num_rows}")
        assert_("fact_earnings_release" in gold, "build_gold() produced fact_earnings_release")
        assert_(gold["fact_earnings_release"].num_rows == 1,
                f"fact_earnings_release has 1 row, got {gold['fact_earnings_release'].num_rows}")

        # Tables without fixtures should be empty but PRESENT
        assert_("sec_thirteenf_holding" in gold, "build_gold() produced sec_thirteenf_holding")
        assert_(gold["sec_thirteenf_holding"].num_rows == 0, "sec_thirteenf_holding empty")
    finally:
        reader.close()

    # Export against fake storage
    class _FakeStorage:
        def __init__(self): self.writes = {}
        def write_bytes(self, rel, payload):
            self.writes[rel] = len(payload)
            return rel

    fake = _FakeStorage()
    counts = write_gold_to_snowflake_export(gold, fake, "smoke-run", "2024-01-01")

    # All 14 mapped tables should appear in counts (8 existing + 6 new)
    expected_exports = {
        "company", "filing_activity", "ownership_activity", "ownership_holdings",
        "adviser_offices", "adviser_disclosures", "private_funds", "filing_detail",
        "sec_financial_fact", "sec_thirteenf_holding", "sec_financial_derived",
        "earnings_release", "executive_record", "accounting_flag",
    }
    missing = expected_exports - set(counts.keys())
    assert_(not missing, f"all 14 exports produced (missing: {missing or 'none'})")
    assert_(counts.get("sec_financial_fact", 0) == 1, "sec_financial_fact export row count = 1")
    assert_(counts.get("earnings_release", 0) == 1, "earnings_release export row count = 1")
    assert_(counts.get("sec_thirteenf_holding", -1) == 0, "sec_thirteenf_holding export row count = 0 (no fixture)")
    assert_(len(fake.writes) == 14, f"14 Parquet files written, got {len(fake.writes)}")

if failures:
    print(f"\n{len(failures)} FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
PY
)"

# Parse output
while IFS= read -r line; do
    if [[ "$line" == PASS::* ]]; then
        ok "${line#PASS::}"
    elif [[ "$line" =~ FAILURES ]] || [[ "$line" =~ ^[[:space:]]+-[[:space:]] ]]; then
        fail_check "${line}"
    fi
done <<< "$SMOKE_OUTPUT"

print_summary "2 gold-refresh-smoke"
