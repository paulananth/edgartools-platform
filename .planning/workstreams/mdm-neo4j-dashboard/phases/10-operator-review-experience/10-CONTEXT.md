# Phase 10: Operator Review Experience - Context

**Gathered:** 2026-05-23T01:07:57Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 10 turns the existing local read-only Streamlit dashboard into a usable operator review experience. It owns the review flow, dashboard labels, bounded filters, empty/error states, and operator runbook documentation for MDM overview, Neo4j overview, and mismatch diagnostics.

This phase stays read-only. It does not add graph sync controls, MDM mutation controls, repair workflows, deployment rollout, new secret-management paths, gold/dbt changes, Step Functions changes, or drill-through graph visualization.

</domain>

<decisions>
## Implementation Decisions

### Review Flow
- **D-01:** Operators should land on a triage overview first, then drill into MDM, Neo4j, and mismatch detail pages.
- **D-02:** Rename/restructure primary navigation around the operator workflow as `Overview`, `MDM Overview`, `Neo4j Overview`, and `Mismatch Diagnostics`.
- **D-03:** The Overview should emphasize attention-needed items first, then high-level counts.
- **D-04:** Phase 10 must include the existing `GRAPH-01` dashboard correctness fix: entity-domain Neo4j counts must use registry Neo4j labels instead of plural label stripping, and the expected-failure regression should be converted into a passing test.

### Filters And Limits
- **D-05:** Use a hybrid filter model: global row limit in the sidebar, with page-specific entity and relationship filters inside the relevant views.
- **D-06:** Default row limit is `50`.
- **D-07:** Row-limit choices are `25`, `50`, `100`, and `250`.
- **D-08:** Page-specific entity type and relationship type filters should be single-select controls with `All` as the default.

### Empty And Error States
- **D-09:** Missing MDM configuration is a blocking error page with a setup message. The dashboard must not continue metric loading when required MDM configuration is absent.
- **D-10:** Neo4j connection or configuration failure is non-blocking. MDM pages remain usable; Neo4j and mismatch views show an unavailable state.
- **D-11:** Secret-safe error details should include environment variable names and next action only. Do not render hostnames, usernames, passwords, secret JSON payloads, raw database URLs, or driver exception text.
- **D-12:** Empty tables should use neutral copy: `No rows match the current filters.` Use separate warnings for real data gaps.

### Runbook Documentation
- **D-13:** The README/operator docs should use a guided review workflow: launch steps, required environment variables, what to inspect first, how filters work, and common failure states.
- **D-14:** Docs should reference existing remediation/check commands only, such as `mdm check-connectivity`, `mdm counts`, and `mdm verify-graph`. Do not add dashboard buttons or mutation controls.
- **D-15:** Docs need a prominent read-only guarantee section stating that the dashboard does not run sync, repair, migrate, load, or write actions.
- **D-16:** Validation docs should include the focused credential-free automated test command. A manual browser checklist is not required by the user decision for this phase.

### the agent's Discretion
- Choose the exact Streamlit implementation mechanics for filters, layout containers, and helper functions, as long as the locked navigation, filter defaults, empty/error copy, and read-only guarantees are preserved.
- Choose whether the current `Neighborhood` placeholder is removed or renamed into the new navigation model, as long as the final primary navigation matches D-02.
- Choose the exact README headings and prose, keeping the guided workflow and read-only guarantee prominent.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Scope
- `.planning/workstreams/mdm-neo4j-dashboard/PROJECT.md` - milestone goal, scope boundaries, and source surfaces.
- `.planning/workstreams/mdm-neo4j-dashboard/REQUIREMENTS.md` - Phase 10 UX requirements and the carried `GRAPH-01` gap.
- `.planning/workstreams/mdm-neo4j-dashboard/ROADMAP.md` - Phase 10 goal, dependency on Phase 9, and success criteria.
- `.planning/workstreams/mdm-neo4j-dashboard/STATE.md` - active worktree, branch, and accumulated workstream decisions.
- `AGENTS.md` - AWS-only path, `uv` tooling, worktree isolation, and safety rules.

### Prior Phase Contracts
- `.planning/workstreams/mdm-neo4j-dashboard/phases/08-dashboard-foundations-and-read-only-data-access/08-CONTEXT.md` - Phase 8 read-only dashboard foundation decisions and helper boundaries.
- `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-CONTEXT.md` - Phase 9 metric layout, warning, diagnostic, and sample-row decisions.
- `.planning/workstreams/mdm-neo4j-dashboard/phases/09-mdm-and-neo4j-review-metrics/09-VALIDATION.md` - documents the `GRAPH-01` display gap that Phase 10 must close.

### Dashboard Implementation
- `examples/mdm_graph_dashboard/streamlit_app.py` - current Streamlit dashboard, navigation, metric rendering, filters entry point, and `GRAPH-01` label-mapping bug.
- `examples/mdm_graph_dashboard/README.md` - current local launch docs, visible sections, read-only scope, and validation command.
- `edgar_warehouse/mdm/dashboard_readonly.py` - MDM read-only helper contract and structured metrics payloads.
- `edgar_warehouse/mdm/graph_readonly.py` - Neo4j read-only helper contract, bounded sample behavior, and secret-safe config handling.

### Tests And Guards
- `tests/mdm/test_dashboard_readonly.py` - credential-free MDM helper test patterns.
- `tests/mdm/test_graph_readonly.py` - credential-free Neo4j helper/fake-client test patterns.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - dashboard boundary checks and expected-failure `GRAPH-01` regression to convert to passing.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `examples/mdm_graph_dashboard/streamlit_app.py` already renders Overview, entity counts, relationship counts, graph coverage tables, warnings, bounded samples, and a global `Refresh metrics` button.
- `edgar_warehouse/mdm/dashboard_readonly.py` returns structured MDM metrics and diagnostic inputs suitable for page-specific filters.
- `edgar_warehouse/mdm/graph_readonly.py` returns structured Neo4j metrics and bounded missing/extra graph samples; its limit handling should guide the Phase 10 row-limit controls.
- `examples/mdm_graph_dashboard/README.md` already contains the launch command, read-only statement, and focused automated validation command that Phase 10 should refine.

### Established Patterns
- Streamlit is the dashboard framework for this workstream.
- Dashboard code calls read-only helper modules directly and uses `st.cache_data` for cached metric reads.
- MDM is required for useful dashboard review; Neo4j remains optional and non-blocking.
- Error copy must avoid printing secrets and low-level connection details.
- Architecture tests statically guard against mutation controls, out-of-scope deployment paths, and write-oriented helper usage.

### Integration Points
- Navigation and rendering changes belong in `examples/mdm_graph_dashboard/streamlit_app.py`.
- Operator runbook changes belong in `examples/mdm_graph_dashboard/README.md`.
- The `GRAPH-01` fix belongs in the entity-domain comparison path in `streamlit_app.py` and the expected-failure regression in `tests/architecture/test_dashboard_foundation_boundaries.py`.
- New filter behavior should preserve the current read-only helper contracts unless implementation research finds a small, testable extension is needed.

</code_context>

<specifics>
## Specific Ideas

- Use an attention-first triage overview before counts.
- Final primary navigation should be `Overview`, `MDM Overview`, `Neo4j Overview`, and `Mismatch Diagnostics`.
- Global row limit choices: `25`, `50`, `100`, `250`; default `50`.
- Page filters: single-select entity type or relationship type with `All` default.
- Empty filtered tables should say `No rows match the current filters.`
- Runbook validation should document the focused credential-free test command:
  `uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q`

</specifics>

<deferred>
## Deferred Ideas

- Manual browser review checklist is not required for Phase 10 documentation.
- Managed AWS-facing deployment remains a future requirement outside Phase 10.
- Historical trend views remain future work.
- Drill-through graph visualization remains future work after the read-only review surface is validated.

</deferred>

---

*Phase: 10-Operator Review Experience*
*Context gathered: 2026-05-23T01:07:57Z*
