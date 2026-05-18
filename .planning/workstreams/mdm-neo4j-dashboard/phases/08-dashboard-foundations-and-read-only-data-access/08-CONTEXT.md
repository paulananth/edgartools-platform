# Phase 8: Dashboard Foundations And Read-Only Data Access - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 8 establishes the local dashboard foundation and safe read-only access contracts for MDM SQL and Neo4j. It should create the shell, connection handling, helper boundaries, and safety tests needed before Phase 9 adds full review metrics and Phase 10 polishes the operator experience.

This phase does not implement the final dashboard views, relationship mismatch analytics, graph sync, MDM mutation, deployment rollout, or gold/dbt changes.

</domain>

<decisions>
## Implementation Decisions

### Dashboard Home
- **D-01:** Create a new operator dashboard path instead of extending the existing Snowflake gold dashboard.
- **D-02:** Use a hybrid structure: keep the local Streamlit app and run documentation in a new examples-style operator dashboard path, while placing reusable query/helper code under `edgar_warehouse` where it can be tested and reused.
- **D-03:** Use Streamlit for the Phase 8 dashboard shell. This matches existing dashboard tooling and is the fastest credible path for an operator review tool.

### MDM Read-Only Contract
- **D-04:** Add dedicated read-only MDM query helpers for the dashboard. Do not call mutating CLI handlers directly from the dashboard.
- **D-05:** Helper functions should return structured data, not printed JSON. They should use SQLAlchemy sessions only for bounded SELECT-style queries.
- **D-06:** Tests should prove dashboard code does not reach mutation surfaces such as `MDMPipeline`, resolver writes, migrations, or graph sync orchestration.

### Neo4j Read-Only Contract
- **D-07:** Reuse existing `Neo4jGraphClient` connection conventions, but add review-only query helpers/wrappers for dashboard reads.
- **D-08:** Dashboard Neo4j helpers must not call `GraphSyncEngine.sync_entities`, `GraphSyncEngine.sync_pending`, relationship merge paths, or any write-oriented graph APIs.
- **D-09:** Dynamic labels and relationship types must be constrained or validated before Cypher interpolation. Tests should prove read queries do not contain write operations such as `MERGE`, `CREATE`, `DELETE`, `SET`, or `REMOVE`.

### Startup Behavior
- **D-10:** Require MDM configuration/connectivity for the dashboard to be useful. Neo4j should be optional at startup.
- **D-11:** If MDM is unavailable, the dashboard should fail with an actionable configuration/connection message that does not print secrets.
- **D-12:** If Neo4j is unavailable, the dashboard should still launch in MDM-only mode and show Neo4j as disconnected or not configured.

### Scope And Isolation
- **D-13:** Keep implementation in the `workspace/mdm-neo4j-dashboard` worktree and `mdm-neo4j-dashboard` planning workstream.
- **D-14:** Do not edit `neo4j-pipe`, `fix-pipelines`, generated deployment JSON, gold/dbt, Step Functions, or runtime rollout files unless the user explicitly expands the phase.
- **D-15:** Keep the dashboard read-only. Do not add controls that run MDM derivation, graph sync, migrations, or repair workflows.

### the agent's Discretion
- Choose the exact module and file names, but preserve the structural split: Streamlit app path for UI, `edgar_warehouse` helper module(s) for reusable read-only queries, and focused tests for safety.
- Choose fixture/mock strategy for tests, as long as live credentials are not required for Phase 8.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Scope
- `.planning/workstreams/mdm-neo4j-dashboard/PROJECT.md` — milestone goal, scope boundaries, and source surfaces.
- `.planning/workstreams/mdm-neo4j-dashboard/REQUIREMENTS.md` — DASH and ISO requirements for Phase 8.
- `.planning/workstreams/mdm-neo4j-dashboard/ROADMAP.md` — Phase 8 goal, dependencies, and success criteria.
- `.planning/workstreams/mdm-neo4j-dashboard/STATE.md` — active branch/worktree and accumulated decisions.

### Existing Dashboard Patterns
- `examples/dashboard/README.md` — existing local Streamlit dashboard run pattern and caveats.
- `examples/dashboard/edgar_universe_dashboard.py` — existing Streamlit application structure, connection setup style, caching, and UI organization.
- `infra/snowflake/streamlit/streamlit_app.py` — existing Streamlit-in-Snowflake app pattern; read only for contrast, not as the default target.

### MDM And Neo4j Runtime Surfaces
- `edgar_warehouse/mdm/cli.py` — existing MDM CLI handlers for counts, check-connectivity, sync-graph, verify-graph, and relationship count helpers. Do not call mutating handlers from the dashboard.
- `edgar_warehouse/mdm/database.py` — MDM SQLAlchemy models and session boundaries.
- `edgar_warehouse/mdm/graph.py` — `Neo4jGraphClient`, graph registry, and sync engine. Reuse connection conventions but avoid sync/merge paths.
- `docs/neo4j.md` — Neo4j environment variables and current connection guidance.

### Project Guardrails
- `AGENTS.md` — AWS-only path, `uv` tooling, worktree isolation, and safety rules.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `examples/dashboard/edgar_universe_dashboard.py`: existing Streamlit app structure for a local dashboard, including sidebar navigation and connection-error handling patterns.
- `edgar_warehouse/mdm/cli.py::_handle_counts`: existing relational count behavior and `_relationship_counts_by_type(session)` helper are useful references, but the dashboard should expose structured helper functions rather than shelling out or printing JSON.
- `edgar_warehouse/mdm/cli.py::_handle_verify_graph`: shows current Neo4j count queries. It is useful as a reference but too CLI-shaped for direct dashboard use.
- `edgar_warehouse/mdm/graph.py::Neo4jGraphClient`: existing Neo4j connection wrapper and env-compatible graph client behavior.

### Established Patterns
- Existing dashboards use Streamlit and `uv` should be used for Python execution.
- MDM relational code is SQLAlchemy-based.
- Neo4j integration currently routes through `Neo4jGraphClient` and `GraphSyncEngine`.
- Current Neo4j verification uses dynamic relationship types and validates relationship type names before interpolation.

### Integration Points
- New UI likely belongs in a separate examples/operator path rather than the existing Snowflake gold dashboard.
- Reusable dashboard queries should live under `edgar_warehouse` near MDM code, but must not import or call mutation-heavy pipeline/sync code.
- Tests should be credential-free and verify read-only behavior through mocks/fakes and static query checks.

</code_context>

<specifics>
## Specific Ideas

- Preferred shape: local Streamlit app in a new operator dashboard path plus reusable read-only query helpers under `edgar_warehouse`.
- MDM is the required source of truth for startup.
- Neo4j is optional at startup so the dashboard can still help diagnose graph connectivity/configuration gaps from the MDM side.
- Dashboard should report disconnected Neo4j state without blocking MDM review.

</specifics>

<deferred>
## Deferred Ideas

- Full MDM/Neo4j metric views are Phase 9.
- Operator polish, filters, empty/error state design, and runbook documentation are Phase 10.
- Deploying this dashboard as a managed AWS-facing application is a future requirement, not Phase 8.
- Drill-through graph visualization is a future requirement after the review surface is validated.

</deferred>

---

*Phase: 8-Dashboard Foundations And Read-Only Data Access*
*Context gathered: 2026-05-17*
