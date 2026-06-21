# Hosted Graph Local Evidence - Phase 9 Plan 09-01

Date: 2026-06-21T22:35:10Z

Environment: production. This artifact records secret-safe local preflight
evidence for the production Snowflake-hosted graph path. It intentionally omits
credential values, Snowflake account identifiers, full Snowflake rows,
connector traces, and Native App logs.

## Scope

Phase 9 consumes the already-populated Phase 8 production MDM secrets and does
not rotate, repopulate, or print them. Task 1 was read-only:

- No production grants were run.
- No MDM data writes were run.
- No graph sync or graph verification command was run.
- No AWS secret value read command was run.
- No Native App graph algorithm command was run.

## Prior Evidence Preconditions

| Evidence | Status | Notes |
|---|---:|---|
| `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/native-pull.md` | PASS | Final SNOW-03 disposition records production native-pull infrastructure live and structurally verified. |
| `.planning/workstreams/go-live/phases/07-production-snowflake-native-pull-and-gold/evidence/dbt-gold.md` | PASS | Final SNOW-04 disposition records 16/16 production models built and 47/47 dbt tests passing. |
| `.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/evidence/mdm-prod-secrets-and-connectivity.md` | COMPLETE | Final Phase 8 verification records both required production MDM secrets populated, production MDM migration/grants applied, and application-role connectivity/counts passing. |

## AWS Secret Metadata Preflight

Command category: `aws secretsmanager describe-secret` only, using
`aws-admin-prod` in `us-east-1`.

| Secret | Status | AWSCURRENT metadata | Last-changed metadata |
|---|---:|---:|---:|
| `edgartools-prod/mdm/postgres_dsn` | PASS | present | present |
| `edgartools-prod/mdm/snowflake` | PASS | present | present |

No secret values were requested or printed.

## Snowflake Native App Metadata Preflight

Connection: `edgartools-prod`

Target:

- Database: `EDGARTOOLS_PROD`
- Graph schema: `NEO4J_GRAPH_MIGRATION`
- Native App: `Neo4j_Graph_Analytics`
- Database role: `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`
- Compute pool selector: `CPU_X64_XS`

Read-only metadata checks:

| Check | Status | Sanitized result |
|---|---:|---|
| Native App installation | PASS | Installed and visible. |
| Grants to Native App | PASS | Application grant metadata visible. |
| Native App `app_user` role grant | PASS | Expected application role mapping visible. |
| Native App `app_admin` role grant | PASS | Expected application role mapping visible. |
| Compute pool selector visibility | PASS | `CPU_X64_XS` is available from the Native App compute-pool listing. |
| Production database exists | PASS | `EDGARTOOLS_PROD` is visible. |
| Production graph schema exists | BLOCKED | `NEO4J_GRAPH_MIGRATION` is not visible from metadata preflight. |
| Production database role exists | BLOCKED | `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE` is not visible from metadata preflight. |
| Database-role privilege grants | BLOCKED | Grant metadata is unavailable because the production database role is missing or not visible. |

## BLOCKED - Production Graph Schema And Database-Role Grants

Owner: production Snowflake operator for Phase 9.

Remediation category: run the production-scoped Native App provisioning/grant
set after explicit operator approval. The remediation must target
`EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`, not the dev grant script unchanged.

Required target state before graph writes:

- Create or confirm schema `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`.
- Create or confirm database role
  `EDGARTOOLS_PROD.NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`.
- Grant database/schema usage, current/future table/view select, and scoped
  create-table privileges required by `mdm verify-graph`.
- Grant the database role to `Neo4j_Graph_Analytics`.
- Reconfirm compute pool selector `CPU_X64_XS` remains visible.

No MDM graph sync, bounded MDM smoke, Native App graph algorithm, or launch
matrix update should run until the production-scoped grant remediation is
operator-approved and recorded.

## Task 1 Disposition

Task 1 completed its read-only preflight and stopped before state-changing
work. Phase 9 Plan 09-01 may continue only at the explicit operator approval
checkpoint for production Native App provisioning and bounded graph writes.

## Task 2 Operator Approval

Operator approval received in-thread after the Task 1 checkpoint. Approved
target state:

- Database/schema: `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`
- Native App: `Neo4j_Graph_Analytics`
- Database role: `NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE`
- Compute pool selector: `CPU_X64_XS`
- Bounded local MDM smoke only if graph inputs are empty:
  `run --entity-type all --limit 5` and
  `backfill-relationships --limit 100`
- Bounded graph sync: `sync-graph --limit 100`

## Task 3 Production Native App Grants

Execution time: 2026-06-21 UTC.

The dev-scoped grant file was used only as a template. The executed target was
production-scoped: `EDGARTOOLS_PROD.NEO4J_GRAPH_MIGRATION`.

Statement categories:

| Category | Status |
|---|---:|
| Grant Native App account create-compute-pool privilege | PASS |
| Grant Native App account create-warehouse privilege | PASS |
| Create/confirm graph schema | PASS |
| Create/confirm production database role | PASS |
| Grant database usage to database role | PASS |
| Grant graph schema usage to database role | PASS |
| Grant select on current graph-schema tables/views to database role | PASS |
| Grant select on future graph-schema tables/views to database role | PASS |
| Grant create-table on graph schema to database role | PASS |
| Grant database role to Native App | PASS |
| Create/confirm Native App user/admin roles | PASS |
| Grant Native App `app_user` and `app_admin` application roles | PASS |
| Grant graph database/schema read visibility to Native App user role | PASS |

Post-grant metadata checks:

| Check | Status | Sanitized result |
|---|---:|---|
| Production graph schema exists | PASS | Schema metadata visible. |
| Production database role exists | PASS | Database role metadata visible. |
| Database/schema usage grants | PASS | Required categories visible. |
| Graph schema create-table grant | PASS | Required category visible. |
| Future table/view select grants | PASS | Required future-grant categories visible. |
| Current graph table count before sync | PASS | zero current graph tables, expected before `sync-graph`. |
| Compute pool selector visibility | PASS | `CPU_X64_XS` remains available. |

No raw Snowflake rows, connector traces, Native App logs, or account identifiers
were recorded. Task 3 unblocks Task 4.
