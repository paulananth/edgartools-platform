# Requirements: Model Builder Source Contract Expansion

workstream: model-builder-contract-gaps
status: proposed
milestone: future Model Builder Source Contract Expansion
updated: 2026-05-30

---

## Milestone Requirements

### Contract Governance

- [ ] **GOV-01**: `edgartools-platform` remains the source of truth for Model Builder source-data contracts; Model Builder must not define independent source `APP_*_V` contracts.
- [ ] **GOV-02**: Every newly added source contract documents grain, keys, required columns, nullable columns, freshness semantics, and lineage fields.
- [ ] **GOV-03**: Each unsupported Model Builder source input is explicitly declared as a gap or out-of-scope item with downstream behavior.

### Market Data

- [ ] **MKT-01**: Consumer can query valuation market inputs by ticker/security and as-of date, including price, market cap, enterprise value, shares outstanding, and beta where available.
- [ ] **MKT-02**: Consumer can query WACC support inputs, including risk-free rate and equity-risk-premium inputs or a documented out-of-scope decision.
- [ ] **MKT-03**: Consumer can identify trading currency and FX availability when trading currency differs from company reporting currency.

### Peers And Estimates

- [ ] **PEER-01**: Consumer can query peer-company candidates with subject company, peer company, ticker/display fields, reason/match basis, as-of date, and lineage, or peer suggestions are explicitly declared out of scope.
- [ ] **EST-01**: Consumer can query analyst estimate facts by company, period, metric, value, currency, source, and as-of date, or estimates are explicitly declared out of scope.

### Citations And Source References

- [ ] **CITE-01**: Consumer can query citation-ready source references for filing-derived facts, including source reference IDs, filing/document locators, source title, section/page metadata, and lineage.
- [ ] **CITE-02**: Consumer can map financial facts and derived metrics back to source references sufficiently for report citations and source-data manifests.

### Data Quality

- [ ] **DQ-01**: Consumer can query source data-quality signals with severity, signal code, message, approval impact, affected object/field/period, detection timestamp, and data-as-of timestamp.
- [ ] **DQ-02**: Consumer can distinguish global, company-specific, and period/model-input-specific source gaps from app-owned workflow gaps.

### Statement Metadata

- [ ] **STMT-01**: Consumer can query financial statement display metadata such as statement type, display label, sort order, and source fact IDs for source-line explainability.
- [ ] **STMT-02**: Consumer can query accounting standard, reporting currency, mapping confidence, review-required flags, and restatement/amendment markers where available.
- [ ] **STMT-03**: Consumer can validate required statement concepts for Model Builder data-review gates using upstream source metadata rather than app-local inferred mappings.

## Future Requirements

- Support sector-specific financial statement contracts for banks, insurance, and REITs.
- Add provider-specific lineage for market data and analyst estimates if multiple providers are supported.
- Add contract-version compatibility views if Model Builder requires stable names across upstream refactors.

## Out Of Scope

- Moving Model Builder app-owned write-back tables into `edgartools-platform`.
- Implementing Model Builder workflows, approvals, exports, or AI narrative generation in `edgartools-platform`.
- Changing active Neo4j graph migration work.
- Adding non-AWS deployment paths or non-Snowflake contract targets as part of this milestone.

## Traceability

| Requirement | Proposed Phase | Status |
|---|---:|---|
| GOV-01 | Phase 1 | Proposed |
| GOV-02 | Phase 1 | Proposed |
| GOV-03 | Phase 1 | Proposed |
| STMT-01 | Phase 2 | Proposed |
| STMT-02 | Phase 2 | Proposed |
| STMT-03 | Phase 2 | Proposed |
| DQ-01 | Phase 3 | Proposed |
| DQ-02 | Phase 3 | Proposed |
| CITE-01 | Phase 4 | Proposed |
| CITE-02 | Phase 4 | Proposed |
| MKT-01 | Phase 5 | Proposed |
| MKT-02 | Phase 5 | Proposed |
| MKT-03 | Phase 5 | Proposed |
| PEER-01 | Phase 6 | Proposed |
| EST-01 | Phase 6 | Proposed |
