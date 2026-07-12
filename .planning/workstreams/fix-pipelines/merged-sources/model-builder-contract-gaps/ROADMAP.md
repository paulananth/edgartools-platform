# Roadmap: Model Builder Source Contract Expansion

workstream: model-builder-contract-gaps
status: planning (Phases 1-4 active; Phases 5-6 held)
milestone: Model Builder Source Contract Expansion (SEC-derivable subset)
updated: 2026-05-30

---

## Milestone Goal

Extend the `edgartools-platform` Snowflake source contract so Model Builder can consume governed company, filing, financial, citation, quality, and statement metadata inputs from `EDGARTOOLS_GOLD` without inventing consumer-local source contracts.

**Scope (per Q1-D decision, 2026-05-30):** This milestone closes the four SEC-derivable gaps. Non-SEC gaps (market data, analyst estimates, advanced peer suggestions) require a separate platform charter decision and are held at `proposed` status pending empirical evidence from Phases 2-4.

---

## Phases

### Activated phases (Q1-D, Q2-C)

- [ ] **Phase 1: Contract Governance And Compatibility Boundary** — lock the source-of-truth boundary, define compatibility-view rules, and classify each Model Builder gap as upstream in-scope, upstream out-of-scope, or charter-blocked. **Must complete before any other phase starts.**
- [ ] **Phase 2 + Phase 3 (paired): Statement Metadata + Data Quality Signals** — both touch `gold_models.py` + dbt models + dbt schema tests. Single rebuild/review cycle.
  - Phase 2: enrich or add gold objects for statement display metadata, source lineage, accounting standard, reporting currency, mapping confidence, and review flags
  - Phase 3: expose source data-quality signals with severity and approval impact for global, company, and period-level gaps
- [ ] **Phase 4: Citation Source Reference Contract** — expose citation-ready source references and fact-to-source lineage for reports and AI narrative governance. Runs after the paired Phase 2+3.

### Held phases (Q1-D charter-deferral)

- [ ] **Phase 5: Market Data Contract Decision And Implementation** — **HELD.** Activates only after a charter decision: "platform owns market data" (B from Q1) vs "external provider via hybrid hosting" (C) vs "out of scope" (A). Empirical evidence from Phases 2-4 informs the decision.
- [ ] **Phase 6: Peer And Estimate Contract Decision And Implementation** — **HELD.** Same charter-deferral. Note: SIC-based peer clusters are already available via the `COMPANY.sic_code` column (per fundamentals AD-03); only advanced peer-suggestion contracts are held.

---

## Phase Details

### Phase 1: Contract Governance And Compatibility Boundary

**Goal**: Model Builder and `edgartools-platform` have a documented source-contract boundary before any schema work starts. Phases 5 and 6 are formally marked `blocked-on-charter-decision` with the decision criteria documented.

**Depends on**: Nothing in this workstream

**Requirements**: GOV-01, GOV-02, GOV-03

**Success Criteria**:

1. The current `EDGARTOOLS_GOLD` object list is verified against dbt models, source DDL, and export schemas.
2. Each Model Builder gap from `INTAKE.md` is classified as upstream in-scope, upstream out-of-scope, or charter-blocked.
3. Compatibility-view rules state that Model Builder-facing source views must be thin views over upstream source objects.
4. A documented charter-decision template exists for the held Phases 5-6 (what evidence triggers activation; what providers are candidates; what licensing/cost decisions are required).
5. The active Neo4j workstream remains untouched.

**Plans**: TBD

### Phase 2 + Phase 3: Paired Financial Statement Metadata + Data Quality Signals

**Goal**: Model Builder can review, explain, and validate statement rows using upstream metadata, AND can consume source-quality issues with severity and approval impact, in a single coordinated milestone delivery.

**Depends on**: Phase 1

**Requirements**: STMT-01, STMT-02, STMT-03 (Phase 2) + DQ-01, DQ-02 (Phase 3)

**Why paired**: Both phases extend `gold_models.py` (new gold tables and/or column additions), both add dbt schema tests, both produce new `EDGARTOOLS_GOLD` objects consumed by Model Builder. Single rebuild/review cycle keeps schema migration coordinated. Within the pair, Model Builder picks which of the two gold tables to ship first as a tiebreaker.

**Success Criteria** (Phase 2):

1. Contract exposes statement type, display label, sort order, and source fact lineage for statement rows or a documented equivalent.
2. Contract exposes accounting standard, reporting currency, mapping confidence, review-required flags, and restatement/amendment markers where available.
3. Required Model Builder data-review gates can validate concept coverage from upstream objects.
4. Tests or dbt checks cover required keys and representative statement metadata.

**Success Criteria** (Phase 3):

1. Contract exposes source data-quality signals with signal code, severity, message, approval impact, affected object/field/period, and timestamps.
2. Contract distinguishes global, company-specific, and period/model-input-specific source gaps.
3. Data-quality signals can be joined back to source contract objects or company/period keys.
4. Tests cover representative warning, overrideable blocker, and hard blocker signals.

**Plans**: TBD

### Phase 4: Citation Source Reference Contract

**Goal**: Model Builder can produce governed source-data manifests and citation-aware narratives from upstream source references.

**Depends on**: Phase 2+3 paired delivery (review cycle from the paired phase must close before this phase's PR cycle starts).

**Requirements**: CITE-01, CITE-02

**Success Criteria**:

1. Contract exposes source reference IDs and filing/document locators sourced from existing `sec_filing_attachment` / `sec_raw_object` silver tables.
2. Contract exposes source title, section/page metadata, excerpt or locator fields, and lineage from financial facts back to citation-ready references.
3. Financial facts (`FINANCIAL_FACTS`) and derived metrics (`FINANCIAL_DERIVED`) can trace to citation-ready source references where available.
4. Missing citation coverage is emitted as an explicit source-contract gap (not silently absent).

**Plans**: TBD

### Phase 5: Market Data Contract Decision And Implementation (HELD)

**Status**: Held. Activates only after Q1-D charter decision.

**Charter decision criteria** (documented in Phase 1):
- Platform owns market data via in-Snowflake provider integration (Q1 option B/C from grilling)
- Or: market data is out-of-platform and Model Builder uses a separate provider (Q1 option A)

**Empirical evidence to collect during Phases 2-4**:
- How many Model Builder workflows actually require live market data (vs being able to defer or use stale data)?
- What providers are Model Builder users already integrated with?
- What is the cost-attribution model if the platform hosts external data?

**Original requirements**: MKT-01, MKT-02, MKT-03

### Phase 6: Peer And Estimate Contract Decision And Implementation (HELD)

**Status**: Held. Activates only after Q1-D charter decision.

**Already partially closed**: `COMPANY.sic_code` is exposed in current gold (per fundamentals AD-03). SIC-based peer clusters work today without additional contract. Only advanced peer suggestions (e.g. analyst-curated peer sets) are charter-blocked.

**Charter decision criteria**: same as Phase 5 (provider boundary, licensing, cost attribution).

**Original requirements**: PEER-01, EST-01

---

## Phase Details

### Phase 1: Contract Governance And Compatibility Boundary

**Goal**: Model Builder and `edgartools-platform` have a documented source-contract boundary before any schema work starts.

**Depends on**: Nothing in this workstream

**Requirements**: GOV-01, GOV-02, GOV-03

**Success Criteria**:

1. The current `EDGARTOOLS_GOLD` object list is verified against dbt models, source DDL, and export schemas.
2. Each Model Builder gap from `INTAKE.md` is classified as upstream in-scope, upstream out-of-scope, or external-provider dependent.
3. Compatibility-view rules state that Model Builder-facing source views must be thin views over upstream source objects.
4. The active Neo4j workstream remains untouched.

**Plans**: TBD

### Phase 2: Financial Statement Metadata Contract

**Goal**: Model Builder can review, explain, and validate statement rows using upstream metadata instead of consumer-local inferred mappings.

**Depends on**: Phase 1

**Requirements**: STMT-01, STMT-02, STMT-03

**Success Criteria**:

1. Contract exposes statement type, display label, sort order, and source fact lineage for statement rows or a documented equivalent.
2. Contract exposes accounting standard, reporting currency, mapping confidence, review-required flags, and restatement/amendment markers where available.
3. Required Model Builder data-review gates can validate concept coverage from upstream objects.
4. Tests or dbt checks cover required keys and representative statement metadata.

**Plans**: TBD

### Phase 3: Data Quality Signal Contract

**Goal**: Model Builder can consume source-quality issues with severity and approval impact from the upstream platform.

**Depends on**: Phase 1

**Requirements**: DQ-01, DQ-02

**Success Criteria**:

1. Contract exposes source data-quality signals with signal code, severity, message, approval impact, affected object/field/period, and timestamps.
2. Contract distinguishes global, company-specific, and period/model-input-specific source gaps.
3. Data-quality signals can be joined back to source contract objects or company/period keys.
4. Tests cover representative warning, overrideable blocker, and hard blocker signals.

**Plans**: TBD

### Phase 4: Citation Source Reference Contract

**Goal**: Model Builder can produce governed source-data manifests and citation-aware narratives from upstream source references.

**Depends on**: Phase 1

**Requirements**: CITE-01, CITE-02

**Success Criteria**:

1. Contract exposes source reference IDs and filing/document locators.
2. Contract exposes source title, section/page metadata, excerpt or locator fields, and lineage.
3. Financial facts and derived metrics can trace to citation-ready source references where available.
4. Missing citation coverage is emitted as an explicit source-contract gap.

**Plans**: TBD

### Phase 5: Market Data Contract Decision And Implementation

**Goal**: Model Builder has a governed answer for valuation and WACC market inputs.

**Depends on**: Phase 1

**Requirements**: MKT-01, MKT-02, MKT-03

**Success Criteria**:

1. The milestone records whether market data is owned by `edgartools-platform` or by a separate provider contract.
2. If in scope, contract exposes price, market cap, enterprise value, shares outstanding, beta, trading currency, FX, and as-of fields where available.
3. If out of scope, contract defines deterministic downstream gap behavior for valuation, WACC, stale alerts, and dashboards.
4. Tests or validation checks cover required market keys and freshness semantics if implemented.

**Plans**: TBD

### Phase 6: Peer And Estimate Contract Decision And Implementation

**Goal**: Model Builder has a governed answer for peer-company and analyst-estimate source inputs.

**Depends on**: Phase 1

**Requirements**: PEER-01, EST-01

**Success Criteria**:

1. Peer-company suggestions are either implemented with reason/as-of/lineage fields or explicitly out of scope.
2. Analyst estimates are either implemented with metric/value/period/source/as-of fields or explicitly out of scope.
3. Missing peer or estimate coverage is surfaced as a source gap, not silently inferred as complete data.
4. Tests or validation checks cover required keys and representative missing-data cases if implemented.

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|---|---|---:|---|---|
| 1. Contract Governance And Compatibility Boundary | Model Builder Source Contract Expansion (SEC-derivable subset) | 0/TBD | **Planning** (activated 2026-05-30 per Q1-D) | - |
| 2+3 paired. Statement Metadata + DQ Signals | Model Builder Source Contract Expansion (SEC-derivable subset) | 0/TBD | Activated (paired per Q2-C); blocked on Phase 1 | - |
| 4. Citation Source Reference Contract | Model Builder Source Contract Expansion (SEC-derivable subset) | 0/TBD | Activated (per Q2-C); blocked on Phase 2+3 | - |
| 5. Market Data Contract Decision And Implementation | (held) Model Builder Source Contract Expansion | 0/TBD | **HELD** — blocked-on-charter-decision (per Q1-D) | - |
| 6. Peer And Estimate Contract Decision And Implementation | (held) Model Builder Source Contract Expansion | 0/TBD | **HELD** — blocked-on-charter-decision (per Q1-D); SIC-based peers already in `COMPANY.sic_code` | - |
