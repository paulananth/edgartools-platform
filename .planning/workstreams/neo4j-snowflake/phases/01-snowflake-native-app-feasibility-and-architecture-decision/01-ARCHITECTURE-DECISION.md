# ADR: Snowflake Native App Neo4j Target

## Status

Accepted for milestone planning.

## Context

This milestone is a production migration path with Phase 1 feasibility first (D-02).
The graph target for the milestone is the Snowflake Marketplace Neo4j Graph
Analytics Native App, not an external Neo4j Aura database, self-hosted Neo4j
runtime, or revived non-AWS deployment path.

`edgar-warehouse mdm sync-graph` remains the graph sync command surface (D-03).
Later phases may change what the command materializes and verifies, but the
operator workflow stays in this repository and in the AWS/Snowflake platform
path.

External Neo4j is not retained as a parallel validation target for this
milestone (D-04). Phase 2 through Phase 4 must plan a direct cutover to
Snowflake-hosted graph projection and validation, with rollback/deprecation
questions tracked separately instead of dual-running an external Bolt target.

Graph access comes from Snowflake-managed application roles, grants, database
roles, warehouse or app warehouse context, compute-pool/application privileges,
and Snowflake connection context rather than external `NEO4J_*` secrets (D-05).
Milestone validation must not depend on `NEO4J_URI`, `NEO4J_USER`, or
`NEO4J_PASSWORD`.

Phase 1 is documentation and architecture decision work only. It must not edit
source code, Terraform, dashboard files, generated application JSON, or sibling
workstream artifacts.

## Current Runtime Mapping

The current MDM CLI still treats graph sync as a Bolt workflow:

- `edgar_warehouse/mdm/cli.py` registers `check-connectivity --neo4j`,
  `sync-graph`, `verify-graph`, `load-relationships`, and
  `backfill-relationships` as graph-related command paths.
- `_neo4j_client()` reads `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`,
  `NEO4J_PASSWORD`, `NEO4J_DATABASE`, and `NEO4J_SECRET_JSON`, normalizes
  `neo4j://` to `bolt://`, and returns a `Neo4jGraphClient`.
- `check-connectivity --neo4j` calls `_neo4j_client()` and reports
  `NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD not configured` when no external
  client can be built.
- `sync-graph` calls `_neo4j_client()`, builds `GraphSyncEngine` with the
  returned `Neo4jGraphClient`, syncs entities, and syncs pending relationships.
- `verify-graph` calls `_neo4j_client()`, queries Neo4j node and relationship
  counts with Cypher, and then compares those counts with pending MDM SQL state.
- `load-relationships` derives MDM relationships and optionally calls
  `GraphSyncEngine.build(session, client)` when graph sync is not skipped.
- `backfill-relationships` derives relationship instances and passes the Bolt
  client into the backfill path when configured.

The existing Snowflake configuration surfaces are separate and remain useful:

- `edgar_warehouse/mdm/export.py` uses `MDM_SNOWFLAKE_ACCOUNT`,
  `MDM_SNOWFLAKE_USER`, `MDM_SNOWFLAKE_PASSWORD`, `MDM_SNOWFLAKE_DATABASE`,
  `MDM_SNOWFLAKE_SCHEMA`, `MDM_SNOWFLAKE_WAREHOUSE`, and
  `MDM_SNOWFLAKE_ROLE`, with `DBT_SNOWFLAKE_*` fallbacks.
- `edgar_warehouse/infrastructure/warehouse_settings.py` validates
  `SERVING_EXPORT_ROOT`, accepts `SNOWFLAKE_EXPORT_ROOT` as a compatibility
  fallback, and requires `MDM_DATABASE_URL` for gold-affecting commands.
- `edgar_warehouse/serving/targets/snowflake.py` writes gold Parquet export
  artifacts for Snowflake native S3 pull; this is not the graph sync writer.
- `infra/terraform/access/snowflake/modules/account_access/main.tf` already
  models Snowflake account roles, database usage grants, schema grants,
  warehouse grants, and all/future object grants for tables, views, and dynamic
  tables.
- `infra/scripts/deploy-aws-application.sh` currently injects
  `NEO4J_SECRET_JSON` from the MDM Neo4j secret container and wires MDM Step
  Functions for `mdm_check_connectivity`, `mdm_backfill_relationships`,
  `mdm_sync_graph`, and `mdm_verify_graph`.
- `infra/scripts/run-aws-mdm-e2e.sh` currently validates the AWS MDM chain by
  running `mdm_check_connectivity`, `mdm_backfill_relationships`,
  `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts`.

## Decision

The Snowflake Marketplace Neo4j Graph Analytics Native App replaces the external
Neo4j target for this milestone.

`edgar-warehouse mdm sync-graph` remains the operator command surface for graph
sync. Phase 2 must keep that command name and bounded operator workflow while
changing the graph target from `Neo4jGraphClient`/Bolt writes to Snowflake
graph-ready node and edge materialization for Native App projection.

There is no external Neo4j parallel validation target planned for this
milestone. Milestone validation must not depend on `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_USERNAME`, `NEO4J_PASSWORD`, or `NEO4J_SECRET_JSON`.

Phase 2 and Phase 3 must replace the `_neo4j_client()`/Bolt credential path for
graph sync, graph connectivity checks, `sync-graph`, `verify-graph`, and graph
sync call sites that currently expect `Neo4jGraphClient`. The replacement path
uses Snowflake connection context, Snowflake-managed application roles,
database roles, table/view grants, warehouse or app warehouse context, and
application role assignment.

## Consequences

- The migration is a direct target change from external Neo4j to Snowflake
  Native App projection and procedure execution.
- Existing MDM database state remains the source of truth for entities and
  relationships.
- Existing AWS/Snowflake runtime settings remain in scope where they support
  MDM database access, Snowflake export, and Snowflake grants.
- `NEO4J_*` runtime inputs become legacy implementation details for removal or
  deprecation after the Snowflake-hosted path is proven.
- Phase 1 intentionally does not modify source code, Terraform, dashboard files,
  generated deployment JSON, or sibling workstream artifacts.
- Operators will need a live-account validation step for Marketplace
  availability, application role grants, compute-pool availability, and app
  warehouse behavior before production rollout.

## Credential And Configuration Model

The future graph path is Snowflake-managed:

- Application access is granted through `Neo4j_Graph_Analytics.app_user` for
  graph procedure users and `Neo4j_Graph_Analytics.app_admin` for app
  administration, unless a live install chooses different application names.
- Data access is granted through Snowflake database roles and explicit
  database/schema/table/view privileges for graph projection inputs.
- Future table/view access should follow the existing Snowflake access pattern:
  account roles, database usage, schema usage, warehouse usage, all-object
  `SELECT`, and future-object `SELECT` grants, narrowed to graph schemas and
  Native App needs.
- Runtime execution uses a Snowflake connection context with account, user or
  service principal, role, database, schema, and warehouse/app warehouse context.
- Native App execution uses app roles, application role assignment, required app
  privileges such as compute-pool and warehouse creation, and compute selector
  configuration documented in the runbook.

Phase 2 must replace the `_neo4j_client()` and Bolt credential path for graph
sync with this Snowflake execution context. It must preserve valid existing
settings for:

- MDM database access through `MDM_DATABASE_URL`.
- Snowflake export and writer settings through `MDM_SNOWFLAKE_*` and
  `DBT_SNOWFLAKE_*`.
- Gold/serving export roots through `SERVING_EXPORT_ROOT` and the temporary
  `SNOWFLAKE_EXPORT_ROOT` fallback.
- Snowflake account roles, schema grants, warehouse grants, and future-object
  grants managed by the existing Snowflake access Terraform pattern.

The deployment and E2E scripts are expected to change in later phases so the AWS
MDM chain no longer requires an MDM Neo4j secret or external Bolt connectivity
for milestone validation.

## Downstream Phase Contract

Phase 2 must:

- Keep `edgar-warehouse mdm sync-graph` as the command surface.
- Materialize active MDM entities and relationships into Snowflake graph-ready
  node and edge tables or views.
- Replace graph sync call sites that currently require `Neo4jGraphClient`.
- Preserve bounded execution by limit, relationship type, and operator repair
  workflow where those options already exist.
- Reuse existing Snowflake source/gold and MDM export configuration where valid
  instead of redesigning the gold layer.

Phase 3 must:

- Move `edgar-warehouse mdm verify-graph` to the Snowflake-hosted graph path.
- Replace `check-connectivity --neo4j` milestone validation with Snowflake and
  Native App context checks.
- Prove node counts, relationship parity, and at least one graph traversal or
  connectivity-style check through the Native App path.
- Update the AWS MDM E2E flow so `mdm_sync_graph` and `mdm_verify_graph` no
  longer depend on `NEO4J_SECRET_JSON` or external Bolt connectivity.

Phase 4 must:

- Update the MDM Neo4j review dashboard to inspect the Snowflake-hosted graph
  target.
- Keep dashboard comparison read-only.
- Remove stale external Neo4j credential assumptions from dashboard
  configuration and error messages.

## Rejected Alternatives

- External Neo4j Aura/Bolt as validation target: rejected because milestone
  validation must prove the Snowflake-hosted Native App path, not a parallel
  external graph target.
- Self-hosted Neo4j: rejected because it introduces a non-Native-App runtime and
  does not satisfy the Snowflake Marketplace target decision.
- dual-write validation: rejected because the milestone is a direct migration
  path and D-04 explicitly excludes an external Neo4j parallel target.
- non-AWS non-AWS app runtime revival: rejected because the repository active path is
  AWS plus Snowflake native S3 pull, and this workstream must not revive
  non-AWS deployment paths.
- Dashboard-owned graph writes: rejected because `edgar-warehouse` owns graph
  sync and the dashboard must remain a read-only review surface.

## Open Questions

- Which Snowflake account and region will host the Marketplace Native App for
  production validation?
- Which exact consumer roles will receive `app_user` and `app_admin` in dev and
  prod after live-account install?
- Will Phase 2 create physical graph tables, graph views, or a hybrid of both
  for `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`?
- Which warehouse or app warehouse should run graph projection and verification
  queries in dev and prod?
- When the Snowflake-hosted path is proven, should legacy external Neo4j code be
  removed immediately or retained only for local development during one release?

## Sources

- `.planning/workstreams/neo4j-snowflake/PROJECT.md`
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md`
- `.planning/workstreams/neo4j-snowflake/STATE.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-CONTEXT.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-RESEARCH.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-PATTERNS.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md`
- `edgar_warehouse/mdm/cli.py`
- `edgar_warehouse/mdm/export.py`
- `edgar_warehouse/infrastructure/warehouse_settings.py`
- `edgar_warehouse/serving/targets/snowflake.py`
- `infra/terraform/access/snowflake/modules/account_access/main.tf`
- `infra/scripts/deploy-aws-application.sh`
- `infra/scripts/run-aws-mdm-e2e.sh`
