# Phase 1 Research: Neo4j Graph Analytics Native App For Snowflake

**Updated:** 2026-05-25
**Status:** Complete for planning

## Current Source Findings

### Native App Install And Activation

Neo4j Graph Analytics for Snowflake is delivered as a Snowflake Native Application and is
installed from the Snowflake Marketplace. Installation requires event sharing. After the
app is installed, Snowflake app privileges must be granted and the app activated so it can
create internal resources such as compute pools.

Source: https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/

### Required Application Privileges

The app requires `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`. Snowflake Native Apps with
Snowpark Container Services generally require consumer-granted privileges before creating
compute pools and services; apps can use grant callbacks or setup procedures to create
resources only after the needed privileges exist.

Sources:
- https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/
- https://docs.snowflake.com/en/developer-guide/native-apps/container-services

### Roles And Grants

The Neo4j app exposes application roles including `app_user` and `app_admin`. A consumer
role receives `Neo4j_Graph_Analytics.app_user` to run graph procedures, while an admin
role receives `Neo4j_Graph_Analytics.app_admin` to administer compute pools and the app
warehouse. The app needs database/schema usage and table/view select grants for graph
projection inputs. Database roles are the documented way to cover future tables/views and
grant those privileges to the application.

Source: https://neo4j.com/docs/snowflake-graph-analytics/current/administration/

### Compute Pools And Warehouse

Algorithms run through Snowpark Container Services compute pools selected by strings such
as `CPU_X64_XS`. The app creates internal compute pools automatically when activated.
The documented defaults are run-on-demand oriented: minimum one node, maximum one node,
auto-resume enabled, auto-suspend after a short timeout, and initially suspended. The app
also creates an application warehouse named after the application, for example
`Neo4j_Graph_Analytics_app_warehouse`, to read and write consumer data.

Source: https://neo4j.com/docs/snowflake-graph-analytics/current/administration/

### Graph Projection Contract

The Native App projects graphs from Snowflake tables/views. Node inputs require a
`nodeId` column. Relationship inputs require `sourceNodeId` and `targetNodeId`. Additional
columns become node or relationship properties. If existing tables do not have the exact
column names, views can adapt them to the required names.

Source: https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/

### Algorithm Invocation Pattern

Graph algorithms are called as application procedures, for example WCC or PageRank, with
a compute pool selector and a configuration object containing `project`, `compute`, and
`write` sections. Example configurations use `defaultTablePrefix`, `nodeTables`, and
`relationshipTables`, then write algorithm outputs back to Snowflake tables.

Sources:
- https://www.snowflake.com/en/developers/guides/practical-graph-analytics-neo4j-snowflake/
- https://neo4j.com/docs/snowflake-graph-analytics/current/algorithms/

## Planning Implications

- Phase 1 must not treat this as a Bolt endpoint swap. It is a Snowflake table/view
  projection plus application privilege and procedure-call model.
- Later `edgar-warehouse mdm sync-graph` changes should materialize graph-ready
  Snowflake inputs rather than write directly to an external Neo4j service.
- The credential model should move from `NEO4J_*` secrets to Snowflake roles,
  database roles, app roles, app grants, and the Snowflake connection context already
  used by the AWS/Snowflake platform.
- The minimum contract for later implementation is:
  - node rows expose `nodeId`, entity type/label, stable entity key, source metadata,
    and sync timestamps;
  - edge rows expose `sourceNodeId`, `targetNodeId`, relationship type, source
    accession or business key when available, properties, and sync timestamps;
  - Native App projection config maps those tables/views into graph algorithm calls.
- Phase 1 should document unresolved live-account checks rather than pretending they
  are complete: Marketplace listing availability, region support, event sharing,
  privilege grant permissions, and compute-pool selector availability.

## Risks To Carry Into Plans

- Marketplace availability and compute-pool families can vary by account/region.
- App installation and activation may need `ACCOUNTADMIN` or equivalent high-privilege
  operator action; Terraform should not silently install or activate the app in this
  AWS-focused repo without an explicit architecture change.
- Granting broad `ALL PRIVILEGES` is shown in examples but should be narrowed in our
  operator runbook to usage, select, future select, and create table where required.
- Future table/view grants may require database roles and may be preview-labeled in some
  docs, so the runbook needs an operator validation checkpoint.
- A "hosted Neo4j" mental model can be misleading: the documented interface is SQL
  procedure execution over Snowflake tables/views, not Cypher over Bolt.

## Validation Architecture

Phase 1 validation is document and source assertion based:

1. The Native App runbook states install path, event sharing, activation, app privileges,
   app roles, database role grants, compute-pool selectors, and app warehouse expectations.
2. The architecture decision states that Snowflake-hosted Neo4j replaces external Neo4j
   for this milestone and that dual external validation is out of scope.
3. The credential model explicitly rejects external `NEO4J_URI`, `NEO4J_USER`, and
   `NEO4J_PASSWORD` for milestone validation.
4. The graph contract document names required columns `nodeId`, `sourceNodeId`, and
   `targetNodeId`, plus proposed MDM node/edge property columns.
5. The plan-review question list surfaces all live-account checks before Phase 2 starts.
