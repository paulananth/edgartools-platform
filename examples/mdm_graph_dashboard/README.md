# EdgarTools MDM Graph Dashboard

Local Streamlit shell for checking MDM SQL connectivity and optional Neo4j
connectivity before the richer review metrics arrive in later phases.

## Prerequisites

- Python environment managed with `uv`.
- `MDM_DATABASE_URL` for an existing local or dev MDM database.
- Optional Neo4j variables when graph connectivity should be checked:
  `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`.
- Optional graph settings: `NEO4J_DATABASE` or `NEO4J_SECRET_JSON`.

## Run

```bash
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

The dashboard opens locally in the browser. The Overview view checks required
MDM access first, then reports Neo4j as connected, unavailable, or not
configured without blocking MDM-only review.

## Scope

This Phase 8 dashboard is read-only. It uses helper modules under
`edgar_warehouse.mdm` for bounded status and smoke checks, and it does not
offer data-changing controls. The non-Overview navigation entries are
placeholders until later dashboard phases add review metrics and operator
workflows.

Status messages name environment variables but do not render raw database URLs,
usernames, passwords, hostnames, secret JSON payloads, or driver exception text.

## Validation

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py
uv run pytest tests/mdm tests/architecture
```
