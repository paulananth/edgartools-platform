# Phase 3 Live Dev Run

Date: 2026-06-12 UTC
Environment: dev
Snowflake connection: `snowconn`
Snowflake database: `EDGARTOOLS_DEV`
AWS profile: `sec_platform_deployer`

This artifact captures non-secret evidence only. It omits passwords, tokens, DSNs,
full task logs, and raw Native App job logs.

## Commands Run

```bash
SNOW_CONNECTION=snowconn \
snow sql -c snowconn \
  -f infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql
```

Result: succeeded.

Observed non-secret outcomes:

- `EDGARTOOLS_DEV.NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE` exists.
- `Neo4j_Graph_Analytics` has the database role grant.
- `EDGARTOOLS_GRAPH_APP_USER` and `EDGARTOOLS_GRAPH_APP_ADMIN` exist.
- Native App application roles `app_user` and `app_admin` are granted to the consumer roles.
- Current/future table and view SELECT grants were applied for `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`.
- Scoped `CREATE TABLE` on `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION` was applied.
- `CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools()` returned no rows.

Additional Native App account privileges were then applied from the Phase 1 runbook and
added back to the repo-managed grant SQL:

```sql
GRANT CREATE COMPUTE POOL ON ACCOUNT TO APPLICATION Neo4j_Graph_Analytics;
GRANT CREATE WAREHOUSE ON ACCOUNT TO APPLICATION Neo4j_Graph_Analytics;
```

Result: both grants succeeded. A repeat call to
`Neo4j_Graph_Analytics.graph.show_available_compute_pools()` still returned no rows.

```bash
SNOW_CONNECTION=snowconn \
SNOWFLAKE_CONNECTION=snowconn \
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV \
uv run --extra snowflake edgar-warehouse mdm verify-graph
```

Result: failed as expected because strict Native App proof is now a hard gate.

Non-secret verification payload summary:

- Overall status: `failed`
- Snowflake graph nodes: `15`
- Snowflake graph edges: `4`
- Node parity status: `ok`
- Relationship parity status: `ok`
- Missing/extra node diagnostics: none
- Missing/extra edge diagnostics: none
- Missing edge endpoint diagnostics: none
- Native App status: `failed`
- Native App checks:
  - `app_installation`: `ok`
  - `app_user_role_grant`: `ok`
  - `app_admin_role_grant`: `ok`
  - `database_role_to_application`: `ok`
  - `database_role_privileges`: `ok`
  - `compute_pool`: `failed`
  - `graph_schema_sample`: `ok`
- Remediation emitted by `verify-graph`:
  `Activate NEO4J_GRAPH_ANALYTICS and confirm compute pool selector CPU_X64_XS is available from GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS().`

Relationship parity by type:

| Relationship type | MDM active | Snowflake graph | Delta |
| --- | ---: | ---: | ---: |
| AUDITED_BY | 0 | 0 | 0 |
| COMPANY_HOLDS | 0 | 0 | 0 |
| EMPLOYED_BY | 0 | 0 | 0 |
| HAS_PARENT_COMPANY | 0 | 0 | 0 |
| HOLDS | 1 | 1 | 0 |
| INSTITUTIONAL_HOLDS | 0 | 0 | 0 |
| ISSUED_BY | 1 | 1 | 0 |
| IS_ENTITY_OF | 0 | 0 | 0 |
| IS_INSIDER | 1 | 1 | 0 |
| IS_PERSON_OF | 0 | 0 | 0 |
| MANAGES_FUND | 1 | 1 | 0 |

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
```

Result: succeeded.

Relevant non-secret Step Functions status:

| Workflow | Latest status | Latest execution name |
| --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `ci-fix-mdm-migrate-1780711962` |
| `mdm_check_connectivity` | `FAILED` | `mdm-sfpg-audit-mdm-check-connectivity-1781019163` |
| `mdm_run` | `SUCCEEDED` | `smoke-1781120544-cik-320193-mdm-run` |
| `mdm_backfill_relationships` | `SUCCEEDED` | `smoke-1781120544-cik-320193-mdm-backfill` |
| `mdm_sync_graph` | `SUCCEEDED` | `smoke-1781120544-cik-320193-mdm-sync` |
| `mdm_verify_graph` | `SUCCEEDED` | `smoke-1781120544-cik-320193-mdm-verify` |
| `mdm_counts` | `SUCCEEDED` | `mdm-sfpg-audit-mdm-counts-1781025197` |

The updated local script emitted warning-only messages for lingering Neo4j references in
the deployment summary and deploy script. It no longer starts `mdm_check_connectivity`
as a required success step.

After follow-up grilling, the script was further updated so full E2E runs preflight
local strict `edgar-warehouse mdm verify-graph` before starting AWS Step Functions.
`--status-only` remains a pure AWS status report, and `--skip-preflight` is available
only for emergency/debug runs that cannot satisfy Phase 3 acceptance.

## Post-Blocker Verification

After the operator activation/repair step completed, strict local verification was rerun:

```bash
SNOW_CONNECTION=snowconn \
SNOWFLAKE_CONNECTION=snowconn \
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV \
uv run --extra snowflake edgar-warehouse mdm verify-graph
```

Result: succeeded.

Non-secret verification payload summary:

- Overall status: `ok`
- Snowflake graph nodes: `15`
- Snowflake graph edges: `4`
- Node parity status: `ok`
- Relationship parity status: `ok`
- Missing/extra node diagnostics: none
- Missing/extra edge diagnostics: none
- Missing edge endpoint diagnostics: none
- Native App status: `ok`
- Native App compute pool: `CPU_X64_XS`
- Native App checks:
  - `app_installation`: `ok`
  - `app_user_role_grant`: `ok`
  - `app_admin_role_grant`: `ok`
  - `database_role_to_application`: `ok`
  - `database_role_privileges`: `ok`
  - `compute_pool`: `ok` (`7` rows)
  - `graph_schema_sample`: `ok`
  - `graph_info`: `ok`
  - `bfs`: `ok`
  - `wcc`: `ok`
- `phase3_acceptance`: `true`

The hosted graph E2E status was then verified:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --status-only
```

Result: succeeded.

Relevant latest Step Functions status:

| Workflow | Latest status | Latest execution name | Started |
| --- | --- | --- | --- |
| `mdm_migrate` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-migrate` | `2026-06-12T11:21:17.727000-04:00` |
| `mdm_run` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-run` | `2026-06-12T11:22:27.408000-04:00` |
| `mdm_backfill_relationships` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-backfill` | `2026-06-12T11:24:20.873000-04:00` |
| `mdm_sync_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-sync` | `2026-06-12T11:26:16.952000-04:00` |
| `mdm_verify_graph` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-verify` | `2026-06-12T11:27:51.841000-04:00` |
| `mdm_counts` | `SUCCEEDED` | `aws-mdm-e2e-1781277675-counts` | `2026-06-12T11:29:26.038000-04:00` |

The status-only command still emitted warning-only messages for lingering Neo4j references
in deployment artifacts/scripts. Those references did not block `mdm_sync_graph` or
`mdm_verify_graph`.

## Acceptance Status

Phase 3 final live acceptance passed.

The hosted Snowflake SQL parity gate is clean, the Neo4j Graph Analytics Native App exposes
`CPU_X64_XS`, the default `GRAPH_INFO`/`BFS`/`WCC` smoke proof succeeds, and the latest AWS
MDM hosted graph E2E chain reached `mdm_sync_graph` and strict `mdm_verify_graph`
successfully without external Neo4j credential validation.

## Remaining Follow-Up

1. Continue treating stale deployment/script `NEO4J_*` references as warning-only unless
   they block the hosted graph path.
2. Start Phase 4 dashboard migration so dashboard comparison moves to the Snowflake-hosted
   graph target.

Useful Phase 3 regression command:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer \
  --snow-connection snowconn \
  --snowflake-database EDGARTOOLS_DEV
```
