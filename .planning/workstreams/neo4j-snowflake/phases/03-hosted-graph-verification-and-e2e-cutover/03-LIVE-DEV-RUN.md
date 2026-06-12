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

## Acceptance Status

Phase 3 final live acceptance is blocked.

The hosted Snowflake SQL parity portion is clean, and grant validation now succeeds, but
Native App algorithm proof cannot run until the application exposes at least one compute
pool selector such as `CPU_X64_XS`.

Full AWS E2E execution was not started after the local strict `verify-graph` failure,
because the current dev environment cannot satisfy the Native App compute-pool gate. The
latest historical `mdm_verify_graph` Step Functions success is not treated as final Phase
3 acceptance evidence for this branch.

## Required Follow-Up

1. In Snowsight, activate or repair `Neo4j_Graph_Analytics` so
   `CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();` returns
   `CPU_X64_XS` or another supported selector.
2. If the supported selector is not `CPU_X64_XS`, rerun `verify-graph` with
   `--native-app-compute-pool <selector>` and update the default only after operator
   review.
3. Deploy an AWS dev image containing the strict hosted `verify-graph` implementation.
4. Run:

```bash
bash infra/scripts/run-aws-mdm-e2e.sh \
  --env dev \
  --aws-profile sec_platform_deployer
```

5. Capture the new Step Functions execution ARNs/statuses and the passing
   `verify-graph` Native App smoke status.
