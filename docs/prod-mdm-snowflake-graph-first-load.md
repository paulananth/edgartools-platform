# Production MDM Snowflake Graph First Load

This runbook documents the first-time production load path for the
Snowflake-hosted MDM graph:

```text
Snowflake Postgres MDM -> EDGARTOOLS_PROD.MDM mirror
  -> EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION graph tables
  -> Neo4j Graph Analytics Native App verification
```

It is intentionally AWS/Snowflake-only. Do not add external Neo4j, non-AWS
storage, or new secret-management systems to this path.

## Boundaries

- Do not rerun `infra/scripts/bootstrap-prod-mdm.sh` for this step.
- Do not rotate or repopulate `edgartools-prod/mdm/postgres_dsn` or
  `edgartools-prod/mdm/snowflake`.
- Load existing secret values only inside one non-printing shell process that
  directly runs the consuming command.
- Do not print connector traces, raw rows, account identifiers, or generated
  JSON containing environment details.
- Use bounded graph deployment: `sync-graph --limit 100`.
- Strict acceptance is `mdm verify-graph --native-app-compute-pool CPU_X64_XS`.

## Required Production Objects

Snowflake targets:

- Database: `EDGARTOOLS_PROD`
- MDM mirror schema: `MDM`
- Graph schema: `NEO4J_GRAPH_MIGRATION`
- Native App: `Neo4j_Graph_Analytics`
- Native App database role: `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`
- Runtime role: `EDGARTOOLS_PROD_DEPLOYER`
- Compute pool selector: `CPU_X64_XS`

The runtime role needs:

- Usage on `EDGARTOOLS_PROD.MDM`.
- Select on current and future `EDGARTOOLS_PROD.MDM` tables/views.
- Usage, create-table, and create-view on
  `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`.
- Native App `app_user` and `app_admin` application roles for strict local
  verification.

The Native App database role needs graph-schema usage, select on graph
tables/views, and create-table in `NEO4J_GRAPH_MIGRATION`.

## First-Time Mirror Bootstrap

Use this only when `EDGARTOOLS_PROD.MDM` has no current MDM mirror tables.

The bootstrap reflects the existing Snowflake Postgres MDM schema and loads the
repo's MDM relational tables into the Snowflake mirror schema. It replaces only
the dedicated mirror tables in `EDGARTOOLS_PROD.MDM`.

Expected source table set comes from
`edgar_warehouse.mdm.migrations.runtime.MDM_TABLES`.

After the first load, verify:

- all MDM mirror tables exist in `EDGARTOOLS_PROD.MDM`;
- zero-row domain tables are acceptable for a fresh production seed state;
- graph contract seed tables are populated;
- runtime-role current/future select grants remain in place.

## Graph Deploy And Verify

After mirror bootstrap:

1. Run bounded graph materialization:
   `mdm sync-graph --limit 100 --target-database EDGARTOOLS_PROD --target-schema NEO4J_GRAPH_MIGRATION --mdm-database EDGARTOOLS_PROD --mdm-schema MDM`.
2. Run strict verification:
   `mdm verify-graph --native-app-compute-pool CPU_X64_XS`.
3. Record only sanitized counts and check statuses.

Acceptance requires:

- graph sync exits 0;
- node and relationship parity are `ok`;
- Native App status is `ok`;
- `compute_pool`, `graph_info`, `bfs`, and `wcc` checks are `ok`.

## Initial Production Evidence

Initial first-time load completed on 2026-06-22 UTC:

- MDM mirror tables loaded: 19.
- Total mirror rows loaded: 135.
- Expected zero-row fresh-production tables:
  `MDM_SOURCE_REF`, `MDM_COMPANY`, `MDM_ADVISER`, `MDM_PERSON`,
  `MDM_SECURITY`, `MDM_FUND`, `MDM_ENTITY_ATTRIBUTE_STAGE`,
  `MDM_MATCH_REVIEW`, `MDM_CHANGE_LOG`, and `MDM_RELATIONSHIP_INSTANCE`.
- Bounded graph sync materialized 10 nodes and 0 edges.
- Strict verify passed with SQL parity `ok`, Native App status `ok`,
  `CPU_X64_XS`, `graph_info`, `bfs`, and `wcc`.

Detailed launch-workstream evidence:

```text
.planning/workstreams/go-live/phases/09-production-hosted-graph-e2e/evidence/hosted-graph-local.md
```

## Recovery Notes

If first-time mirror bootstrap fails after creating mirror tables, rerun the
same first-time mirror bootstrap before rerunning graph sync. Do not proceed to
AWS MDM E2E or launch-matrix reconciliation until strict local verification
passes again.
