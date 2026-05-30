---
gsd_state_version: 1.0
workstream: model-builder-contract-gaps
milestone: active
milestone_name: Model Builder Source Contract Expansion (SEC-derivable subset)
status: planning
last_updated: "2026-05-30T17:30:00-04:00"
last_activity: 2026-05-30 -- Charter-deferral decision (Q1-D) and phase concurrency (Q2-C) locked
progress:
  total_phases: 6
  active_phases: 4
  held_phases: 2
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State - model-builder-contract-gaps

## Current Position

Phase: Phase 1 (Contract Governance) — planning
Plan: —
Status: Active for SEC-derivable subset (Phases 1-4). Phases 5-6 held pending charter decision.
Last activity: 2026-05-30 -- Q1-D + Q2-C decisions; activated SEC-derivable phases; market/peer/estimate phases held.

Progress: [----------] 0% (Phase 1 planning starts next)

## Milestone Context

Model Builder is a downstream web application that consumes `edgartools-platform` Snowflake source contracts. The agreed policy is that `edgartools-platform` is the source of truth for source-data contracts; Model Builder should not invent independent `APP_*_V` source contracts.

The current `EDGARTOOLS_GOLD` contract covers company, ticker, filing, financial facts, derived metrics, earnings releases, accounting flags, executive records, 13F holdings, ownership/adviser/fund facts, and freshness status. The gaps captured in `INTAKE.md` block full Model Builder workflows for market data, peers, estimates, citations, data quality, and statement metadata.

## Decisions

### Q1-D (2026-05-30): Defer charter, activate SEC-derivable gaps first

The platform's charter for non-SEC data sources (market data, analyst estimates, peer suggestions) requires a separate decision. **Defer that decision** until Phases 2-4 (SEC-derivable gaps) have delivered, then revisit with empirical evidence from Model Builder's usage of the SEC-only contract.

In the meantime:
- **Activate** Phases 1 (governance), 2 (statement metadata), 3 (DQ signals), 4 (citation source refs) — all SEC-derivable.
- **Hold** Phases 5 (market) and 6 (peer/estimate) at `proposed` status with `blocked-on-charter-decision`.
- The `market/` Python modules shipped in PR #31 stay as-is (they are an in-process tool for consumers to install, not a Snowflake source contract).

### Q2-C (2026-05-30): Paired Phase 2+3, then Phase 4

Phase 1 (governance) must complete first. After that:
- **Phase 2 + Phase 3 run paired** — both touch `gold_models.py` + dbt models + dbt schema tests, so a single rebuild/review cycle delivers both. Statement metadata (Phase 2) and DQ signals (Phase 3) share code locality.
- **Phase 4 (citations) runs after.** It touches different code (`sec_filing_attachment`, `_raw_object` indexing) and is genuinely independent.

Estimated wall clock: ~9 weeks for the activated subset.

### Prior workstream-isolation decisions (still in force)

- This workstream is separate from the active `neo4j-snowflake` workstream.
- Active Neo4j graph migration work must remain untouched unless the user explicitly reprioritizes.
- Missing source inputs in held phases (5/6) are treated by Model Builder as explicit gaps or limited-mode blockers until upstream closes them or declares them out of scope.

## Pending Todos

### Activated (Phases 1-4)
- [ ] Phase 1: draft `PHASE.md` covering governance rules and compatibility-view conventions
- [ ] Phase 1: enumerate the lint/test that prevents Model Builder from creating `APP_*_V` parallel contracts
- [ ] Phase 2: scope the v1 column set for statement metadata (display_label, sort_order, accounting_standard, mapping_confidence, review_required)
- [ ] Phase 3: scope the v1 DQ signal types (warning, overrideable_blocker, hard_blocker) and severity codes
- [ ] Phase 4: scope the v1 citation_source_reference record (filing locator, section, excerpt vs page reference)

### Held (Phases 5-6)
- [ ] Charter decision input: Model Builder usage observations from Phases 2-4 (collect after each phase delivers)
- [ ] Provider-boundary survey: yfinance/FRED licensing for in-platform redistribution if Phase 5 activates
- [ ] Decide whether peer suggestions (gap 2) belong upstream at all, or stay app-owned with platform providing only SIC

## Blockers

### Active blockers (block Phase 1+ start)
- None — Phase 1 is doc-only and can start immediately.

### Charter blockers (block Phases 5/6)
- Provider licensing decision for market data (yfinance terms of service for redistribution; FRED is public)
- Analyst estimate provider selection (Refinitiv, FactSet, Visible Alpha)
- Cost attribution if non-SEC data goes through this platform's Snowflake account

## Session Continuity

Last session: 2026-05-30
Stopped at: Q1-D + Q2-C locked; planning Phase 1 next
Resume file: `.planning/workstreams/model-builder-contract-gaps/ROADMAP.md`
