# Requirements: Neo4j Snowflake Native App Migration

workstream: neo4j-snowflake
status: active
milestone: v1.3 Neo4j Snowflake Native App Migration
updated: 2026-06-12

---

## Milestone Requirements

### Feasibility And Architecture

- [x] **DISC-01**: Operator can install or validate access to the Neo4j Graph Analytics Native App through the Snowflake Marketplace flow.
- [x] **DISC-02**: Operator has an architecture decision that makes Snowflake-hosted Neo4j the graph target and removes external Neo4j from milestone validation.
- [x] **DISC-03**: Operator has a documented credential/configuration model where graph access comes from Snowflake-managed app roles, grants, and connection context rather than external `NEO4J_*` secrets.
- [x] **DISC-04**: Operator has a confirmed table/view contract for nodes, edges, labels, relationship types, and graph projection inputs expected by the Native App.

### Sync Contract

- [x] **SYNC-01**: Operator can run `edgar-warehouse mdm sync-graph` so active MDM entities and relationships are materialized into Snowflake graph-ready node and edge tables/views.
- [x] **SYNC-02**: Running graph sync twice against unchanged MDM state produces stable Snowflake node/edge counts and does not duplicate graph rows.
- [x] **SYNC-03**: Graph sync still supports bounded execution by relationship type, entity type, and row limit for operator repair workflows.
- [x] **SYNC-04**: `edgar-warehouse mdm verify-graph` targets the Snowflake-hosted graph path and no longer requires an external Neo4j Bolt connection for milestone verification.

### Snowflake Native App Integration

- [x] **SNOW-01**: Snowflake roles, grants, warehouses, and application permissions required by the Neo4j Native App are documented and can be applied without broadening unrelated platform privileges.
- [x] **SNOW-02**: Neo4j graph projections can be created from existing Snowflake source/gold data plus MDM graph-ready tables/views without redesigning the gold layer.
- [x] **SNOW-03**: Query-level graph checks can run through the Native App path, including at least one traversal/connectivity-style check relevant to SEC entity relationships.
- [x] **SNOW-04**: Native App output tables, if used, land in a governed Snowflake schema with clear ownership and cleanup behavior.

### Verification

- [x] **VERIFY-01**: Verification reports matching node counts between MDM active entities, Snowflake graph node tables/views, and Native App graph projection results.
- [x] **VERIFY-02**: Verification reports exact relationship parity between active MDM relationship rows and Snowflake graph edge tables/views by relationship type.
- [x] **VERIFY-03**: Verification reports query-level graph traversal checks that prove important ownership/adviser/fund relationships are reachable.
- [ ] **VERIFY-04**: Verification includes dashboard comparison against the Snowflake-hosted graph target.
- [x] **VERIFY-05**: Verification includes an end-to-end AWS pipeline run that reaches the Snowflake-hosted graph validation path.

### Dashboard Migration

- [ ] **DASH-01**: Operator can use the existing MDM Neo4j review dashboard against the Snowflake-hosted graph target instead of an external Neo4j service.
- [ ] **DASH-02**: Dashboard comparison views show MDM-to-Snowflake-hosted graph mismatches with bounded filters and no mutation of MDM or graph state.
- [ ] **DASH-03**: Dashboard configuration and error messages remove stale external Neo4j credential assumptions and do not print Snowflake secrets.

### Isolation

- [x] **ISO-01**: Work stays isolated from unfinished `mdm-neo4j-dashboard` and older `neo4j-pipe` workstream artifacts unless explicitly merged.
- [x] **ISO-02**: Changes remain AWS/Snowflake-focused and do not introduce non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management paths.

## Future Requirements

- [ ] Deprecate or remove external Neo4j runtime support after the Snowflake-hosted path is proven.
- [ ] Add graph analytics result marts for downstream Snowflake dashboard use.
- [ ] Add production cost and compute-pool monitoring for Neo4j Graph Analytics workloads.

## Out Of Scope

- Keeping external Neo4j as a parallel validation target for this milestone.
- Redesigning the Snowflake gold layer beyond graph projection support.
- Adding non-AWS deployment or secret-management paths.
- Running graph writes from the dashboard.
- Replacing MDM PostgreSQL as the MDM source of truth.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DISC-01 | Phase 1 | Complete |
| DISC-02 | Phase 1 | Complete |
| DISC-03 | Phase 1 | Complete |
| DISC-04 | Phase 1 | Complete |
| SYNC-01 | Phase 2 | Complete |
| SYNC-02 | Phase 2 | Complete |
| SYNC-03 | Phase 2 | Complete |
| SYNC-04 | Phase 3 | Complete |
| SNOW-01 | Phase 1 | Complete |
| SNOW-02 | Phase 2 | Complete |
| SNOW-03 | Phase 3 | Complete |
| SNOW-04 | Phase 2 | Complete |
| VERIFY-01 | Phase 3 | Complete |
| VERIFY-02 | Phase 3 | Complete |
| VERIFY-03 | Phase 3 | Complete |
| VERIFY-04 | Phase 4 | Pending |
| VERIFY-05 | Phase 3 | Complete |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| ISO-01 | Phase 1 | Complete |
| ISO-02 | Phase 1 | Complete |
