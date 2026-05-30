# Project: EdgarTools Platform

workstream: model-builder-contract-gaps
status: planning (Phases 1-4 active; Phases 5-6 held)
milestone: Model Builder Source Contract Expansion (SEC-derivable subset)
updated: 2026-05-30

---

## Core Value

Extend the `edgartools-platform` Snowflake gold contract so downstream applications can build governed investment-model workflows from a single source-data contract, without inventing parallel app-local source views.

---

## Platform Charter (decision-record 2026-05-30, Q1-D)

`edgartools-platform` is the **canonical source for SEC-derived data**. Non-SEC data sources (market data, analyst estimates, advanced peer suggestions) require a **separate platform charter decision** before the platform takes ownership.

This decision is **deferred** until Phases 2-4 of this workstream deliver and provide empirical evidence of Model Builder's usage patterns against the SEC-only contract.

**Charter decision options** (recorded for future revisit):

| Option | Description | Cost |
|---|---|---|
| **A** Stay SEC-only | Non-SEC gaps are formally out of scope; consumers use separate providers | Lowest; clearest boundary |
| **B** Expand beyond SEC | All gaps in-scope; platform ingests market/estimate data | Highest; multi-provider lineage, licensing, cost-attribution work |
| **C** Hybrid: SEC canonical + thin views over external sources | `EDGARTOOLS_GOLD` SEC-only; sibling schema (`EDGARTOOLS_MARKET`, etc.) for external | Medium; one Snowflake account, two contract surfaces |

The Python market modules (`edgar_warehouse/market/price_provider.py`, `wacc.py`) shipped in PR #31 are **aligned with this deferral** — they are an in-process tool for consumers, not a Snowflake source contract.

---

## Active Milestone: Model Builder Source Contract Expansion (SEC-derivable subset)

**Goal:** Close the four SEC-derivable gaps (statement metadata, DQ signals, citation source refs, governance) so Model Builder can run its full SEC-only workflow against governed `EDGARTOOLS_GOLD` contracts.

**Activated phases** (per Q1-D + Q2-C decisions):

- **Phase 1: Contract Governance** — lock the boundary, document the rules. Must complete first.
- **Phase 2 + Phase 3 paired: Statement Metadata + DQ Signals** — both touch `gold_models.py` + dbt, share a single rebuild cycle.
- **Phase 4: Citation Source References** — independent code area (`sec_filing_attachment`, `_raw_object`); runs after the paired phase.

**Held phases** (await charter decision):

- Phase 5 (Market Data) — requires charter option B or C
- Phase 6 (Peer/Estimate) — same; note SIC-based peers already in `COMPANY.sic_code`

**Estimated wall clock for active subset:** ~9 weeks.

**Target features:**

- Enrich financial fact/derived contracts, or add app-facing gold objects, for statement display metadata, source lineage, accounting standard, reporting currency, mapping confidence, and review-required flags.
- Provide source data-quality signals with severity, affected fields/periods, and approval impact.
- Provide citation-ready source references for filings, facts, excerpts, and row-level lineage.

Developer-facing success metric: Model Builder can validate its required source contract entirely against `EDGARTOOLS_GOLD` objects and deterministic documented gaps, with no independent `APP_*_V` source contract invented in the consumer application.

---

## Scope Boundaries

- This workstream is isolated under `.planning/workstreams/model-builder-contract-gaps/`.
- This is a future upstream milestone candidate, not part of the active `neo4j-snowflake` workstream.
- `edgartools-platform` remains the source of truth for source-data contracts.
- Model Builder owns its application write-back artifacts; those tables do not move into `edgartools-platform`.
- Compatibility views for Model Builder are acceptable only if they are thin views over `EDGARTOOLS_GOLD` objects or newly added upstream source objects.
- Do not modify active Neo4j graph sync, verification, dashboard, or Native App work unless explicitly reprioritized.

---

## Current Source Contract Baseline

Current Model Builder-consumable objects:

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

Source gap intake: `INTAKE.md`.

---

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Keep Model Builder source contracts upstream in `edgartools-platform` | Prevents source contract drift and duplicate data definitions | Accepted |
| Keep this workstream separate from active Neo4j work | Active graph milestone is unrelated and should not be destabilized | Accepted |
| Treat missing inputs as explicit gaps until upstream closes them | Gives Model Builder deterministic limited-mode behavior | Accepted |
| **Q1-D**: defer non-SEC charter decision, activate SEC-derivable gaps first (Phases 1-4) | Avoids premature charter commitment; closes high-value gaps while collecting empirical evidence | Accepted 2026-05-30 |
| **Q2-C**: pair Phases 2+3, then run Phase 4 | Code locality — both touch `gold_models.py` + dbt; single rebuild cycle; ~9 weeks wall clock vs 18+ for strict sequential | Accepted 2026-05-30 |

## Evolution

**Activation state**: Phases 1-4 active (planning). Phases 5-6 held pending charter decision.

**Charter decision triggers** (when to revisit Q1):

1. Phase 2+3 has delivered and Model Builder has used the statement metadata + DQ signal contract for ≥ 1 month.
2. Phase 4 has delivered and citation usage data is available.
3. Concrete data on how often Model Builder users hit "no market data available" or "no estimates available" gaps.
4. A provider boundary survey has been completed (yfinance ToS, FRED public-domain status, estimate-provider licensing).

**Active-milestone evolution**:

1. Phase 1 produces a CONTRACT.md (or equivalent) that documents the governance rules.
2. Phases 2+3 (paired) and Phase 4 each produce their own `phases/N-<name>/` directory with PLAN.md.
3. After each delivery, this PROJECT.md is updated with the new `EDGARTOOLS_GOLD` objects added and any changes to the gap inventory in INTAKE.md.
