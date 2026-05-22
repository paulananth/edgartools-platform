# Requirements: MDM Neo4j Review Dashboard

workstream: mdm-neo4j-dashboard
status: active
milestone: v1.2 MDM Neo4j Review Dashboard
updated: 2026-05-17

---

## Milestone Requirements

### Data Access

- [x] **DASH-01**: Operator can launch the dashboard locally with existing MDM and Neo4j environment variables, without adding new secret-management steps.
- [x] **DASH-02**: Dashboard reads MDM relational state in read-only mode and never mutates MDM tables.
- [x] **DASH-03**: Dashboard reads Neo4j graph state in read-only mode and never writes nodes, edges, labels, or properties.

### MDM Review

- [x] **MDM-01**: Operator can see MDM entity counts by domain: company, adviser, person, security, and fund.
- [x] **MDM-02**: Operator can see MDM relationship counts by relationship type and active/pending sync status.
- [x] **MDM-03**: Operator can inspect source freshness and data-readiness warnings relevant to MDM and graph review.

### Neo4j Review

- [ ] **GRAPH-01**: Operator can see Neo4j node counts by label and relationship counts by type.
- [x] **GRAPH-02**: Operator can see pending MDM relationship rows that have not reached Neo4j for the selected scope.
- [x] **GRAPH-03**: Operator can see missing-edge diagnostics comparing active MDM relationship rows to Neo4j edges.

### Dashboard Experience

- [ ] **UX-01**: Dashboard presents review-first views for MDM overview, Neo4j overview, and mismatch diagnostics.
- [ ] **UX-02**: Dashboard supports bounded filters such as relationship type, entity type, and row limit so large stores remain inspectable.
- [ ] **UX-03**: Dashboard surfaces connection/configuration errors with actionable messages and without printing secret values.

### Isolation

- [x] **ISO-01**: Work is developed only in the `workspace/mdm-neo4j-dashboard` worktree and does not modify `neo4j-pipe`, `fix-pipelines`, or generated deployment JSON.
- [x] **ISO-02**: Dashboard work avoids pipeline mutation, gold/dbt changes, Step Functions changes, and runtime rollout changes unless explicitly requested.

## Future Requirements

- [ ] Deploy the review dashboard as a managed AWS-facing operator application.
- [ ] Add historical trend views for MDM and graph coverage.
- [ ] Add drill-through graph visualization once the read-only review surface is validated.

## Out Of Scope

- Changing MDM derivation rules.
- Running graph sync from the dashboard.
- Editing Neo4j graph data from the dashboard.
- Snowflake gold or dbt model changes.
- New non-AWS storage, registry, deployment, workflow, or secret-management paths.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DASH-01 | Phase 8 | Satisfied |
| DASH-02 | Phase 8 | Satisfied |
| DASH-03 | Phase 8 | Satisfied |
| MDM-01 | Phase 9 | Satisfied |
| MDM-02 | Phase 9 | Satisfied |
| MDM-03 | Phase 9 | Satisfied |
| GRAPH-01 | Phase 9 | Unsatisfied - integration display gap |
| GRAPH-02 | Phase 9 | Satisfied |
| GRAPH-03 | Phase 9 | Satisfied |
| UX-01 | Phase 10 | Unsatisfied - phase not started |
| UX-02 | Phase 10 | Unsatisfied - phase not started |
| UX-03 | Phase 10 | Unsatisfied - phase not started |
| ISO-01 | Phase 8 | Satisfied |
| ISO-02 | Phase 8 | Satisfied |
