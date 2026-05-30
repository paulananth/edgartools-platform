#!/usr/bin/env bash
# Stage 1 (PR-2) — export wiring integrity (no Snowflake creds).
#
# Verifies the warehouse export side now writes Parquet for all 6 Branch B
# tables and that the multi-namespace gold-refresh path is wired correctly.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

step "Stage 1 (PR-2) — Export wiring integrity"

# ── 1. write_gold_to_snowflake_export export_map covers all 6 ───────
log "Checking edgar_warehouse/serving/targets/snowflake.py"
SNOWFLAKE_TARGET="${REPO_ROOT}/edgar_warehouse/serving/targets/snowflake.py"
require_file "$SNOWFLAKE_TARGET"

declare_pairs=(
    "sec_financial_fact:sec_financial_fact"
    "sec_thirteenf_holding:sec_thirteenf_holding"
    "sec_financial_derived:sec_financial_derived"
    "earnings_release:fact_earnings_release"
    "executive_record:fact_executive_record"
    "accounting_flag:fact_accounting_flag"
)
for pair in "${declare_pairs[@]}"; do
    export_name="${pair%%:*}"
    builder_key="${pair##*:}"
    if grep -q "\"${export_name}\": \"${builder_key}\"" "$SNOWFLAKE_TARGET"; then
        ok "export_map: ${export_name} → ${builder_key}"
    else
        fail_check "export_map missing or wrong: ${export_name} → ${builder_key}"
    fi
done

# ── 2. _hydrate_fundamentals_shard exists ──────────────────────────
log "Checking edgar_warehouse/application/warehouse_orchestrator.py"
ORCH="${REPO_ROOT}/edgar_warehouse/application/warehouse_orchestrator.py"
require_file "$ORCH"

if grep -q "def _hydrate_fundamentals_shard" "$ORCH"; then
    ok "_hydrate_fundamentals_shard() defined"
else
    fail_check "_hydrate_fundamentals_shard() NOT defined"
fi

if grep -q "silver/fundamentals/shard-0.duckdb" "$ORCH"; then
    ok "fundamentals shard path referenced in orchestrator"
else
    fail_check "fundamentals shard path NOT referenced"
fi

# ── 3. Multi-namespace gold_silver reader wiring ───────────────────
if grep -q "fundamentals_shard_path = " "$ORCH" \
    && grep -q "ShardedSilverReader.*silver_db_path.*fundamentals_shard_path" "$ORCH"; then
    ok "gold-refresh uses ShardedSilverReader when fundamentals shard exists"
else
    fail_check "gold-refresh multi-namespace wiring NOT found"
fi

# ── 4. ShardedSilverReader per-shard membership detection ──────────
log "Checking edgar_warehouse/silver_support/sharded_reader.py"
READER="${REPO_ROOT}/edgar_warehouse/silver_support/sharded_reader.py"
require_file "$READER"

if grep -q "aliases_with_table" "$READER"; then
    ok "ShardedSilverReader has per-shard table membership detection"
else
    fail_check "ShardedSilverReader missing per-shard membership detection (PR-2 reader fix)"
fi

# ── 5. PR-2 unit tests ──────────────────────────────────────────────
log "Running PR-2 regression tests"
if [[ -d "${REPO_ROOT}/.venv" ]]; then
    if (cd "$REPO_ROOT" && source .venv/bin/activate && python3 -m pytest \
        tests/unit/test_fundamentals_modules.py::FundamentalsSnowflakeExportTests \
        tests/unit/test_fundamentals_modules.py::FundamentalsShardedReaderTests \
        --tb=line -q 2>&1 | tail -3 | grep -q "passed"); then
        ok "FundamentalsSnowflakeExportTests + FundamentalsShardedReaderTests pass"
    else
        fail_check "PR-2 regression tests FAILED"
    fi
else
    warn "skipped pytest — .venv not found"
fi

print_summary "1 export-wiring-integrity"
