# Phase 1: Snowflake Native App Feasibility And Architecture Decision - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Source:** User milestone answers plus current Neo4j and Snowflake documentation

<domain>
## Phase Boundary

This phase is documentation and architecture decision work only. It proves how the
Snowflake Marketplace Neo4j Graph Analytics Native App will replace the external Neo4j
target before any source code, Terraform, dashboard, or runtime command changes begin.

The execution output must be a set of workstream-local documents under:

`.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/`

No implementation source files are in scope for Phase 1.
</domain>

<decisions>
## Implementation Decisions

### D-01 Native App Target
- The Neo4j target for this milestone is the Snowflake Marketplace Neo4j Graph Analytics Native App.
- The expected install flow is Snowflake Marketplace / Native App, not external Neo4j Aura, a self-hosted Neo4j container, or a new non-AWS deployment path.

### D-02 Production Migration Direction
- This milestone is a production migration path, with Phase 1 acting as feasibility and architecture decision before implementation.
- Phase 1 must identify unresolved account/privilege risks clearly enough that implementation phases do not guess.

### D-03 edgar-warehouse Ownership
- `edgar-warehouse mdm sync-graph` remains the operator command surface for graph sync.
- Later implementation phases may change what that command writes or invokes, but ownership of the workflow remains in this repository.

### D-04 No External Neo4j Parallel Target
- External Neo4j is not retained as a parallel validation target for this milestone.
- Phase 1 documents a direct cutover architecture and lists rollback/deprecation questions separately; it does not plan dual-write or dual-read validation.

### D-05 Snowflake-Managed Graph Access
- Graph access and runtime credentials should come from Snowflake-managed app roles, grants, database roles, warehouses, compute pools, and Snowflake connection context.
- Phase 1 must explicitly reject carrying external `NEO4J_URI`, `NEO4J_USER`, or `NEO4J_PASSWORD` into milestone validation.

### D-06 Existing Snowflake Model Reuse
- Reuse existing source/gold Snowflake models where possible.
- Only graph-ready node/edge tables or views needed by the Native App contract should be introduced in later phases.

### D-07 Verification Standard
- The milestone proof must include matching node and edge counts, exact relationship parity, query-level graph traversal/connectivity checks, dashboard comparison, and an end-to-end AWS pipeline run.
- Phase 1 must turn those later proof obligations into a concrete contract and risk list.

### D-08 Workstream Isolation
- Work stays inside `.planning/workstreams/neo4j-snowflake` for Phase 1.
- Do not touch unfinished `mdm-neo4j-dashboard`, `neo4j-pipe`, or `fix-pipelines` artifacts.

### the agent's Discretion
- Exact document names are flexible as long as every Phase 1 requirement is covered and future implementation phases have unambiguous inputs.
- Phase 1 may recommend names for future Snowflake schemas, roles, tables, and views, but must mark them as proposed until an operator applies them in a real Snowflake account.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Scope
- `.planning/workstreams/neo4j-snowflake/PROJECT.md` - Milestone value, architecture, and AWS/Snowflake boundaries.
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md` - Phase 1 requirement IDs and out-of-scope exclusions.
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md` - Phase 1 success criteria and downstream phase dependencies.
- `.planning/workstreams/neo4j-snowflake/STATE.md` - Current decisions and blockers.

### Repository Guardrails
- `AGENTS.md` - AWS-only platform guidance and protected concurrent workstream rules.

### Current Product References
- `https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/` - Native App installation, required app privileges, required node/relationship columns, and usage example.
- `https://neo4j.com/docs/snowflake-graph-analytics/current/administration/` - Application roles, table access grants, compute pools, app warehouse, and event sharing.
- `https://docs.snowflake.com/en/developer-guide/native-apps/container-services` - Snowflake Native Apps with Snowpark Container Services privilege and service creation model.
- `https://www.snowflake.com/en/developers/guides/practical-graph-analytics-neo4j-snowflake/` - Practical projection and algorithm invocation examples.
</canonical_refs>

<specifics>
## Specific Ideas

- Proposed application name: `Neo4j_Graph_Analytics`, matching documentation defaults until an operator chooses otherwise.
- Proposed graph schema: `EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH`, with views/tables named `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` unless Phase 1 discovers a better convention.
- Native App projection inputs must expose `nodeId` on node rows and `sourceNodeId` / `targetNodeId` on relationship rows. Additional columns are graph properties.
- The first traversal/connectivity smoke check should be a low-cost algorithm or path-style check that proves SEC entity relationships are reachable through the Native App path without relying on external Bolt connectivity.
</specifics>

<deferred>
## Deferred Ideas

- Implementing `edgar-warehouse mdm sync-graph` changes is deferred to Phase 2.
- Implementing hosted verification and AWS E2E changes is deferred to Phase 3.
- Updating the dashboard is deferred to Phase 4.
- Removing legacy external Neo4j runtime code is deferred until after the Snowflake-hosted path is proven.
</deferred>

---

*Phase: 01-snowflake-native-app-feasibility-and-architecture-decision*
*Context gathered: 2026-05-25*
