# Roadmap: Neo4j Snowflake Native App Migration

workstream: neo4j-snowflake
status: active
milestone: v1.3 Neo4j Snowflake Native App Migration
updated: 2026-05-27

---

## Milestone Goal

Move Neo4j graph analytics from an external Neo4j runtime into the Snowflake Marketplace
Neo4j Graph Analytics Native App while preserving `edgar-warehouse` graph sync ownership,
MDM relationship parity, dashboard inspection, and end-to-end AWS verification.

---

## Phases

- [x] **Phase 1: Snowflake Native App Feasibility And Architecture Decision** - validate marketplace installation, permissions, graph projection contract, and the decision to cut over from external Neo4j (completed 2026-05-26)
- [x] **Phase 2: Snowflake Graph Sync Contract** - adapt `edgar-warehouse mdm sync-graph` to materialize MDM graph state into Snowflake graph-ready node and edge tables/views (completed 2026-05-27)
- [ ] **Phase 3: Hosted Graph Verification And E2E Cutover** - move `verify-graph` and AWS pipeline validation onto the Snowflake-hosted Native App path
- [ ] **Phase 4: Dashboard Hosted Graph Migration** - update the MDM Neo4j review dashboard to compare MDM state with the Snowflake-hosted graph target

---

## Phase Details

### Phase 1: Snowflake Native App Feasibility And Architecture Decision

**Goal**: Operators know exactly how the Neo4j Graph Analytics Native App will be installed, permissioned, and used as the replacement graph target before implementation changes begin.

**Depends on**: Nothing in this workstream

**Requirements**: DISC-01, DISC-02, DISC-03, DISC-04, SNOW-01, ISO-01, ISO-02

**Success Criteria** (what must be TRUE):

1. Marketplace install path, app role grants, warehouse/compute-pool expectations, and required Snowflake privileges are documented from current Snowflake/Neo4j sources.
2. A recorded architecture decision states that Snowflake-hosted Neo4j replaces external Neo4j for this milestone; no dual external validation path is required.
3. Credential/configuration flow is defined around Snowflake connection/app context rather than external `NEO4J_*` credentials.
4. Node/edge table or view contract is defined for MDM entities, relationship types, labels, ids, properties, and projection inputs.
5. Implementation risks and plan-review questions are captured so `$gsd-plan-review-convergence 1 --codex` can review the plan before coding.

**Plans**:

| Plan | Wave | Objective | Requirements |
|------|------|-----------|--------------|
| 01-01 | 1 | Create the Native App install, privilege, compute-pool, warehouse, and live-account validation runbook. | DISC-01, SNOW-01, ISO-01, ISO-02 |
| 01-02 | 1 | Record the architecture decision for direct migration to the Snowflake Native App target and Snowflake-managed graph access. | DISC-02, DISC-03, ISO-01, ISO-02 |
| 01-03 | 2 | Define the graph projection contract and plan-review checklist for implementation phases. | DISC-04, SNOW-01, ISO-01, ISO-02 |

### Phase 2: Snowflake Graph Sync Contract

**Goal**: `edgar-warehouse mdm sync-graph` writes idempotent Snowflake graph-ready node and edge state from existing MDM data and reusable Snowflake models.

**Depends on**: Phase 1

**Requirements**: SYNC-01, SYNC-02, SYNC-03, SNOW-02, SNOW-04

**Success Criteria** (what must be TRUE):

1. Graph sync can materialize active MDM entities into Snowflake node tables/views with stable ids, labels, source metadata, and timestamps.
2. Graph sync can materialize active MDM relationships into Snowflake edge tables/views with source/target ids, relationship type, properties, and sync status.
3. Re-running sync against unchanged MDM state leaves Snowflake graph rows stable and does not duplicate nodes or edges.
4. Bounded relationship/entity filters still work for repair and validation workflows.
5. Focused tests cover SQL generation or Snowflake writer behavior without live credentials.

**Plans**:

| Plan | Wave | Objective | Requirements |
|------|------|-----------|--------------|
| 02-01 | 1 | Define the Snowflake graph projection SQL contract for canonical MDM graph inputs and Native App-compatible table projections. | SYNC-01, SYNC-02, SNOW-02, SNOW-04 |
| 02-02 | 2 | Add the reusable Snowflake graph sync executor with fail-closed relationship/entity filter validation and credential-free writer/idempotency tests. | SYNC-01, SYNC-02, SYNC-03, SNOW-02, SNOW-04 |
| 02-03 | 3 | Wire `edgar-warehouse mdm sync-graph` to Snowflake graph materialization while keeping `load-relationships` graph writes explicit opt-in. | SYNC-01, SYNC-02, SYNC-03, SNOW-02, SNOW-04 |

### Phase 3: Hosted Graph Verification And E2E Cutover

**Goal**: Operators can prove the Snowflake-hosted graph path matches MDM relationship state and works through an end-to-end AWS run.

**Depends on**: Phase 2

**Requirements**: SYNC-04, SNOW-03, VERIFY-01, VERIFY-02, VERIFY-03, VERIFY-05

**Success Criteria** (what must be TRUE):

1. `edgar-warehouse mdm verify-graph` validates Snowflake graph node counts against active MDM entity counts.
2. Verification validates exact edge parity against active MDM relationships by relationship type.
3. Verification runs at least one Native App query-level traversal/connectivity check relevant to ownership, adviser, or fund graph coverage.
4. End-to-end AWS validation reaches graph sync and Snowflake-hosted verification without external Neo4j credentials.
5. Operator runbook documents how to distinguish app permission failures, missing graph projection data, and real MDM parity defects.

**Plans**:

| Plan | Wave | Objective | Requirements |
|------|------|-----------|--------------|
| 03-01 | 1 | Replace minimal `verify-graph` counts with a strict Snowflake SQL parity gate and structured diagnostics. | SYNC-04, VERIFY-01, VERIFY-02 |
| 03-02 | 2 | Add least-privilege Native App grants, grant validation, and default `GRAPH_INFO`/`BFS`/`WCC` smoke proof. | SYNC-04, SNOW-03, VERIFY-01, VERIFY-03 |
| 03-03 | 3 | Cut AWS MDM E2E validation over to Snowflake `sync-graph` plus strict `verify-graph` and capture live dev proof. | SYNC-04, VERIFY-05 |

### Phase 4: Dashboard Hosted Graph Migration

**Goal**: Operators can use the existing review dashboard to inspect MDM state, Snowflake graph state, Native App validation outputs, and mismatches without mutating either store.

**Depends on**: Phase 3

**Requirements**: VERIFY-04, DASH-01, DASH-02, DASH-03

**Success Criteria** (what must be TRUE):

1. Dashboard reads Snowflake-hosted graph counts and relationship diagnostics instead of external Neo4j Bolt counts.
2. Dashboard comparison views show MDM-to-Snowflake graph mismatches with relationship type, entity type, and row-limit filters.
3. Dashboard configuration and documentation remove stale external Neo4j assumptions and avoid printing secrets.
4. Dashboard tests use fixtures or mocks and do not require live Snowflake credentials.
5. The milestone final verification includes dashboard comparison plus CLI verification results.

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Snowflake Native App Feasibility And Architecture Decision | v1.3 Neo4j Snowflake Native App Migration | 3/3 | Complete    | 2026-05-26 |
| 2. Snowflake Graph Sync Contract | v1.3 Neo4j Snowflake Native App Migration | 3/3 | Complete    | 2026-05-27 |
| 3. Hosted Graph Verification And E2E Cutover | v1.3 Neo4j Snowflake Native App Migration | 1/3 | In Progress | - |
| 4. Dashboard Hosted Graph Migration | v1.3 Neo4j Snowflake Native App Migration | 0/TBD | Not started | - |
