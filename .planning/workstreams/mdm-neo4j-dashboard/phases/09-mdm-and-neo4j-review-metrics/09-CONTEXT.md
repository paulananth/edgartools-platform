# Phase 9: MDM And Neo4j Review Metrics - Context

**Gathered:** 2026-05-20T10:47:56Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 9 turns the Phase 8 read-only Streamlit shell into a real metrics review surface. It adds MDM entity counts, MDM relationship counts, Neo4j node and edge counts, pending sync counts, source-readiness warnings, and missing-edge comparison diagnostics.

This phase stays read-only. It does not add graph sync controls, MDM mutation controls, repair workflows, managed deployment, secret-management changes, or Phase 10 operator polish beyond what is needed to render the metrics clearly.

</domain>

<decisions>
## Implementation Decisions

### Metric Priority And Layout
- **D-01:** The first real metrics view should lead with a coverage snapshot showing MDM entity counts, MDM relationship counts, Neo4j node/edge counts, and pending sync totals.
- **D-02:** Snapshot metrics should show count plus simple status, such as `OK`, `Pending sync`, `Missing graph data`, or `Unavailable`.
- **D-03:** Attention-needed signals in Phase 9 are sync and coverage gaps: pending sync rows, missing Neo4j counts, missing edges, extra graph data, or unavailable sources. Zero counts alone should not automatically be a warning.
- **D-04:** Organize detailed metrics into MDM Overview, Neo4j Overview, and Graph Coverage. Planners may refine exact labels, but must preserve this structure and meaning.
- **D-05:** Use a hybrid page layout: Overview gets the coverage snapshot; detailed metrics go into the relevant existing sidebar destinations.
- **D-06:** Show raw counts plus percentages where meaningful, especially graph coverage percent by relationship type when both MDM and Neo4j counts exist.
- **D-07:** If Neo4j is unavailable, MDM metrics remain usable. Neo4j and comparison metrics should be marked unavailable rather than blocking the entire metrics view.
- **D-08:** Lightweight charts are allowed where Streamlit makes them cheap, but charts must not delay or complicate the metric tables.
- **D-09:** Demote Phase 8 smoke output once real metrics exist. Keep it only as low-priority diagnostics or remove it from the primary view.

### Refresh And Failure Display
- **D-10:** Prefer separate refresh per section for MDM, Neo4j, and Graph Coverage.
- **D-11:** The agent has discretion on whether to keep the existing global `Refresh data` button, add section refresh controls, or choose the cleanest Streamlit behavior after implementation research. Section-level refresh must not make the UI awkward.
- **D-12:** Show last-refreshed timestamps per section.
- **D-13:** Gather metric failures and attention signals into one warning area rather than repeating them inline in every section.
- **D-14:** The warning area should be grouped: blocking failures first, then non-blocking coverage warnings.

### Missing-Edge And Coverage Diagnostics
- **D-15:** Missing-edge diagnostics should start with entity-domain coverage: compare company, adviser, person, security, and fund counts first, then relationship edge types.
- **D-16:** Entity-domain coverage should be chart-first, with side-by-side MDM vs Neo4j bars by domain and a details table underneath.
- **D-17:** Relationship edge coverage should use a per-type table with MDM active count, Neo4j edge count, pending sync count, missing estimate, and coverage percent.
- **D-18:** Missing estimate for relationship types is `MDM active count - Neo4j edge count`, clamped at zero when Neo4j has more edges.
- **D-19:** Show all registered active relationship types, including types with zero MDM active rows.
- **D-20:** When Neo4j has more edges than MDM active rows for a type, show an extra graph data warning.

### Source-Readiness Warnings
- **D-21:** Show MDM readiness and graph sync readiness as separate warning groups.
- **D-22:** MDM readiness severity should distinguish structural problems from sparse data: missing registry data is warning/error; zero domain counts are informational unless the implementation finds a stronger reason.
- **D-23:** Graph sync readiness should warn for pending sync, Neo4j unavailable, lower Neo4j counts, and extra graph data.
- **D-24:** Warning severity should use three levels: error, warning, and info.
- **D-25:** Warnings should include short recommended operator action text, such as checking configuration or running existing MDM/graph sync commands, but must not add mutation buttons.

### Bounded Sample Detail
- **D-26:** Phase 9 should include counts plus bounded sample rows for pending sync and missing/extra graph diagnostics.
- **D-27:** Sample rows should include operator-readable names when cheaply available, falling back to IDs when names are not cheap or reliable.
- **D-28:** Use per-type small sample limits, such as 5 rows per relationship type, capped globally.
- **D-29:** Sample priority should use registry order, with oldest rows within each type.
- **D-30:** Do not expose raw properties JSON by default. Show key identifiers and names only unless implementation research finds a small, safe detail surface.

### the agent's Discretion
- Choose the exact Streamlit layout and labels, while preserving the coverage snapshot, MDM Overview, Neo4j Overview, Graph Coverage, and grouped attention-needed summary.
- Choose whether the best Streamlit implementation keeps the global refresh, adds section refresh controls, or both, as long as the user can refresh MDM, Neo4j, and Graph Coverage independently without awkward UI.
- Add lightweight Streamlit charts only when they are cheap and do not weaken the table-first audit surface.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Scope
- `.planning/workstreams/mdm-neo4j-dashboard/PROJECT.md` - milestone goal, scope boundaries, and source surfaces.
- `.planning/workstreams/mdm-neo4j-dashboard/REQUIREMENTS.md` - Phase 9 MDM and Graph requirements.
- `.planning/workstreams/mdm-neo4j-dashboard/ROADMAP.md` - Phase 9 goal, dependencies, and success criteria.
- `.planning/workstreams/mdm-neo4j-dashboard/STATE.md` - active worktree, branch, and accumulated workstream decisions.
- `AGENTS.md` - AWS-only path, `uv` tooling, worktree isolation, and safety rules.

### Prior Phase Contracts
- `.planning/workstreams/mdm-neo4j-dashboard/phases/08-dashboard-foundations-and-read-only-data-access/08-CONTEXT.md` - Phase 8 read-only dashboard decisions and helper boundaries.
- `.planning/workstreams/mdm-neo4j-dashboard/phases/08-dashboard-foundations-and-read-only-data-access/08-UI-SPEC.md` - Streamlit shell, labels, color/status rules, and deferred Phase 9 surfaces.
- `examples/mdm_graph_dashboard/streamlit_app.py` - existing Streamlit shell, sidebar destinations, cache pattern, and placeholder views.
- `examples/mdm_graph_dashboard/README.md` - local launch path and operator-facing scope.

### Read-Only Helper Surfaces
- `edgar_warehouse/mdm/dashboard_readonly.py` - existing MDM read-only status and smoke-query helper pattern.
- `edgar_warehouse/mdm/graph_readonly.py` - existing Neo4j review-only helper pattern.
- `tests/mdm/test_dashboard_readonly.py` - credential-free test pattern for MDM read-only helpers.
- `tests/mdm/test_graph_readonly.py` - fake-client test pattern for Neo4j review-only helpers.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - static safety guard pattern for dashboard boundaries.

### MDM And Neo4j Runtime References
- `edgar_warehouse/mdm/database.py` - MDM SQLAlchemy models, domain tables, relationship registry, and `graph_synced_at`.
- `edgar_warehouse/mdm/cli.py` - current `counts`, `verify-graph`, and relationship count references. Do not shell out or call mutating handlers from the dashboard.
- `edgar_warehouse/mdm/graph.py` - `Neo4jGraphClient`, `GraphRegistry`, `GraphSyncEngine.pending_counts`, and current graph count/sync conventions. Avoid sync and merge paths.
- `docs/neo4j.md` - Neo4j environment variables and current connection guidance.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `examples/mdm_graph_dashboard/streamlit_app.py` already defines `Overview`, `Entities`, `Relationships`, `Graph Coverage`, and `Neighborhood` sidebar destinations. Phase 9 should populate the appropriate existing destinations rather than inventing a new navigation model.
- `edgar_warehouse/mdm/dashboard_readonly.py` provides structured dataclass results and injected-session testing patterns for bounded SQL reads.
- `edgar_warehouse/mdm/graph_readonly.py` provides structured Neo4j status results and fake-client testing patterns.
- `edgar_warehouse/mdm/cli.py::_relationship_counts_by_type` shows the existing SQL shape for active and pending relationship counts.
- `edgar_warehouse/mdm/cli.py::_handle_verify_graph` shows the current reference behavior for Neo4j node/edge counts and pending MDM counts, but it is CLI-shaped and should be converted into reusable read-only helpers.
- `edgar_warehouse/mdm/graph.py::GraphSyncEngine.pending_counts` provides a read-only pending sync count reference.

### Established Patterns
- Streamlit is the dashboard framework for this workstream.
- Dashboard helpers return structured Python data, not printed JSON.
- Dashboard tests should be credential-free and use injected SQLAlchemy sessions or fake Neo4j clients.
- Neo4j relationship types must be validated before dynamic Cypher interpolation.
- Query results should be bounded, cached where appropriate, and refreshable by the operator.

### Integration Points
- New MDM metrics should likely extend or sit next to `dashboard_readonly.py` while preserving read-only SQL behavior.
- New Neo4j metrics should likely extend or sit next to `graph_readonly.py` while avoiding `GraphSyncEngine.sync_entities`, `sync_pending`, merge operations, and mutation APIs.
- The Streamlit app should replace Phase 8 placeholders with metric surfaces in existing destinations.
- Existing architecture guards should be extended so Phase 9 cannot introduce graph sync, MDM mutation, deployment, dbt/gold, or Terraform paths.

</code_context>

<specifics>
## Specific Ideas

- Coverage snapshot first, detailed MDM/Neo4j/Graph Coverage sections second.
- Entity-domain comparison should be chart-first, backed by a details table.
- Relationship coverage should remain audit-friendly through a per-type table.
- Missing estimate is a simple clamped delta: `max(MDM active - Neo4j edges, 0)`.
- Extra Neo4j data should be visible as a warning, not silently treated as OK.
- Warning copy should be factual and action-oriented, but must never add mutation controls.
- Diagnostic sample rows should be small, per-type, and readable by operators.

</specifics>

<deferred>
## Deferred Ideas

- Phase 10 owns broader operator polish, more complete filters, final empty/error state design, and run documentation.
- Managed AWS-facing deployment remains a future requirement outside Phase 9.
- Drill-through graph visualization remains deferred until the read-only review surface is validated.

</deferred>

---

*Phase: 9-MDM And Neo4j Review Metrics*
*Context gathered: 2026-05-20T10:47:56Z*
