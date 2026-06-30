---
phase: 2
slug: profitability-and-returns-factors
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-30
---

# Phase 2 — Validation Strategy

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

Note: confirm at execution time whether `dbt compile`-only validation is sufficient for
plan verification, or whether a live `dbt test` run (requiring `DBT_SNOWFLAKE_*` env
vars) is required — `dbt compile` alone does NOT execute unit tests, only validates
SQL/Jinja syntax.

---

## Sampling Rate

- **After every task commit:** Run `dbt test --select financial_factors`
- **After every plan wave:** Run `dbt test --target prod` (full suite, per repo convention)
- **Before `/gsd-verify-work`:** Full suite must be green; also verify `git diff --stat`
  shows only `infra/snowflake/dbt/edgartools_gold/**` paths touched (Phase 2 success
  criterion #5 — no silver/loader changes)
- **Max feedback latency:** ~60 seconds (scoped dbt test run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PROF-01 | — | gross_margin/operating_margin/net_margin compute correctly for representative FY row | unit | `dbt test --select financial_factors` | ✅ extend existing | ⬜ pending |
| 02-01-02 | 01 | 1 | PROF-01 | — | margins compute for non-FY (quarterly) rows too, per D-02 | unit | `dbt test --select financial_factors` | ✅ extend existing | ⬜ pending |
| 02-01-03 | 01 | 1 | PROF-02 | — | return_on_equity nulls when total_equity < 0 (D-01) | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 02-01-04 | 01 | 1 | PROF-02 | — | return_on_assets computes normally including negative net_income | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 02-01-05 | 01 | 1 | PROF-03 | — | roic passes through unchanged from financial_derived | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `infra/snowflake/dbt/edgartools_gold/macros/safe_ratio_signed.sql` — new macro, does not exist yet (ROE sign-guard variant of `safe_ratio()`)
- [ ] New unit test case(s) in `_financial_factors_unit_tests.yml` covering: (a) negative total_equity nulling ROE, (b) negative net_income flowing through margins/ROA without special-casing, (c) ROIC pass-through assertion

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification via dbt unit tests.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`safe_ratio_signed.sql`, 3 new test cases)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
