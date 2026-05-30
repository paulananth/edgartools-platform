---
status: promoted (Phases 1-4 active per 2026-05-30 charter-deferral decision)
source_project: model-builder
consumer: Model Builder web application
created: 2026-05-30
promoted: 2026-05-30
last_synced: 2026-05-30
owner: edgartools-platform
---

# Model Builder Source Contract Gaps

## Sync Status (2026-05-30)

This intake has been **synced** against the current platform state:

- **All 6 gold tables shipped in PR #31 fundamentals milestone** are confirmed present in the "Current Contract Consumed By Model Builder" section below (no change needed).
- **`COMPANY.sic_code`** is already exposed (per fundamentals AD-03 — SIC-based peer clustering works today against the current contract; only advanced peer-suggestion contracts are charter-blocked).
- **Python market modules** (`edgar_warehouse/market/price_provider.py`, `wacc.py`) shipped in PR #31 are NOT a Snowflake source contract; GAP-01 remains open at the contract layer.

## Activated Gap Subset (per Q1-D decision)

Activated phases close these gaps:

| Gap | Phase | Status |
|---|---|---|
| GAP-04 Citation Source References | Phase 4 | **Active** (after Phase 2+3) |
| GAP-05 Data Quality Signals | Phase 3 (paired with 2) | **Active** |
| GAP-06 Statement Metadata | Phase 2 (paired with 3) | **Active** |

## Held Gap Subset (charter-blocked)

These gaps require a separate charter decision before activation:

| Gap | Phase | Status |
|---|---|---|
| GAP-01 Market Data | Phase 5 | **HELD** — provider/licensing decision required |
| GAP-02 Peer Companies (advanced) | Phase 6 | **HELD** — partial (SIC clusters work today) |
| GAP-03 Analyst Estimates | Phase 6 | **HELD** — provider/licensing decision required |

See `PROJECT.md` Charter section for option matrix and decision criteria.

## Purpose

Model Builder depends on `edgartools-platform` as the source of truth for all Snowflake source-data contracts. The application will consume `EDGARTOOLS_GOLD` objects and must not invent independent `APP_*_V` source contracts.

This intake captures upstream source-contract gaps discovered while syncing `model-builder-spec.md` to the current `edgartools-platform` dbt gold models, Snowflake DDL, and export schemas.

Promoted future milestone artifacts:

- `PROJECT.md`
- `REQUIREMENTS.md`
- `ROADMAP.md`
- `STATE.md`

## Current Contract Consumed By Model Builder

Current usable contract objects:

- `EDGARTOOLS_GOLD.COMPANY`
- `EDGARTOOLS_GOLD.TICKER_REFERENCE`
- `EDGARTOOLS_GOLD.FILING_DETAIL`
- `EDGARTOOLS_GOLD.FILING_ACTIVITY`
- `EDGARTOOLS_GOLD.FINANCIAL_FACTS`
- `EDGARTOOLS_GOLD.FINANCIAL_DERIVED`
- `EDGARTOOLS_GOLD.EARNINGS_RELEASES`
- `EDGARTOOLS_GOLD.ACCOUNTING_FLAGS`
- `EDGARTOOLS_GOLD.EXECUTIVE_RECORDS`
- `EDGARTOOLS_GOLD.INSTITUTIONAL_HOLDINGS`
- `EDGARTOOLS_GOLD.OWNERSHIP_ACTIVITY`
- `EDGARTOOLS_GOLD.OWNERSHIP_HOLDINGS`
- `EDGARTOOLS_GOLD.ADVISER_OFFICES`
- `EDGARTOOLS_GOLD.ADVISER_DISCLOSURES`
- `EDGARTOOLS_GOLD.PRIVATE_FUNDS`
- `EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS`

Canonical source artifacts checked:

- `infra/snowflake/dbt/edgartools_gold/models/sources.yml`
- `infra/snowflake/dbt/edgartools_gold/models/gold/*.sql`
- `infra/snowflake/sql/bootstrap/01_source_stage.sql`
- `edgar_warehouse/serving/gold_models.py`

## Contract Gaps

### GAP-01 Market Data

Model Builder needs quote and market inputs for valuation, WACC, stale alerts, dashboards, and exports.

Missing source contract fields or tables:

- Trading price history and current price
- Market capitalization
- Enterprise value
- Shares outstanding
- Beta
- Risk-free rates
- Equity-risk premiums
- Trading currency and FX rates where trading currency differs from reporting currency

Until closed, Model Builder should treat DCF/WACC, current-price upside/downside, market-cap multiples, EV/EBITDA, and stale market-data alerts as gap-limited workflows.

### GAP-02 Peer Companies And Peer Multiples

Model Builder needs app-ready peer suggestions and peer-multiple inputs.

Missing source contract fields or tables:

- Company-to-peer relationships
- Peer reason or matching basis
- Peer ticker and display name
- Peer financial metric coverage for multiples
- As-of date and lineage for peer sets

Until closed, Model Builder can store user-selected peers as app artifacts, but automated peer suggestions and peer-derived multiples should remain gap-limited.

### GAP-03 Analyst Estimates

Model Builder has optional analyst estimate workflows, but no current source contract exists for estimates.

Missing source contract fields or tables:

- Estimate metric
- Estimate value
- Estimate fiscal period/year
- Estimate currency
- Source system and as-of date

Until closed, analyst estimate workflows should be disabled or explicitly marked unavailable.

### GAP-04 Citation Source References

Model Builder needs citation-aware AI narrative and report generation.

Missing source contract fields or tables:

- Source-reference IDs
- Filing/document URLs
- Source titles
- Section/page/locator metadata
- Excerpts or claim-level source locators
- Row-level lineage from financial/narrative inputs to citation-ready references

Until closed, citation-required AI narratives must either use app-owned/manual citations or remain blocked by citation-source gaps.

### GAP-05 Data Quality Signals

Model Builder needs global, company, and model-run gap analysis with severity and approval impact.

Missing source contract fields or tables:

- Source data-quality signal code
- Severity
- Human-readable message
- Approval impact
- Affected table/field/period
- Detection timestamp

Until closed, Model Builder can run its own validation over current `EDGARTOOLS_GOLD` objects, but upstream source-quality diagnostics are not available as a first-class contract.

### GAP-06 Statement Metadata And Mapping Confidence

Model Builder needs reviewable statement rows and source-data manifests.

Missing source contract fields or tables:

- Standard statement type and display label
- Statement row sort order
- Source fact IDs for rollups
- Accounting standard
- Reporting currency
- Mapping confidence
- Review-required flag
- Restatement/amendment marker

Current `FINANCIAL_FACTS` and `FINANCIAL_DERIVED` support core financial facts and derived metrics, but they do not yet expose enough metadata for full data-review gates, statement-line explainability, or approval blocking based on mapping confidence.

## Recommended Upstream Requirements

- [ ] **CONTRACT-01**: `edgartools-platform` exposes a Snowflake source contract for market data inputs needed by valuation and WACC workflows.
- [ ] **CONTRACT-02**: `edgartools-platform` exposes peer-company source data or explicitly declares peer suggestions out of scope for the platform.
- [ ] **CONTRACT-03**: `edgartools-platform` exposes analyst estimate source data or explicitly declares estimates out of scope for the platform.
- [ ] **CONTRACT-04**: `edgartools-platform` exposes citation-ready source references for filings, facts, and narrative source material.
- [ ] **CONTRACT-05**: `edgartools-platform` exposes data-quality signals with severity and approval impact.
- [ ] **CONTRACT-06**: `edgartools-platform` enriches financial facts or adds app-facing gold objects for statement metadata, source lineage, accounting standard, reporting currency, mapping confidence, and review-required flags.

## Non-Goals

- Do not move Model Builder application artifact tables into `edgartools-platform`.
- Do not create Model Builder-specific write-back tables in the source platform.
- Do not add parallel `APP_*_V` source contracts in Model Builder unless they are thin compatibility views over `EDGARTOOLS_GOLD`.
- Do not make these gaps part of the active Neo4j workstream unless the user explicitly reprioritizes the current milestone.

## Model Builder Behavior Until Gaps Close

Model Builder should:

- Consume only current `EDGARTOOLS_GOLD` source contract objects.
- Store user/model artifacts in its own app-owned Snowflake tables.
- Treat unavailable source inputs as explicit gaps or limited-mode blockers.
- Preserve traceability from each model run to the `EDGARTOOLS_GOLD` objects and columns used.
- Re-sync its spec when `edgartools-platform` adds or changes source contract objects.
