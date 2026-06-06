# Requirements: Neo4j Bronze-To-Graph Pipe

status: active
milestone: v1.1 Neo4j bronze-to-graph pipe
updated: 2026-06-06

---

## Milestone Requirements

### Source To MDM

- [x] **PIPE-01**: Operator can run the MDM entity loaders against an existing local or S3-backed silver DuckDB produced from bronze without re-fetching SEC artifacts.
- [x] **PIPE-02**: MDM company, adviser, person, security, and fund loaders are idempotent across repeated runs against the same silver data.
- [x] **PIPE-03**: Missing silver source configuration fails with a clear operator message that names the required setting and does not partially mutate MDM state.
- [x] **PIPE-04**: `mdm coverage-report` reports silver vs MDM counts for companies, persons, securities, advisers, and funds, exits 0 as a reporting tool, and documents intended exclusions.
- [x] **PIPE-05**: `mdm sync-graph` materializes the Snowflake `NEO4J_GRAPH_MIGRATION` graph tables from Snowflake MDM mirror rows and passes the MDM-to-graph parity gate for the bounded real-data sample. Phase 6 owns full 11-edge coverage across the active target.

### Relationship Derivation

- [ ] **REL-01**: MDM derives `IS_INSIDER` relationships for all non-corporate Forms 3/4/5 reporting owners with resolved issuer and person entities.
- [ ] **REL-02**: MDM derives `HOLDS` and `ISSUED_BY` relationships for ownership securities with resolved owners, securities, and issuers.
- [ ] **REL-03**: MDM derives `MANAGES_FUND`, `IS_ENTITY_OF`, and `IS_PERSON_OF` relationships for adviser, fund, company, and person links.
- [ ] **REL-04**: Relationship derivation is idempotent: repeated runs against unchanged silver and MDM data do not create duplicate active relationship rows.

### Neo4j Sync And Verification

- [ ] **GRAPH-01**: `edgar-warehouse mdm sync-graph` materializes all active MDM entities as graph nodes before syncing relationships.
- [ ] **GRAPH-02**: `edgar-warehouse mdm sync-graph` supports bounded relationship sync by relationship type and per-type limit without starving other relationship types.
- [ ] **GRAPH-03**: Graph verification reports node counts, relationship counts by type, pending MDM relationship counts, parity gaps, and missing-edge endpoint diagnostics.
- [ ] **GRAPH-04**: Running graph sync twice against unchanged data produces stable graph node and edge counts and leaves zero MDM-to-graph parity gaps for the selected scope.

### Isolation

- [x] **ISO-01**: This milestone is developed in the `workspace/neo4j-pipe` worktree and does not modify the active loader-fix worktree, loader workstream artifacts, or generated deployment JSON.
- [x] **ISO-02**: Changes avoid gold refresh, Step Functions failure-observability, and unrelated loader refactors unless they are required to prove the bronze-to-Neo4j path.

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
| PIPE-01 | Phase 5 | Complete |
| PIPE-02 | Phase 5 | Complete |
| PIPE-03 | Phase 5 | Complete |
| PIPE-04 | Phase 5 | Complete |
| PIPE-05 | Phase 5 | Complete |
| REL-01 | Phase 6 | Pending |
| REL-02 | Phase 6 | Pending |
| REL-03 | Phase 6 | Pending |
| REL-04 | Phase 6 | Pending |
| GRAPH-01 | Phase 6 | Pending |
| GRAPH-02 | Phase 6 | Pending |
| GRAPH-03 | Phase 6 | Pending |
| GRAPH-04 | Phase 6 | Pending |
| ISO-01 | Phase 5 | Complete |
| ISO-02 | Phase 5 | Complete |
