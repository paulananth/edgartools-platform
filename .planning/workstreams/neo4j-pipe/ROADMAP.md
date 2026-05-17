# Roadmap: Neo4j Bronze-To-Graph Pipe

workstream: neo4j-pipe
status: active
milestone: v1.1 Neo4j bronze-to-graph pipe
updated: 2026-05-17

---

## Milestone Goal

Fix the path from already-captured bronze/silver data through MDM relationship derivation into
Neo4j so graph sync is complete, idempotent, and independently verifiable.

---

## Phases

- [ ] **Phase 5: Source To MDM Load Path** - MDM loaders consume existing silver data produced from bronze with clear configuration, idempotency, and no loader-workstream overlap
- [x] **Phase 6: Relationship Derivation Coverage** - Ownership, adviser, fund, company, person, and security relationships are fully derived into MDM relationship rows
- [ ] **Phase 7: Neo4j Sync And Verification** - Neo4j node/edge sync is idempotent and `verify-graph` reports coverage defects clearly

---

## Phase Details

### Phase 5: Source To MDM Load Path
**Goal**: Operators can populate MDM entities from an existing local or S3-backed silver DuckDB produced from bronze, without re-fetching SEC artifacts or touching the loader-fix workstream.
**Depends on**: Nothing in this worktree
**Requirements**: PIPE-01, PIPE-02, PIPE-03, ISO-01, ISO-02
**Success Criteria** (what must be TRUE):
  1. MDM commands document and validate the silver input source (`MDM_SILVER_DUCKDB` or S3-backed equivalent) before mutation.
  2. Running entity resolution twice against the same silver fixture keeps company, adviser, person, security, and fund counts stable.
  3. Missing silver configuration exits non-zero with an actionable message and does not mutate MDM tables.
  4. The worktree remains isolated on `workspace/neo4j-pipe` and does not edit loader-fix artifacts or generated deployment JSON.
**Plans**: 4 plans
Plans:
- [x] 05-01-PLAN.md — Wave 0 tests and fixtures for parser repair, source preflight, and MDM entity idempotency. (ffc9ad8)
- [x] 05-02-PLAN.md — Repair parse-ownership-bronze against current silver schema and artifact-registry reads.
- [ ] 05-03-PLAN.md — Add shared MDM silver preflight before mutating commands.
- [ ] 05-04-PLAN.md — Prove all-domain entity-load idempotency and document AWS/local operator flow.

### Phase 6: Relationship Derivation Coverage
**Goal**: All graph-relevant relationships derivable from silver and resolved MDM entities are created as active MDM relationship rows without duplicates.
**Depends on**: Phase 5
**Requirements**: REL-01, REL-02, REL-03, REL-04
**Success Criteria** (what must be TRUE):
  1. `IS_INSIDER` rows cover non-corporate Forms 3/4/5 reporting-owner to issuer pairs.
  2. `HOLDS` and `ISSUED_BY` rows cover ownership security relationships where owner, security, and issuer resolve.
  3. `MANAGES_FUND`, `IS_ENTITY_OF`, and `IS_PERSON_OF` rows cover adviser/fund/company/person relationships.
  4. Re-running relationship derivation against unchanged data inserts zero new active duplicate rows.
**Plans**: 1 plan
Plans:
- [x] 06-01-PLAN.md — TDD: expand fixture_world, add broken-down skip counters, D-03 stderr events, and all-six-types idempotency test. (7193b57)

### Phase 7: Neo4j Sync And Verification
**Goal**: Neo4j sync upserts all required nodes and pending edges idempotently, and verification reports both graph counts and missing MDM-to-Neo4j edges.
**Depends on**: Phase 6
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04
**Success Criteria** (what must be TRUE):
  1. `sync-graph` upserts MDM nodes before relationships and can sync by relationship type with per-type limits.
  2. A second `sync-graph` run against unchanged selected scope leaves node and edge counts stable.
  3. `verify-graph` reports node counts, edge counts by type, pending MDM rows, and missing-edge diagnostics.
  4. Focused local tests pass; live Neo4j smoke test is documented and runnable when `NEO4J_*` credentials are available.
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 5. Source To MDM Load Path | v1.1 Neo4j bronze-to-graph pipe | 4/4 | Complete | 2026-05-17 |
| 6. Relationship Derivation Coverage | v1.1 Neo4j bronze-to-graph pipe | 1/1 | Complete | 2026-05-17 |
| 7. Neo4j Sync And Verification | v1.1 Neo4j bronze-to-graph pipe | 0/TBD | Not started | - |
