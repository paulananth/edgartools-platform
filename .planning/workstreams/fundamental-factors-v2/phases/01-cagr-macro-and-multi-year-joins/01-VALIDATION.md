---
phase: 1
slug: cagr-macro-and-multi-year-joins
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | dbt unit tests (`unit_tests:` YAML spec, dbt-core native feature) |
| **Config file** | `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_factors_unit_tests.yml` |
| **Quick run command** | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --select financial_factors` |
| **Full suite command** | `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --target prod` |
| **Estimated runtime** | ~30-60 seconds (scoped); full suite several minutes per repo convention |

**Known environment caveat (carried forward from Phase 2):** live `dbt test` may be
blocked by this dev account's pre-existing `SEC_FINANCIAL_DERIVED` source-schema
staleness (a different column, `current_assets`, breaks the test fixture at the whole-
`financial_derived`-model level, even though this phase's own columns —
`revenue`/`net_income`/`total_assets` — are in the original `CREATE TABLE` and
unaffected directly). If still open when this phase executes, `dbt compile`/`dbt parse`
success is the achievable verification bar; live `dbt test` is deferred/blocked, not
silently treated as equivalent to passing.

---

## Sampling Rate

- **After every task commit:** Run `dbt test --select financial_factors` (or `dbt
  compile`/`dbt parse` if the environment caveat above is still blocking)
- **After every plan wave:** Run `dbt test --target prod` (full suite, per repo convention)
- **Before `/gsd-verify-work`:** Full suite must be green (or the environment-blocked
  state explicitly documented, matching Phase 2's precedent); also verify `git diff
  --stat` shows only `infra/snowflake/dbt/edgartools_gold/**` paths touched
- **Max feedback latency:** ~60 seconds (scoped dbt test run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | GROW-01 | — | `cagr()` macro exists, uses `1.0 / years` (not integer division) | unit | `dbt compile --select financial_factors` | ❌ W0 — new macro | ⬜ pending |
| 01-01-02 | 01 | 1 | GROW-01 | — | 3yr/5yr CAGR compute correctly for revenue/net_income/total_assets given exact N-year-apart FY rows | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 01-01-03 | 01 | 1 | GROW-01 | — | CAGR nulls when insufficient history exists | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 01-01-04 | 01 | 1 | GROW-02 | — | Negative-to-negative endpoints null CAGR (D-02) | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 01-01-05 | 01 | 1 | GROW-02 | — | Single-endpoint-negative nulls CAGR (both directions) | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 01-01-06 | 01 | 1 | GROW-03 | — | Fiscal-year gap nulls CAGR, no fuzzy match (D-03) | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 01-01-07 | 01 | 1 | GROW-01/02/03 | — | Quarterly rows never receive a CAGR value (D-01) | unit | `dbt test --select financial_factors` (extends existing test) | ✅ extend existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `infra/snowflake/dbt/edgartools_gold/macros/cagr.sql` — new macro, does not exist yet
- [ ] New unit test cases in `_financial_factors_unit_tests.yml`: happy-path 3yr/5yr CAGR, negative-to-negative nulling, single-endpoint-negative nulling (both directions), fiscal-year-gap nulling, quarterly-row exclusion (extend existing test)

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification via dbt unit tests.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`cagr.sql`, 6 new/extended test cases)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
