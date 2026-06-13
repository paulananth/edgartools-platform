# Phase 4: Dashboard Hosted Graph Migration - Context

**Gathered:** 2026-06-12T21:09:40Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 updates the existing local MDM graph review dashboard so operators can inspect MDM state, Snowflake-hosted graph state, and bounded mismatch diagnostics without mutating MDM or graph data. The dashboard should become the one-stop operator surface for graph data issues, while `edgar-warehouse mdm sync-graph` and `edgar-warehouse mdm verify-graph` remain the authoritative sync and verification command surfaces.

</domain>

<decisions>
## Implementation Decisions

### Scope Boundary
- **D-01:** Phase 4 owns the dashboard, shared read-only helpers, tests, and operator docs needed to migrate the existing review surface to the Snowflake-hosted graph target.
- **D-02:** Older `mdm-neo4j-dashboard` planning artifacts are not a source of truth for this phase. Treat them as historical only; Phase 4 should stand on the `neo4j-snowflake` roadmap, requirements, Phase 3 outcomes, and current code.
- **D-03:** Naming cleanup is intentionally minimal. Keep the established `Neo4j Overview` operator route for continuity, but replace misleading external Neo4j/Bolt/credential assumptions in copy, docs, helpers, and tests.
- **D-04:** Phase 4 includes shared verification/readiness documentation. The dashboard README/runbook should point operators to hosted `verify-graph`, Native App prerequisites, and AWS hosted graph E2E expectations.

### Hosted Graph Dashboard Data
- **D-05:** The dashboard should use direct Snowflake read-only queries aligned with `verify-graph` diagnostics, not shell out to `edgar-warehouse mdm verify-graph` or parse command output.
- **D-06:** Dashboard graph diagnostics should reflect the same conceptual checks as `verify-graph`: MDM active node parity, Snowflake graph node parity, relationship parity by type, missing graph nodes, extra graph nodes, missing graph edges, extra graph edges, and missing graph edge endpoints.
- **D-07:** The dashboard remains strictly read-only. It must not expose sync, repair, migrate, load, derive, write, or Native App activation controls.

### Refresh And Staleness
- **D-08:** Refresh should be manual. The dashboard can cache read-only helper payloads, but operators must have an explicit refresh control and visible last-checked timestamps for MDM and Snowflake graph data.
- **D-09:** Page-load behavior should not silently imply a fresh acceptance gate. The dashboard is an inspection surface; CLI `verify-graph` remains the acceptance gate.

### Native App Proof Display
- **D-10:** Native App proof should stay quiet on success. Do not turn `GRAPH_INFO`, `BFS`, `WCC`, and compute-pool status into always-prominent dashboard chrome.
- **D-11:** When Native App prerequisites or smoke checks fail, the dashboard should expose failure detail for compute pool, `GRAPH_INFO`, `BFS`, and `WCC` so operators can diagnose hosted graph readiness from the dashboard.
- **D-12:** Failure copy must remain secret-safe. Show environment variable names, connection names, expected grants/prerequisites, and next commands; do not print DSNs, passwords, tokens, raw connector exceptions, or stack traces.

### Mismatch Detail Depth
- **D-13:** Mismatch diagnostics should include counts plus bounded row-level samples for missing/extra nodes, missing/extra edges, missing edge endpoints, entity type, relationship type, and direction.
- **D-14:** Bounded samples are enough for dashboard review. Full export/download diagnostics are out of scope for this phase unless already available through read-only helper structures without adding a new operator workflow.
- **D-15:** Existing dashboard ergonomics should be preserved where they still fit: `Overview`, `MDM Overview`, `Neo4j Overview`, and `Mismatch Diagnostics`; row limit choices `25`, `50`, `100`, `250`; single-select entity type and relationship type filters defaulting to `All`.

### the agent's Discretion
- The planner can decide whether to implement Snowflake-hosted graph dashboard reads by adding a new read-only helper or by extending existing helper boundaries, as long as the Streamlit layer stays free of raw SQL and mutation surfaces.
- The planner can decide exact table/section placement for quiet-on-success Native App failure detail, as long as the dashboard remains one-stop shopping for data issues.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Scope And Requirements
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md` - Phase 4 goal and success criteria for dashboard hosted graph migration.
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md` - Pending `VERIFY-04`, `DASH-01`, `DASH-02`, and `DASH-03` requirements.
- `.planning/workstreams/neo4j-snowflake/STATE.md` - Current milestone state, prior decisions, and Phase 3 acceptance summary.
- `.planning/workstreams/neo4j-snowflake/reports/MILESTONE_SUMMARY-v1.3.md` - Onboarding summary for the v1.3 migration and accepted live Phase 3 proof.

### Prior Graph Migration Decisions
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` - Native App install, role, warehouse, compute-pool, and operator setup guidance.
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-GRAPH-PROJECTION-CONTRACT.md` - Node and edge projection contract for Native App graph inputs.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-CONTEXT.md` - Phase 3 decisions for strict hosted `verify-graph`, Native App proof, and AWS E2E cutover.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-02-SUMMARY.md` - Native App grant and smoke proof summary.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-03-SUMMARY.md` - AWS hosted graph E2E cutover summary and Phase 4 handoff.
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md` - Accepted live dev evidence for strict `verify-graph` and AWS hosted graph E2E.

### Dashboard And Verification Code
- `examples/mdm_graph_dashboard/streamlit_app.py` - Existing Streamlit dashboard shell, navigation, filters, refresh control, and operator copy.
- `examples/mdm_graph_dashboard/README.md` - Existing local dashboard operator runbook; currently contains stale external `NEO4J_*` assumptions.
- `edgar_warehouse/mdm/dashboard_readonly.py` - Existing read-only MDM dashboard metrics, samples, warnings, and secret-safe failure copy.
- `edgar_warehouse/mdm/snowflake_graph.py` - Snowflake graph sync and hosted verification surface, including parity SQL and Native App proof concepts.
- `edgar_warehouse/mdm/cli.py` - MDM CLI wiring for `sync-graph` and `verify-graph`; dashboard docs should point operators to these commands, not run them.
- `infra/scripts/run-aws-mdm-e2e.sh` - AWS hosted graph E2E script and preflight contract that Phase 4 docs should reference.
- `infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` - Repo-managed Native App grant setup referenced by readiness/failure guidance.

### Tests
- `tests/mdm/test_dashboard_readonly.py` - Credential-free tests for read-only MDM dashboard helper behavior and secret-safe error handling.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - Architecture guardrails for dashboard read-only behavior, route labels, copy, docs, and hosted graph E2E expectations.
- `tests/mdm/test_cli_snowflake_graph.py` - Hosted graph CLI and verification behavior tests.
- `tests/mdm/test_snowflake_graph_migration.py` - Snowflake graph SQL generation and verification coverage.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `examples/mdm_graph_dashboard/streamlit_app.py`: already has the four operator routes, manual `Refresh metrics`, row limit control, single-select filters, timestamp captions, attention-first overview, and bounded sample tables.
- `edgar_warehouse/mdm/dashboard_readonly.py`: already provides read-only MDM entity counts, relationship counts, pending sync samples, registry details, warnings, last-refreshed timestamps, and secret-safe unavailable states.
- `edgar_warehouse/mdm/snowflake_graph.py`: contains the hosted graph verification model and SQL concepts Phase 4 should mirror for dashboard diagnostics.
- `infra/scripts/run-aws-mdm-e2e.sh`: documents the hosted graph E2E acceptance flow and options that the dashboard README should reference.

### Established Patterns
- Streamlit should remain a thin rendering layer over structured helper payloads; raw SQL and graph queries belong in helper modules.
- Read-only helpers return dataclasses or plain dictionaries with `as_dict()` payloads and no stdout parsing.
- Dashboard tests use fixtures and monkeypatching rather than live Snowflake or live MDM credentials.
- Secret-safe error handling names expected env vars and next actions but suppresses raw DSNs, passwords, hostnames, and tracebacks.
- Existing dashboard tests preserve route labels and dense operator navigation; Phase 4 should avoid a full UI redesign.

### Integration Points
- Replace or bypass the current external graph helper boundary with a Snowflake-hosted read-only graph diagnostic boundary aligned with `SnowflakeGraphVerifier` output.
- Current `streamlit_app.py` imports `edgar_warehouse.mdm.graph_readonly`, but that file is absent in the synced checkout. Phase 4 planning must resolve this explicitly rather than relying on a missing legacy helper.
- Existing README and architecture tests still expect external `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON` copy. Phase 4 should replace those assumptions with Snowflake connection context such as `SNOW_CONNECTION`, `SNOWFLAKE_CONNECTION`, `DBT_SNOWFLAKE_DATABASE`, and Native App prerequisite guidance.
- Relationship and entity comparison surfaces should use full registry-derived entity/relationship types, not only bounded samples, so filters remain complete while samples stay bounded.

</code_context>

<specifics>
## Specific Ideas

The dashboard should be one-stop shopping for data issues: an operator should be able to open it, refresh read-only metrics, see whether MDM and Snowflake-hosted graph state agree, inspect bounded samples for concrete missing/extra rows, and understand Native App readiness failures without switching immediately to raw SQL or secret-bearing logs.

Native App proof should be quiet when healthy. Only show compute pool, `GRAPH_INFO`, `BFS`, and `WCC` details when they explain a graph-readiness failure.

</specifics>

<deferred>
## Deferred Ideas

- Full downloadable diagnostics/export is deferred unless it falls out naturally from existing read-only helper payloads.
- Removing or deprecating all external Neo4j runtime support remains a future requirement after this milestone; Phase 4 only removes dashboard assumptions that block or confuse the hosted graph path.
- Production cost and compute-pool monitoring remain future work.

</deferred>

---

*Phase: 4-Dashboard Hosted Graph Migration*
*Context gathered: 2026-06-12T21:09:40Z*
