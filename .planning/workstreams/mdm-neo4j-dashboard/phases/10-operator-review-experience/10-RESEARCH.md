# Phase 10: Operator Review Experience - Research

**Status:** Complete
**Generated:** 2026-05-23

## Goal

Plan Phase 10 so the existing local Streamlit dashboard becomes an operator-ready, read-only review surface with MDM overview, Neo4j overview, mismatch diagnostics, bounded filters, safe empty/error states, and runbook documentation.

## Implementation Surfaces

| File | Role | Phase 10 use |
|------|------|--------------|
| `examples/mdm_graph_dashboard/streamlit_app.py` | Streamlit UI and rendering logic | Primary implementation surface for navigation labels, attention-first overview, filters, empty states, Neo4j unavailable states, and `GRAPH-01` display correctness. |
| `examples/mdm_graph_dashboard/README.md` | Operator runbook | Update from Phase 9 metric docs to guided operator workflow, read-only guarantee, filters, failure states, and validation command. |
| `tests/architecture/test_dashboard_foundation_boundaries.py` | Static/dashboard behavior guard | Convert the expected-failure `GRAPH-01` regression into a passing test and add/adjust guards for final navigation, filters, read-only scope, and secret-safe copy. |
| `tests/mdm/test_dashboard_readonly.py` | MDM helper tests | Likely unchanged unless implementation extends helper payloads for registry/filter metadata. Prefer avoiding helper changes. |
| `tests/mdm/test_graph_readonly.py` | Neo4j helper tests | Likely unchanged unless implementation changes bounded sample limits. Prefer keeping helper contracts stable. |

Current app state:

- `SECTIONS` is `Overview`, `Entities`, `Relationships`, `Graph Coverage`, `Neighborhood`; Phase 10 must replace primary labels with `Overview`, `MDM Overview`, `Neo4j Overview`, and `Mismatch Diagnostics`.
- `render_overview` currently renders snapshot metrics before `_render_grouped_warnings`; Phase 10 requires attention-needed content first, then counts.
- `_render_entity_comparison` currently derives `graph_key = label.rstrip("s")`; this is the carried `GRAPH-01` bug.
- Existing render helpers already use `st.dataframe(..., use_container_width=True, hide_index=True)`, `st.cache_data(ttl=60)`, warning grouping, bounded sample copy, and read-only helper imports. Preserve those patterns.

## Plan Slices

Recommended plan breakdown:

| Plan | Wave | Objective | Depends on |
|------|------|-----------|------------|
| `10-01` | 1 | Close dashboard correctness and safety gaps: `GRAPH-01`, final navigation labels, overview ordering, and architecture tests. | none |
| `10-02` | 1 | Add global row-limit control and page-specific single-select filters for MDM, Neo4j, and mismatch views. | none |
| `10-03` | 2 | Polish empty/error states and operator copy across MDM-required, Neo4j-unavailable, filtered-empty, and permission/unavailable states. | `10-01`, `10-02` |
| `10-04` | 2 | Update runbook documentation for guided review workflow, read-only guarantee, filter usage, failure states, existing check commands, and validation. | `10-01`, `10-02`, `10-03` |

Why this split:

- `10-01` and `10-02` can be implemented independently if they avoid overlapping edits carefully, but both touch `streamlit_app.py`; execute-phase should run them sequentially or ensure same-wave overlap detection serializes them.
- `10-03` depends on the final navigation/filter shape because empty/error copy should appear in the final views.
- `10-04` should document the final UI behavior after implementation contracts are settled.

## GRAPH-01 Closure

Bug:

- `_render_entity_comparison` uses `label.rstrip("s")` to map display labels to Neo4j labels.
- This fails for `Companies`, `Securities`, and `People`, producing `Companie`, `Securitie`, and `People` instead of registry labels `Company`, `Security`, and `Person`.

Planning target:

- Build a mapping from MDM entity domain/entity type to registry `neo4j_label` using `mdm_metrics["registry"]["entity_type_details"]`.
- Keep display labels operator-friendly, but use exact registry labels for Neo4j node count lookup.
- Add a `Neo4j Label` column to entity-domain coverage if the implementation follows `10-UI-SPEC.md`.
- Convert `DashboardFoundationBoundaryTests.test_entity_comparison_uses_registry_labels_for_neo4j_node_counts` from `@unittest.expectedFailure` to a normal passing regression.
- Ensure unavailable Neo4j states show `-` and `Unavailable`, not misleading zero counts.

## UI/UX Contracts

Planner must preserve these locked contracts from `10-CONTEXT.md` and `10-UI-SPEC.md`:

- Use Streamlit native primitives only; do not introduce a new frontend framework or component registry.
- Primary navigation order is exactly `Overview`, `MDM Overview`, `Neo4j Overview`, `Mismatch Diagnostics`.
- Operators land on `Overview`.
- Overview renders attention-needed items before snapshot metrics.
- Global sidebar row limit uses `st.selectbox` labeled `Row limit`, options `25`, `50`, `100`, `250`, default `50`.
- Page-specific filters use single-select `st.selectbox` controls with `All` default.
- `Overview` aggregate metrics remain unfiltered.
- Empty filtered tables use `No rows match the current filters.`
- Missing MDM config/connection is blocking and should stop metric rendering.
- Neo4j unavailable is non-blocking; MDM review remains usable.
- Secret-safe error details may name env vars and next actions only. Do not render hostnames, usernames, passwords, secret JSON payloads, raw database URLs, full Neo4j URIs, or raw driver exception text.
- `Refresh metrics` remains the only action button.
- No sync, repair, migrate, load, write, or deployment controls.

## Validation Architecture

Required automated validation:

| Test file | Coverage |
|-----------|----------|
| `tests/architecture/test_dashboard_foundation_boundaries.py` | Final navigation labels, no old primary labels, no mutation/out-of-scope controls, read-only helper usage, `GRAPH-01` registry-label display behavior, filter labels/defaults if statically checkable. |
| `tests/mdm/test_dashboard_readonly.py` | Existing MDM read-only helper behavior remains green; extend only if helper payloads change. |
| `tests/mdm/test_graph_readonly.py` | Existing Neo4j read-only helper and bounded sample behavior remains green; extend only if graph helper limit behavior changes. |

Recommended focused command:

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q
```

Additional quick checks for implementation plans:

- `uv run pytest tests/architecture/test_dashboard_foundation_boundaries.py -q`
- `git diff --check`

Nyquist expectations:

- `UX-01` covered by tests/assertions for final navigation labels and separate MDM/Neo4j/mismatch render paths.
- `UX-02` covered by tests/assertions for row-limit choices/default and single-select `All` filters.
- `UX-03` covered by tests/assertions for secret-safe error copy and no raw secret/URI/driver-text rendering in dashboard docs/code.
- `GRAPH-01` covered by a passing registry-label regression.

## Risks And Pitfalls

- **Overlapping plan edits:** Most implementation work touches `streamlit_app.py`. The planner should either serialize implementation plans or make the overlap explicit so execute-phase does not parallelize conflicting edits.
- **False graph zeroes:** Do not use display labels, plural stripping, or fallback guesses for Neo4j node count keys. Use registry labels.
- **Filter semantics:** Row limit should apply to large detail/sample tables, not the high-level overview snapshot. Avoid arbitrary numeric inputs.
- **Read-only safety:** Do not import MDM resolver, stewardship, migration, graph sync, or CLI mutation handlers into the Streamlit app.
- **Secret leakage:** Error copy and docs should name env vars and next action only. Avoid raw exceptions, full URLs, hosts, usernames, passwords, and secret JSON.
- **Doc drift:** README must match the final navigation labels and filter behavior.
- **Credential-free tests:** Do not require live MDM or Neo4j credentials for Phase 10 automated checks. Use current fake Streamlit/module-loading and helper test patterns.

## Research Complete

Phase 10 is ready for planning. The highest-risk item is the `streamlit_app.py` edit surface overlap; the planner should account for that in wave assignment.
