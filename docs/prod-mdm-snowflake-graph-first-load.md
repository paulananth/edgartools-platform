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
- Runtime role (mirror writer, `mdm export`): `EDGARTOOLS_PROD_LOADER` --
  **not** `EDGARTOOLS_PROD_DEPLOYER` as originally documented here. See the
  2026-08-09 Recovery Notes entry: the deployer role was never actually
  granted MDM-schema access in prod, and the export path authenticates as
  `EDGARTOOLS_PROD_LOADER` (`edgar_warehouse.mdm.export.py`'s
  `MDM_SNOWFLAKE_SECRET_JSON` secret's `ROLE` field).
- Runtime role (graph sync, `mdm sync-graph`): `EDGARTOOLS_PROD_DEPLOYER`.
- Compute pool selector: `CPU_X64_XS`

`EDGARTOOLS_PROD_LOADER` needs:

- Usage on `EDGARTOOLS_PROD.MDM`.
- Select, insert, update, delete on current and future
  `EDGARTOOLS_PROD.MDM` tables (granted by
  `infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql`).

`EDGARTOOLS_PROD_DEPLOYER` needs:

- Select on current and future `EDGARTOOLS_PROD.MDM` tables/views (read-only,
  for graph sync).
- Usage, create-table, and create-view on
  `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`.
- Native App `app_user` and `app_admin` application roles for strict local
  verification.

The Native App database role needs graph-schema usage, select on graph
tables/views, and create-table in `NEO4J_GRAPH_MIGRATION`.

## First-Time Mirror Bootstrap

Use this whenever `EDGARTOOLS_PROD.MDM` has no current MDM mirror tables --
including after a Snowflake account rebuild/cutover, not just the very first
time. This step is **not** covered by any Terraform root or by
`deploy-aws-application.sh`/`deploy-snowflake-stack.sh` -- it must be run
explicitly.

Run:

```bash
MDM_DATABASE_URL=sqlite:///:memory: uv run python \
    infra/scripts/generate_mdm_mirror_ddl.py > /tmp/mdm_mirror_bootstrap.sql
snow sql --connection edgartools-prod -f /tmp/mdm_mirror_bootstrap.sql
```

or apply the committed snapshot directly:
`snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql`.

The generator reflects `edgar_warehouse.mdm.database`'s SQLAlchemy models --
the same models the Postgres MDM instance is built from -- for exactly the
19 tables in `edgar_warehouse.mdm.migrations.runtime.MDM_TABLES`, and emits
`CREATE TABLE IF NOT EXISTS` DDL plus the DML grants
`EDGARTOOLS_PROD_LOADER` needs. It creates the schema and table *shape* only
(zero rows) -- `mdm export` populates it on its next run from whatever is
pending in the Postgres MDM instance's `mdm_change_log`; there is no
row-level Postgres-to-Snowflake copy step.

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

### 2026-08-09: schema lost on account cutover, no script to recreate it

The 2026-06-22 first-time load above was a one-off, uncommitted manual shell
session -- it had no script. When the platform's Snowflake account was
rebuilt for the go-live cutover (Cutover Stages 1-13), every other piece
(gold, source, loader role, dashboards, Neo4j app) was re-provisioned via
Terraform/bootstrap SQL, but this step had nothing to re-run. `EDGARTOOLS_PROD.MDM`
came back as an empty, `ACCOUNTADMIN`-owned schema (created 2026-08-07, zero
tables, zero grants to any application role), and the next `mdm export`
failed: `SQL compilation error: Object 'EDGARTOOLS_PROD.MDM.MDM_ENTITY' does
not exist or not authorized.`

A second, independent gap compounded it: even if the tables had existed,
`EDGARTOOLS_PROD_LOADER` -- the role `mdm export`'s mirror writer actually
authenticates as -- had zero grants on the MDM schema. The "Required
Production Objects" grants above were only ever written for
`EDGARTOOLS_PROD_DEPLOYER`; nothing carried them over when the export path
was standardized onto `EDGARTOOLS_PROD_LOADER`.

Fixed by writing `infra/scripts/generate_mdm_mirror_ddl.py` (reflects the
schema straight from `edgar_warehouse.mdm.database`'s SQLAlchemy models, so
it can't drift from what Postgres actually has) and committing its output as
`infra/snowflake/sql/bootstrap/09_mdm_mirror_schema.sql` -- the first-time
mirror bootstrap is no longer a lost, unrepeatable manual session. Applied
live to prod 2026-08-09: 19 tables created, `EDGARTOOLS_PROD_LOADER` granted
schema USAGE + current/future table SELECT/INSERT/UPDATE/DELETE.

**Lesson:** any provisioning step that isn't Terraform or a committed script
does not survive an account rebuild, however carefully it was documented in
prose. If a runbook says "run this once," it needs a script next to it, not
just a description of what an operator did.
