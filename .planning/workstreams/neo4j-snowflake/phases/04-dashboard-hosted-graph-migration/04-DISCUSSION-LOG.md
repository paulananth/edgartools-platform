# Phase 4: Dashboard Hosted Graph Migration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-12T21:09:40Z
**Phase:** 4-Dashboard Hosted Graph Migration
**Areas discussed:** Scope boundary, Hosted graph data source, Refresh and staleness, Native App proof display, Mismatch detail depth

---

## Scope Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Dashboard + shared helpers + tests/docs | Update `examples/mdm_graph_dashboard`, read-only helper code, tests, and operator docs. | yes |
| Dashboard only | Update Streamlit pages/copy while leaving helper names/contracts mostly intact. | |
| Docs/tests only | Document the hosted graph boundary but avoid runtime dashboard code changes. | |

**User's choice:** `1A`
**Notes:** Phase 4 owns the dashboard plus shared helpers, tests, and docs because stale Neo4j assumptions exist across these layers.

| Option | Description | Selected |
|--------|-------------|----------|
| Reference only | Reuse older `mdm-neo4j-dashboard` decisions as precedent only. | |
| Promote compatible pieces | Copy relevant older decisions into Phase 4 context before planning. | |
| Ignore them | Make Phase 4 self-contained from current code and Phase 3 outcomes. | yes |

**User's choice:** `2C`
**Notes:** Older dashboard workstream artifacts are not a source of truth for Phase 4.

| Option | Description | Selected |
|--------|-------------|----------|
| Operator-facing rename only | UI/docs say hosted graph while internal helper names can remain where lower risk. | |
| Full dashboard boundary rename | Update UI, helper names, tests, and docs away from Neo4j wording where practical. | |
| Minimal rename | Only replace misleading error text; keep `Neo4j Overview` for continuity. | yes |

**User's choice:** `3C`
**Notes:** Keep naming changes minimal and preserve operator route continuity.

| Option | Description | Selected |
|--------|-------------|----------|
| Include shared verification/readiness docs | README/runbook points operators to `verify-graph`, Native App prerequisites, and AWS E2E expectations. | yes |
| Only dashboard behavior | Keep verification docs in Phase 3 artifacts. | |
| Tests as documentation | Encode expectations in tests with only light README updates. | |

**User's choice:** `4A`
**Notes:** Phase 4 should include docs that make hosted graph readiness visible to dashboard operators.

---

## Hosted Graph Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| Direct Snowflake read-only queries | Query Snowflake graph tables directly with diagnostics aligned to `verify-graph`. | yes |
| Run/parse `verify-graph` | Launch the CLI from the dashboard and parse its output. | |
| Persisted verification snapshots | Show only stored verification results. | |

**User's choice:** `1A`
**Notes:** The dashboard should not shell out to CLI commands; it should use structured read-only Snowflake diagnostics.

---

## Refresh And Staleness

| Option | Description | Selected |
|--------|-------------|----------|
| Manual refresh with timestamps | Operators refresh explicitly and see last-checked times. | yes |
| Live query on page load plus manual refresh | Query on page entry and allow manual refresh. | |
| Cached data only | Show cached data with stale warnings. | |

**User's choice:** `2A`
**Notes:** Manual refresh preserves operator control. Dashboard inspection is not the same as running the CLI acceptance gate.

---

## Native App Proof Display

| Option | Description | Selected |
|--------|-------------|----------|
| Always show compute pool and `GRAPH_INFO`/`BFS`/`WCC` status | Make Native App proof part of the main dashboard status. | |
| Summary pass/fail only | Show high-level status and point to CLI/runbook. | |
| Failure-only detail | Keep proof quiet unless there is a failure. | yes |

**User's choice:** `3C`
**Notes:** Native App proof should not dominate healthy dashboard views, but failure detail must be available in-dashboard.

---

## Mismatch Detail Depth

| Option | Description | Selected |
|--------|-------------|----------|
| Counts plus bounded row-level samples | Include missing/extra nodes, edges, endpoints, entity type, relationship type, and direction. | yes |
| Counts plus top samples only | Keep mismatch detail shallow. | |
| Full downloadable diagnostics/export | Add export-oriented diagnostics. | |

**User's choice:** `4A`
**Notes:** The dashboard is intended to be one-stop shopping for all data issues, so bounded row-level detail is required.

---

## the agent's Discretion

- Exact helper/module shape for Snowflake-hosted graph diagnostics, provided the dashboard stays read-only and the Streamlit layer does not own raw SQL.
- Exact placement of Native App failure detail in the operator pages, provided healthy views remain quiet and failures are actionable.

## Deferred Ideas

- Full downloadable diagnostics/export.
- Complete external Neo4j runtime deprecation or removal.
- Production cost and compute-pool monitoring.
