# Requirements: Neo4j Bronze-To-Graph Pipe

workstream: neo4j-pipe
status: active
milestone: v1.1 Neo4j bronze-to-graph pipe
updated: 2026-05-16

---

## Milestone Requirements

### Source To MDM

- [ ] **PIPE-01**: Operator can run the MDM entity loaders against an existing local or S3-backed silver DuckDB produced from bronze without re-fetching SEC artifacts.
- [ ] **PIPE-02**: MDM company, adviser, person, security, and fund loaders are idempotent across repeated runs against the same silver data.
- [ ] **PIPE-03**: Missing silver source configuration fails with a clear operator message that names the required setting and does not partially mutate MDM state.

### Relationship Derivation

- [ ] **REL-01**: MDM derives `IS_INSIDER` relationships for all non-corporate Forms 3/4/5 reporting owners with resolved issuer and person entities.
- [ ] **REL-02**: MDM derives `HOLDS` and `ISSUED_BY` relationships for ownership securities with resolved owners, securities, and issuers.
- [ ] **REL-03**: MDM derives `MANAGES_FUND`, `IS_ENTITY_OF`, and `IS_PERSON_OF` relationships for adviser, fund, company, and person links.
- [ ] **REL-04**: Relationship derivation is idempotent: repeated runs against unchanged silver and MDM data do not create duplicate active relationship rows.

### Neo4j Sync And Verification

- [ ] **GRAPH-01**: `edgar-warehouse mdm sync-graph` upserts all active MDM entities as Neo4j nodes before syncing pending relationships.
- [ ] **GRAPH-02**: `edgar-warehouse mdm sync-graph` supports bounded relationship sync by relationship type and per-type limit without starving other relationship types.
- [ ] **GRAPH-03**: `edgar-warehouse mdm verify-graph` reports Neo4j node counts, relationship counts by type, pending MDM relationship counts, and missing-edge diagnostics.
- [ ] **GRAPH-04**: Running graph sync twice against unchanged data produces stable Neo4j node and edge counts and leaves zero pending relationship rows for the selected scope.

### Isolation

- [ ] **ISO-01**: This milestone is developed in the `workspace/neo4j-pipe` worktree and does not modify the active loader-fix worktree, loader workstream artifacts, or generated deployment JSON.
- [ ] **ISO-02**: Changes avoid gold refresh, Step Functions failure-observability, and unrelated loader refactors unless they are required to prove the bronze-to-Neo4j path.

## Future Requirements

- [ ] Full 100-company AWS runtime proof after credentials and Neo4j environment are available.
- [ ] Dashboard or Streamlit visualization of graph coverage metrics.

## Out Of Scope

- Gold table enrichment and dbt model changes.
- Generic Step Functions failure notification/status work.
- Non-AWS deployment paths, registries, storage targets, or secret-management paths.
- Loader rewrites unrelated to feeding existing bronze/silver data into MDM.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 5 | Pending |
| PIPE-02 | Phase 5 | Pending |
| PIPE-03 | Phase 5 | Pending |
| REL-01 | Phase 6 | Pending |
| REL-02 | Phase 6 | Pending |
| REL-03 | Phase 6 | Pending |
| REL-04 | Phase 6 | Pending |
| GRAPH-01 | Phase 7 | Pending |
| GRAPH-02 | Phase 7 | Pending |
| GRAPH-03 | Phase 7 | Pending |
| GRAPH-04 | Phase 7 | Pending |
| ISO-01 | Phase 5 | Pending |
| ISO-02 | Phase 5 | Pending |
