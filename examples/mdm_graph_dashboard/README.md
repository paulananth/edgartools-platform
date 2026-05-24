# EdgarTools MDM Graph Dashboard

Local Streamlit dashboard for reviewing read-only Phase 9 MDM and Neo4j
coverage metrics.

## Prerequisites

- Python environment managed with `uv`.
- `MDM_DATABASE_URL` for an existing local or dev MDM database.
- Optional Neo4j variables when graph metrics should be checked:
  `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
- Optional graph settings: `NEO4J_DATABASE` or `NEO4J_SECRET_JSON`.

## Run

```bash
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

The dashboard opens locally in the browser. MDM metrics are required for the
review surface. Neo4j metrics are optional; when Neo4j is unavailable, the MDM
Overview and Relationships sections remain usable.

## Visible Sections

- Overview: coverage snapshot for MDM entities, MDM relationships, Neo4j nodes,
  Neo4j edges, pending sync totals, grouped blocking failures, and coverage
  warnings.
- Entities: MDM entity counts by domain with status and last-refreshed data.
- Relationships: active registered relationship types with MDM active counts,
  pending sync counts, Neo4j edge counts when available, and status.
- Graph Coverage: chart-first entity-domain comparison, relationship coverage
  table, pending sync samples, missing-edge samples, and extra graph data
  samples.

## Read-Only Scope

The dashboard does not run sync, repair, migrate, load, or mutation commands.
It only calls read-only helper functions under `edgar_warehouse.mdm` and clears
cached metrics when the operator selects Refresh metrics.

Pending sync, missing-edge, and extra graph data samples are bounded and
non-exhaustive. They are small diagnostic examples for review, not complete
cross-store diff exports.

Status messages name environment variables but do not render raw database URLs,
usernames, passwords, hostnames, secret JSON payloads, or driver exception text.

## Validation

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py -q
```
