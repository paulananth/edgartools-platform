# Roadmap: Neo4j Bronze-To-Graph Pipe

status: active
milestone: v1.1 Neo4j bronze-to-graph pipe
updated: 2026-06-06

---

## Milestone Goal

Fix the path from already-captured bronze/silver data through MDM relationship derivation into
Neo4j so graph sync is complete, idempotent, and independently verifiable.

---

## Phases

- [x] **Phase 5: Source To MDM Load Path** - MDM loaders consume existing silver data produced from bronze with clear configuration, idempotency, coverage reporting, and Snowflake graph parity for the bounded real-data sample. Completed 2026-06-06.
- [ ] **Phase 6: Full Graph Coverage And Verification** - all graph-relevant relationships are derived and graph sync/parity is verified across the full active coverage target
- [ ] **Phase 8: Neo4j E2E Snowflake Graph Analytics Migration** - keep AWS MDM/Postgres plus Neo4j as the operational graph path while adding Snowflake graph-ready analytics migration and validation

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
  5. `mdm coverage-report` reports silver vs MDM counts for all five domains and exits 0 as a reporting tool.
  6. Snowflake graph sync materializes `NEO4J_GRAPH_MIGRATION`, all 11 relationship-specific `GRAPH_EDGE_*` views exist, and MDM-to-graph parity holds for the bounded real-data sample.
**Plans**: 5 plans (complete)

### Phase 6: Full Graph Coverage And Verification
**Goal**: All graph-relevant relationships derivable from silver and resolved MDM entities are created as active MDM relationship rows without duplicates, synced into graph-ready Snowflake tables, and verified across the full active coverage target.
**Depends on**: Phase 5
**Requirements**: REL-01, REL-02, REL-03, REL-04, GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04
**Success Criteria** (what must be TRUE):
  1. `IS_INSIDER` rows cover non-corporate Forms 3/4/5 reporting-owner to issuer pairs.
  2. `HOLDS` and `ISSUED_BY` rows cover ownership security relationships where owner, security, and issuer resolve.
  3. `MANAGES_FUND`, `IS_ENTITY_OF`, and `IS_PERSON_OF` rows cover adviser/fund/company/person relationships.
  4. Re-running relationship derivation against unchanged data inserts zero new active duplicate rows.
  5. All 11 active relationship types have either graph rows or documented source-coverage exclusions.
  6. `sync-graph` can sync by relationship type with per-type limits, preserves node/edge count stability on repeat runs, and leaves zero MDM-to-graph parity gaps.
  7. Verification reports node counts, edge counts by type, pending MDM relationship counts, and missing-edge diagnostics.
**Plans**: TBD

### Phase 8: Neo4j E2E Snowflake Graph Analytics Migration
**Goal**: Operators can validate the full AWS graph analytics path from bronze to silver to MDM entities/relationships to Snowflake graph-ready node and edge tables for Neo4j Graph Analytics hosted in Snowflake.
**Depends on**: Phase 6
**Requirements**: GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04, REL-01, REL-02, REL-03, REL-04
**Success Criteria** (what must be TRUE):
  1. Neo4j Graph Analytics is Snowflake-hosted; the supported analytics path does not depend on external Aura/Bolt runtime credentials.
  2. `mdm export` has a real Snowflake writer and Snowflake MDM mirror tables can be transformed into graph node/edge tables plus validation SQL using a `snow` connection.
  3. Relationship derivation covers corporate Form 3/4/5 reporting owners through company-to-security holdings and derivative transaction holdings.
  4. Existing `mdm migrate`, `mdm run --entity-type all`, `mdm derive-relationships`, `mdm sync-graph`, and `mdm verify-graph` compatibility is preserved.
  5. Focused local tests cover new registry seed data, idempotent relationship derivation, and Snowflake graph migration SQL generation.
**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 5. Source To MDM Load Path | v1.1 Neo4j bronze-to-graph pipe | 5/5 | Complete | 2026-06-06 |
| 6. Full Graph Coverage And Verification | v1.1 Neo4j bronze-to-graph pipe | 1/TBD | In progress | - |
| 8. Neo4j E2E Snowflake Graph Analytics Migration | v1.1 Neo4j bronze-to-graph pipe | 0/TBD | Not started | - |
