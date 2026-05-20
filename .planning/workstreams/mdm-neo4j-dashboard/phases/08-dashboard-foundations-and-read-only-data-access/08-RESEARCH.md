# Phase 08 Research: Dashboard Foundations And Read-Only Data Access

Researched: 2026-05-17
Scope: DASH-01, DASH-02, DASH-03, ISO-01, ISO-02 only.
Confidence: HIGH for codebase patterns and phase constraints; MEDIUM for exact helper names because implementation has not started.

## Implementation Surface

Phase 8 should create a local Streamlit operator shell plus reusable read-only helper modules; it should not extend the Snowflake gold dashboard. [VERIFIED: 08-CONTEXT.md, 08-UI-SPEC.md]

Required user-visible surface:
- Streamlit page config: `page_title="EdgarTools MDM Graph"`, `layout="wide"`. [VERIFIED: 08-UI-SPEC.md]
- Sidebar title `EdgarTools MDM`, caption `Read-only MDM and Neo4j status`, navigation entries `Overview`, `Entities`, `Relationships`, `Graph Coverage`, `Neighborhood`. [VERIFIED: 08-UI-SPEC.md]
- Only `Overview` is implemented in Phase 8; the other pages render the exact placeholder copy from the UI spec. [VERIFIED: 08-UI-SPEC.md]
- The only implemented action is `Refresh data`; it clears Streamlit caches and reruns status/smoke helpers. [VERIFIED: 08-UI-SPEC.md]
- MDM is required at startup; Neo4j is optional and must not block MDM-backed display. [VERIFIED: 08-CONTEXT.md, 08-UI-SPEC.md]

Implementation boundaries:
- UI files should live in a new examples-style operator dashboard path, not `infra/snowflake/streamlit`. [VERIFIED: 08-CONTEXT.md]
- Reusable query/helper code should live under `edgar_warehouse`, near MDM code, so it can be unit-tested without Streamlit. [VERIFIED: 08-CONTEXT.md]
- Do not edit generated deployment JSON, dbt/gold models, Terraform, Step Functions, rollout scripts, or other workstream planning artifacts. [VERIFIED: REQUIREMENTS.md, AGENTS.md, STATE.md]

## Existing Patterns To Reuse

Use `uv` for execution and dependency management; do not introduce bare `pip` setup steps. [VERIFIED: AGENTS.md]

Launch pattern should be uv-based, for example:

```bash
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

`pyproject.toml` already defines a `dashboard` extra with `streamlit>=1.32` and an `mdm-runtime` extra with SQLAlchemy, PostgreSQL, Neo4j, and related runtime libraries. [VERIFIED: pyproject.toml]

Streamlit UI patterns to reuse from `examples/dashboard/edgar_universe_dashboard.py`:
- `st.set_page_config(..., layout="wide")`. [VERIFIED: examples/dashboard/edgar_universe_dashboard.py]
- Sidebar navigation. [VERIFIED: examples/dashboard/edgar_universe_dashboard.py]
- Cached query/resource calls. [VERIFIED: examples/dashboard/edgar_universe_dashboard.py]
- `st.info`, `st.warning`, and `st.error` for state handling. [VERIFIED: examples/dashboard/edgar_universe_dashboard.py]
- `st.dataframe(..., use_container_width=True, hide_index=True)` for bounded smoke output only. [VERIFIED: examples/dashboard/edgar_universe_dashboard.py, 08-UI-SPEC.md]

MDM connection patterns to reuse:
- `edgar_warehouse.mdm.database.get_engine()` reads `MDM_DATABASE_URL` by default and installs existing SQL logging. [VERIFIED: edgar_warehouse/mdm/database.py]
- `get_session(engine)` returns a SQLAlchemy `Session`. [VERIFIED: edgar_warehouse/mdm/database.py]
- Existing tests use in-memory SQLite fixtures with `Base.metadata.create_all(engine)` for credential-free MDM testing. [VERIFIED: tests/mdm/conftest.py]

Neo4j connection patterns to reuse:
- `Neo4jGraphClient` owns driver creation, session lifecycle, and query logging. [VERIFIED: edgar_warehouse/mdm/graph.py]
- The CLI already supports `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON`. [VERIFIED: edgar_warehouse/mdm/cli.py, docs/neo4j.md]
- `neo4j://` is normalized to `bolt://` in existing CLI/test connection helpers for single-instance deployments. [VERIFIED: edgar_warehouse/mdm/cli.py, tests/mdm/conftest.py]

## Read-Only Data Access Strategy

Recommended module shape:
- `edgar_warehouse/mdm/dashboard_readonly.py`: MDM status and smoke-query helpers.
- `edgar_warehouse/mdm/graph_readonly.py`: Neo4j optional config/status and smoke-query helpers.
- `examples/mdm_graph_dashboard/streamlit_app.py`: Streamlit shell only; no direct SQL/Cypher construction except calling helper functions.

MDM helper contract:
- Return structured objects/dicts, not printed JSON. [VERIFIED: 08-CONTEXT.md]
- Use bounded SELECT-only SQLAlchemy queries. [VERIFIED: 08-CONTEXT.md]
- Keep Phase 8 smoke output minimal, such as `SELECT 1 AS ok` and a tiny metadata/sample query with limit 5-10. [VERIFIED: 08-UI-SPEC.md]
- Roll back/close sessions after reads; do not call `commit()` from dashboard helper paths. [VERIFIED: 08-CONTEXT.md]
- Do not import or call `MDMPipeline`, migration runtime, resolver writes, `derive_relationships`, `load_relationships`, `sync_graph`, or stewardship/mutation handlers. [VERIFIED: 08-CONTEXT.md, edgar_warehouse/mdm/cli.py]

Neo4j helper contract:
- Reuse `Neo4jGraphClient` construction conventions, but add a review-only wrapper for status/smoke reads. [VERIFIED: 08-CONTEXT.md, edgar_warehouse/mdm/graph.py]
- Optional config result should distinguish `not_configured`, `connected`, and `query_failed`. [VERIFIED: 08-UI-SPEC.md]
- Smoke query should be read-only and static, for example `RETURN 1 AS ok`; avoid label/relationship interpolation in Phase 8. [VERIFIED: 08-UI-SPEC.md]
- Do not import or call `GraphSyncEngine`, `node_merge_cypher`, `relationship_merge_cypher`, `sync_entities`, `sync_pending`, `backfill_relationship_instances`, or any Cypher containing `MERGE`, `CREATE`, `DELETE`, `SET`, or `REMOVE`. [VERIFIED: 08-CONTEXT.md, edgar_warehouse/mdm/graph.py]

Do not use CLI handlers directly from Streamlit. `_handle_counts`, `_handle_check_connectivity`, and `_handle_verify_graph` print JSON and some adjacent handlers mutate MDM/Neo4j state. They are reference material only. [VERIFIED: edgar_warehouse/mdm/cli.py]

## Secret-Safe Error Handling

Required display copy:
- MDM missing/unreachable: `MDM database unavailable. Check \`MDM_DATABASE_URL\`, confirm the database is reachable, and restart the dashboard.` [VERIFIED: 08-UI-SPEC.md]
- Neo4j not configured: `Neo4j is not configured. MDM relationship tables are still available.` [VERIFIED: 08-UI-SPEC.md]
- Neo4j query failure: `Neo4j query failed. Check \`NEO4J_URI\`, \`NEO4J_USER\`, \`NEO4J_PASSWORD\`, and network access.` [VERIFIED: 08-UI-SPEC.md]

Sanitization rules:
- Never render `MDM_DATABASE_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, or `NEO4J_SECRET_JSON` values. [VERIFIED: 08-UI-SPEC.md, docs/neo4j.md]
- Error objects shown in Streamlit should expose exception class/category and an actionable message, not raw exception strings that may include URLs or credentials. [ASSUMED]
- Sidebar diagnostics may show labels such as `MDM connected`, `MDM unavailable`, `Neo4j connected`, `Neo4j not configured`, or `Neo4j failed`; no hostnames or DSNs are required in Phase 8. [VERIFIED: 08-UI-SPEC.md]
- Existing CLI safe-argument filtering blocks argument names containing `password`, `secret`, `token`, or `key`; follow the same spirit for dashboard diagnostics. [VERIFIED: edgar_warehouse/mdm/cli.py]

## Suggested File Plan

Add:
- `examples/mdm_graph_dashboard/streamlit_app.py` - Streamlit shell, sidebar nav, status panel, placeholders, refresh action.
- `examples/mdm_graph_dashboard/README.md` - uv launch docs, env var names, read-only guarantee, Phase 8 scope.
- `edgar_warehouse/mdm/dashboard_readonly.py` - MDM required status/smoke helpers.
- `edgar_warehouse/mdm/graph_readonly.py` - Neo4j optional status/smoke helpers and secret-safe config loading.
- `tests/mdm/test_dashboard_readonly.py` - MDM helper unit tests with SQLite fixtures and no live credentials.
- `tests/mdm/test_graph_readonly.py` - Neo4j helper tests with fake client/session; assert no write Cypher tokens.
- `tests/architecture/test_dashboard_foundation_boundaries.py` - static import/scope guard preventing Streamlit/helper paths from importing mutation surfaces.

Avoid:
- `infra/snowflake/streamlit/*`, `infra/snowflake/dbt/*`, Terraform roots, `infra/aws-*-application.json`, rollout scripts, and other workstream directories. [VERIFIED: REQUIREMENTS.md, AGENTS.md]
- `examples/dashboard/edgar_universe_dashboard.py` except as a read-only reference. [VERIFIED: 08-CONTEXT.md]

## Verification Commands

Fast local checks:

```bash
uv run pytest tests/mdm/test_dashboard_readonly.py tests/mdm/test_graph_readonly.py tests/architecture/test_dashboard_foundation_boundaries.py
```

Broader regression check:

```bash
uv run pytest tests/mdm tests/architecture
```

Dashboard smoke launch:

```bash
MDM_DATABASE_URL="<local-or-dev-db-url>" \
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

Optional Neo4j smoke launch:

```bash
MDM_DATABASE_URL="<local-or-dev-db-url>" \
NEO4J_URI="<neo4j-uri>" \
NEO4J_USER="<neo4j-user>" \
NEO4J_PASSWORD="<neo4j-password>" \
uv run --extra dashboard --extra mdm-runtime streamlit run examples/mdm_graph_dashboard/streamlit_app.py
```

Do not add commands that run migrations, derive relationships, sync graph, deploy AWS components, generate application JSON, or refresh Snowflake/dbt. [VERIFIED: REQUIREMENTS.md, 08-CONTEXT.md]

## Validation Architecture

Test framework: pytest via `uv run pytest`. [VERIFIED: tests directory, AGENTS.md]

Credential-free tests:
- MDM helper tests should use in-memory SQLite and existing MDM model metadata/seeding patterns from `tests/mdm/conftest.py`. [VERIFIED: tests/mdm/conftest.py]
- Neo4j helper tests should use fake driver/client/session objects; do not require live `NEO4J_*` credentials for Phase 8. [VERIFIED: 08-CONTEXT.md]
- Streamlit shell tests can be static/import-level in Phase 8; full browser testing is not required by the phase scope. [ASSUMED]

Requirement-to-test map:

| Requirement | Behavior | Suggested Test |
|-------------|----------|----------------|
| DASH-01 | uv launch docs and existing env var names | README/static assertions |
| DASH-02 | MDM helpers are SELECT-only and never commit | SQLite helper tests plus monkeypatch session `commit()` failure |
| DASH-03 | Neo4j helpers use read-only static smoke query | fake Neo4j session captures query; assert no write tokens |
| ISO-01 | edits remain in dashboard worktree/workstream | git/status review plus file-plan adherence |
| ISO-02 | no pipeline, dbt, Step Functions, rollout mutation | architecture test for forbidden imports/paths |

Safety assertions worth adding:
- Dashboard helper modules do not import `MDMPipeline` or `GraphSyncEngine`. [VERIFIED: 08-CONTEXT.md]
- Captured Cypher from graph-readonly tests does not contain `MERGE`, `CREATE`, `DELETE`, `SET`, `REMOVE`, or `CALL`. [VERIFIED: 08-CONTEXT.md]
- MDM helper smoke queries use hard-coded bounds and do not accept user SQL. [VERIFIED: 08-UI-SPEC.md]
- Error messages include env var names but not env var values. [VERIFIED: 08-UI-SPEC.md]

## Planning Risks And Constraints

Main risk: `edgar_warehouse/mdm/graph.py` is sync-oriented and contains write templates (`MERGE`, `SET`) near the reusable `Neo4jGraphClient`; implementation must avoid importing sync helpers into dashboard-readonly code. [VERIFIED: edgar_warehouse/mdm/graph.py]

Do not implement Phase 9 metrics in Phase 8. Entity counts, relationship counts, Neo4j node/edge counts, pending sync counts, missing-edge diagnostics, charts, and operator filters are explicitly deferred. [VERIFIED: ROADMAP.md, 08-UI-SPEC.md]

Do not add mutation controls. Buttons for sync graph, derive relationships, load relationships, migrate, seed universe, repair, merge, or accept/reject review violate the phase. [VERIFIED: 08-UI-SPEC.md]

Keep AWS-focused repository guidance intact, but Phase 8 is local-only; do not add new deployment paths, secret-management systems, Terraform, ECS, Step Functions, Snowflake, dbt, or generated application JSON. [VERIFIED: AGENTS.md, REQUIREMENTS.md]

Existing `docs/neo4j.md` includes Azure Key Vault notes, but this phase should document only the existing local/runtime environment variables and must not introduce new non-AWS secret-management steps. [VERIFIED: docs/neo4j.md, AGENTS.md]

Assumptions needing planner awareness:
- [ASSUMED] Secret-safe error wrappers may need to mask raw SQLAlchemy/Neo4j exception text rather than displaying it directly.
- [ASSUMED] Static Streamlit/import tests are sufficient for Phase 8 because UI-SPEC only requires shell/status behavior, not browser-level interaction testing.

