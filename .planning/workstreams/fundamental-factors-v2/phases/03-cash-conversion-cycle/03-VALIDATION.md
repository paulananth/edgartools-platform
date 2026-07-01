---
phase: 3
slug: cash-conversion-cycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework (Python)** | `pytest` (existing `[tool.pytest.ini_options]` in `pyproject.toml`) |
| **Framework (dbt)** | dbt unit tests (`unit_tests:` YAML spec, dbt-core native feature) |
| **Config file** | `pyproject.toml` (pytest); `infra/snowflake/dbt/edgartools_gold/models/gold/_financial_derived_unit_tests.yml` / `_financial_factors_unit_tests.yml` (dbt) |
| **Quick run command** | `uv run pytest tests/unit/test_fundamentals_modules.py -x` (fast, no Snowflake creds needed) |
| **Full suite command** | `uv run pytest tests/unit/ -x` ; `cd infra/snowflake/dbt/edgartools_gold && uv run --with dbt-snowflake dbt test --select financial_derived financial_factors` |
| **Estimated runtime** | Python unit: <5s. dbt scoped test: ~30-60s. |

**Known environment caveat (carried forward from Phase 1/2, confirmed live 2026-07-01):**
live `dbt test` may be blocked by this dev account's pre-existing `SEC_FINANCIAL_DERIVED`
source-schema staleness (`current_assets` and other columns missing from the deployed
table). This phase adds TWO more physical columns (`cost_of_revenue`, `accounts_payable`)
to that same table via Terraform (03-RESEARCH.md Pitfall 1) and inherits the identical
risk. `dbt compile`/`dbt parse` success is the achievable verification bar if the
source-sync gap is still open when this phase executes; live `dbt test` is
deferred/blocked and held-open per the Phase 1/2 precedent, not silently treated as
equivalent to passing.

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/unit/test_fundamentals_modules.py -x`
  (Python parser tasks) plus `uv run --with dbt-snowflake dbt parse` (dbt/macro tasks)
- **After every plan wave:** `uv run --with dbt-snowflake dbt compile --select
  financial_derived financial_factors`
- **Before `/gsd-verify-work`:** Full suite must be green (or the environment-blocked
  state explicitly documented, matching Phase 1/2's precedent); also verify `git diff
  --stat` touches only the files enumerated in 03-RESEARCH.md's 9-touchpoint checklist
  (Pattern 1) — no bronze/loader file
- **Max feedback latency:** ~60 seconds (scoped dbt test run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | CCC-01 | — | `days_outstanding()` macro exists, null-guards zero/null flow denominator | unit | `dbt parse` | ❌ W0 — new macro | ⬜ pending |
| 03-01-02 | 01 | 1 | CCC-01 | — | `days_sales_outstanding` column added to `financial_factors.sql` using existing `accounts_receivable`/`revenue` (D-02: no new fields for DSO) | unit | `dbt compile --select financial_factors` | ❌ W0 — new column | ⬜ pending |
| 03-01-03 | 01 | 1 | CCC-01 | — | DSO nulls when `accounts_receivable` or `revenue` is null/zero | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 03-01-04 | 01 | 1 | CCC-01 | — | DSO happy-path value matches hand-computed/live-verified expected ratio | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 03-02-01 | 02 | 2 | CCC-01, D-04 | Pitfall 1 (Terraform drift) | `cost_of_revenue`/`accounts_payable` extracted from XBRL facts via `_pick()` fallback lists | unit | `uv run pytest tests/unit/test_fundamentals_modules.py -x` | ❌ W0 — new fields | ⬜ pending |
| 03-02-02 | 02 | 2 | CCC-01, D-04 | Pitfall 1 | Both new columns physically present in Snowflake `EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` (Terraform-managed) | integration | `SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED` after `terraform apply` | ❌ W0 — new Terraform columns | ⬜ pending |
| 03-02-03 | 02 | 2 | CCC-01 | — | `days_inventory_outstanding`/`days_payable_outstanding` columns added using `days_outstanding()` | unit | `dbt compile --select financial_factors` | ❌ W0 — new columns | ⬜ pending |
| 03-02-04 | 02 | 2 | CCC-01, D-01 | — | DIO/DPO null when `cost_of_revenue`/`accounts_payable`/`inventory` is null (majority case per D-01's accepted structural-null population) | unit | `dbt test --select financial_factors` | ❌ W0 — new test, requires explicit `cost_of_revenue: null` fixture row (RESEARCH.md: omission-equals-null won't distinguish "field doesn't exist yet" from "intentional null test") | ⬜ pending |
| 03-02-05 | 02 | 2 | CCC-01 | — | DIO/DPO happy-path values match hand-computed/live-verified expected ratios | unit | `dbt test --select financial_factors` | ❌ W0 — new test | ⬜ pending |
| 03-02-06 | 02 | 2 | CCC-02 | — | Coverage evidence (D-01's accepted 51.5-63.3% economically-applicable-filer rate) documented in `gold.yml` column descriptions and/or REQUIREMENTS.md | manual | N/A — 03-RESEARCH.md + 03-CONTEXT.md D-01 ARE the CCC-02 evidence; verify it's cross-referenced in shipped docs | ✅ evidence exists, needs cross-ref | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `infra/snowflake/dbt/edgartools_gold/macros/days_outstanding.sql` — new macro, does not exist yet
- [ ] New unit test cases in `_financial_factors_unit_tests.yml`: DSO happy-path + null-guard (Wave 1); DIO/DPO happy-path + null-guard with explicit `cost_of_revenue: null` fixture row (Wave 2)
- [ ] `tests/unit/test_fundamentals_modules.py` — no `cost_of_revenue`/`accounts_payable` extraction test exists yet (Wave 2)
- [ ] `_financial_derived_unit_tests.yml` fixture rows — none currently populate `cost_of_revenue`/`accounts_payable` (Wave 2)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CCC-02 coverage evidence is documented and cross-referenced | CCC-02 | Not a runtime test — a plan-time/doc-time deliverable confirming the go/no-go decision (D-01) is traceable from shipped artifacts, not just this planning doc | Confirm `gold.yml`'s DIO/DPO column descriptions (or REQUIREMENTS.md) cite the measured coverage rate and D-01's "economically-applicable filers" framing, matching the precedent set by Phase 1/2's D-01/D-02/D-03 citations in `gold.yml` |
| Physical Snowflake column presence after `terraform apply` | CCC-01 | Terraform state changes are not exercised by `dbt parse`/`dbt compile` — those only validate the dbt project's own model definitions, not the live warehouse (03-RESEARCH.md Pitfall 1) | Run `terraform apply` against the target Snowflake account (dev, then eventually prod), then `snow sql -q "SHOW COLUMNS IN TABLE EDGARTOOLS_SOURCE.SEC_FINANCIAL_DERIVED"` and confirm `COST_OF_REVENUE`/`ACCOUNTS_PAYABLE` are present |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`days_outstanding.sql`, new dbt/Python test cases)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
