# EdgarTools MDM Graph Dashboard

## Purpose

Use this local Streamlit dashboard to review MDM and Neo4j coverage from the
read-only metric helpers. The first pass is triage: start with system-wide
attention items, then inspect MDM counts, graph counts, and mismatch samples.

## Read-only guarantee

This dashboard does not run sync, repair, migrate, load, or write actions.
`Refresh metrics` only clears cached read-only dashboard data and rereads the
current helper payloads.

## Prerequisites

- Python environment managed with `uv`.
- Required: `MDM_DATABASE_URL` for an existing MDM database.
- Optional graph connection variables: `NEO4J_URI`, `NEO4J_USER`, and
  `NEO4J_PASSWORD`.
- Optional graph settings: `NEO4J_DATABASE` and `NEO4J_SECRET_JSON`.

## Launch

```bash
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

The dashboard opens locally in the browser. MDM metrics are required for review;
Neo4j metrics are optional and do not block the MDM-only pages.

## Review workflow

1. Open `Overview` first. Review blocking failures and coverage warnings before
   comparing counts.
2. Open `MDM Overview` to inspect registered entity and relationship counts.
3. Open `Neo4j Overview` to inspect graph node and relationship counts when the
   graph connection is available.
4. Open `Mismatch Diagnostics` to review entity coverage, relationship coverage,
   pending sync samples, missing-edge samples, and extra graph samples.

Samples are bounded diagnostics, not exhaustive diffs.

## Filters

Use the sidebar `Row limit` to bound diagnostic and sample tables. Choices are
`25`, `50`, `100`, and `250`; the default is `50`.

Detail pages use page-specific single-select filters. `Entity type` and
`Relationship type` both default to `All`, and their options come from the
current MDM registry and metric payloads.

Filtered tables with no matching rows show `No rows match the current filters.`

## Failure states

Missing MDM configuration blocks metric rendering with this exact copy:
MDM configuration is required. Set `MDM_DATABASE_URL`, then restart the dashboard.

MDM connection or permission failures block dependent MDM and graph-backed
rendering with setup or permission guidance. Error copy names expected
environment variables and next actions only.

Neo4j unavailable or permission-denied states do not block `MDM Overview`.
`Neo4j Overview` and `Mismatch Diagnostics` show graph availability guidance
while keeping MDM review available.

## Existing checks

Run these existing checks outside the dashboard when the review output needs
confirmation:

```bash
edgar-warehouse mdm check-connectivity --neo4j
edgar-warehouse mdm counts
edgar-warehouse mdm verify-graph
```

## Validation

Run the focused credential-free validation suite:

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q
```
