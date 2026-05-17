# Roadmap: MDM Neo4j Review Dashboard

workstream: mdm-neo4j-dashboard
status: active
milestone: v1.2 MDM Neo4j Review Dashboard
updated: 2026-05-17

---

## Milestone Goal

Build a read-only dashboard for reviewing MDM relational data and Neo4j graph data, with clear mismatch diagnostics and no overlap with active pipeline workstreams.

---

## Phases

- [ ] **Phase 8: Dashboard Foundations And Read-Only Data Access** - establish the dashboard shell, read-only MDM access, read-only Neo4j access, and configuration safety
- [ ] **Phase 9: MDM And Neo4j Review Metrics** - expose entity counts, relationship counts, pending sync, and missing-edge comparison queries
- [ ] **Phase 10: Operator Review Experience** - build review-first dashboard views, bounded filters, error states, and run documentation

---

## Phase Details

### Phase 8: Dashboard Foundations And Read-Only Data Access
**Goal**: Operators can launch a local read-only dashboard shell that connects to MDM and Neo4j using existing environment variables without mutating either store.
**Depends on**: Nothing in this worktree
**Requirements**: DASH-01, DASH-02, DASH-03, ISO-01, ISO-02
**Success Criteria** (what must be TRUE):
  1. Dashboard can be launched locally through `uv` with documented environment variables.
  2. MDM connection uses read-only query helpers or transaction handling that prevents mutation.
  3. Neo4j connection uses read-only sessions/transactions for review queries.
  4. Missing configuration and connection errors are actionable and do not print secret values.
  5. Changed files stay inside the dashboard worktree scope and avoid generated deployment JSON.
**Plans**:
  - 08-01: MDM read-only dashboard helpers (wave 1)
  - 08-02: Neo4j review-only dashboard helpers (wave 1)
  - 08-03: Streamlit dashboard shell, docs, and architecture guards (wave 2; depends on 08-01, 08-02)

### Phase 9: MDM And Neo4j Review Metrics
**Goal**: Operators can inspect MDM and Neo4j coverage metrics side by side, including pending sync and missing-edge diagnostics.
**Depends on**: Phase 8
**Requirements**: MDM-01, MDM-02, MDM-03, GRAPH-01, GRAPH-02, GRAPH-03
**Success Criteria** (what must be TRUE):
  1. MDM view reports entity counts by domain and relationship counts by type.
  2. Neo4j view reports node counts by label and relationship counts by type.
  3. Comparison view reports pending MDM relationship rows for the selected scope.
  4. Comparison view reports missing Neo4j edges by relationship type with bounded sample rows.
  5. Focused tests prove comparison queries are bounded and read-only.
**Plans**: TBD

### Phase 10: Operator Review Experience
**Goal**: Operators have a usable review dashboard with MDM overview, Neo4j overview, mismatch diagnostics, filters, and runbook documentation.
**Depends on**: Phase 9
**Requirements**: UX-01, UX-02, UX-03
**Success Criteria** (what must be TRUE):
  1. Dashboard presents separate MDM overview, Neo4j overview, and mismatch diagnostic views.
  2. Relationship type, entity type, and row-limit filters keep large stores inspectable.
  3. Empty, partial, disconnected, and permission-error states are clear and safe.
  4. Documentation explains local launch, environment variables, read-only guarantees, and expected operator workflow.
  5. Focused dashboard tests pass without live credentials by using fixtures/mocks.
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 8. Dashboard Foundations And Read-Only Data Access | v1.2 MDM Neo4j Review Dashboard | 1/3 | In Progress | - |
| 9. MDM And Neo4j Review Metrics | v1.2 MDM Neo4j Review Dashboard | 0/TBD | Not started | - |
| 10. Operator Review Experience | v1.2 MDM Neo4j Review Dashboard | 0/TBD | Not started | - |
