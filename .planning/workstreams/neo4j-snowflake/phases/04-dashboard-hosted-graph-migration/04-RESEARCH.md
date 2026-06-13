# Phase 4 Research: Dashboard Hosted Graph Migration

**Created:** 2026-06-13
**Scope:** Phase 4 planning research after operator selected research-first.

## Inputs Reviewed

- `.planning/workstreams/neo4j-snowflake/ROADMAP.md`
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-snowflake/STATE.md`
- `.planning/workstreams/neo4j-snowflake/reports/MILESTONE_SUMMARY-v1.3.md`
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-CONTEXT.md`
- `.planning/workstreams/neo4j-snowflake/phases/04-dashboard-hosted-graph-migration/04-UI-SPEC.md`
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md`
- `examples/mdm_graph_dashboard/streamlit_app.py`
- `examples/mdm_graph_dashboard/README.md`
- `edgar_warehouse/mdm/dashboard_readonly.py`
- `edgar_warehouse/mdm/snowflake_graph.py`
- `edgar_warehouse/mdm/cli.py`
- `edgar_warehouse/mdm/export.py`
- `tests/mdm/test_dashboard_readonly.py`
- `tests/mdm/test_cli_snowflake_graph.py`
- `tests/mdm/test_snowflake_graph_migration.py`
- `tests/architecture/test_dashboard_foundation_boundaries.py`

## Findings

### Current Dashboard Boundary

The existing Streamlit dashboard already has the right operator shell: the four required routes, manual `Refresh metrics`, row-limit selector, single-select filters, attention-first overview, timestamp captions, and bounded sample rendering. It should be migrated in place instead of redesigned.

The current graph path is not executable in the synced branch. `examples/mdm_graph_dashboard/streamlit_app.py` imports `edgar_warehouse.mdm.graph_readonly`, but no `edgar_warehouse/mdm/graph_readonly.py` file exists. The app still calls `graph_readonly.get_neo4j_graph_metrics(...)` and uses old external graph concepts such as `Neo4j permission denied` and read-only `MATCH` guidance.

The dashboard also contains stale naming in metrics and table columns (`Neo4j nodes`, `Neo4j Edges`, `Neo4j Label`) that conflicts with Phase 4's copy contract. The route label `Neo4j Overview` should remain, but the content must identify the target as Snowflake-hosted Neo4j Graph Analytics.

### MDM Helper Pattern

`edgar_warehouse/mdm/dashboard_readonly.py` is the correct local pattern for dashboard helpers:

- Return dataclasses with `as_dict()` payloads.
- Keep raw database access in helper modules, not Streamlit.
- Bound diagnostic samples.
- Return secret-safe unavailable states instead of raw connector exceptions.
- Provide timestamps with `_utc_now_iso()`.
- Use fixture and monkeypatch tests, not live credentials.

The existing `build_relationship_coverage_rows(...)` currently takes only MDM relationship counts. The Streamlit app calls it as if it also accepted graph relationship counts, so Phase 4 should replace that coupling with a hosted graph helper payload rather than stretching an MDM-only helper into a cross-store comparison surface.

### Hosted Graph Verification Payload

`edgar_warehouse/mdm/snowflake_graph.py` now has the authoritative hosted graph verification logic. `SnowflakeGraphVerifier.verify(...)` returns structured payloads containing:

- `status`
- `snowflake_graph_nodes`
- `snowflake_graph_edges`
- `target.database` and `target.schema`
- `node_parity.by_entity_type`
- `relationship_parity.by_relationship_type`
- `diagnostics.missing_graph_nodes`
- `diagnostics.extra_graph_nodes`
- `diagnostics.missing_graph_edges`
- `diagnostics.extra_graph_edges`
- `diagnostics.missing_graph_edge_endpoints`
- `native_app.status`, `native_app.required`, `native_app.phase3_acceptance`, and `native_app.checks`

This is the right conceptual source for the dashboard comparison because it matches Phase 3 acceptance semantics. The dashboard should not shell out to `edgar-warehouse mdm verify-graph` or parse CLI output. Instead, a read-only helper should call the verifier or reuse its SQL-facing object boundary directly and normalize the payload into UI-ready rows.

The Native App check set already covers app installation, app role grants, database role grants, schema privileges, compute pool availability, graph schema sample access, `GRAPH_INFO`, `BFS`, and `WCC`. Phase 4 should render those details only when a check fails or is unavailable.

### Configuration And Secret Safety

The Snowflake connector settings currently accept `MDM_SNOWFLAKE_*`, `DBT_SNOWFLAKE_*`, `MDM_SNOWFLAKE_SECRET_JSON`, `DBT_SNOWFLAKE_SECRET_JSON`, and a Snowflake CLI connection selected through `SNOWFLAKE_CONNECTION`. The Phase 4 runbook should document the exact accepted local dashboard configuration rather than carrying forward `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, or `NEO4J_SECRET_JSON`.

The AWS E2E wrapper uses a `--snow-connection` option and maps it into `SNOWFLAKE_CONNECTION` for the local preflight. Documentation can mention that command as an acceptance reference, but the dashboard must not add a control that runs it.

### Test Surface

`tests/architecture/test_dashboard_foundation_boundaries.py` currently mixes useful guardrails with stale external Neo4j expectations. It should be updated, not deleted. Useful guardrails to preserve:

- Dashboard imports read-only helpers only.
- No mutation surfaces or repair controls.
- No raw SQL or Cypher in `streamlit_app.py`.
- Stable route labels and row-limit options.
- Single-select filters with `All` defaults.
- Secret-safe copy checks.
- README validation command.

Stale expectations to replace:

- `NEO4J_*` variables as prerequisites.
- `check-connectivity --neo4j`.
- external Bolt/Aura/read-only `MATCH` guidance.
- generic bans on the word `snowflake` in dashboard docs.

## Research Conclusion

Phase 4 should be planned as three waves:

1. Add the missing hosted graph read-only helper contract over the existing `SnowflakeGraphVerifier` payload, with credential-free tests and secret-safe unavailable states.
2. Migrate the Streamlit dashboard in place to render the hosted graph payload, preserve the operator navigation, add required mismatch/native-app tables, and remove external Neo4j credential copy.
3. Update dashboard docs, architecture guardrails, and final verification evidence so Phase 4 proves dashboard comparison plus strict CLI verification without requiring live credentials in unit tests.

