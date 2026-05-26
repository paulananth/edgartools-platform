# Neo4j Graph Analytics Native App Runbook

## Purpose

This runbook gives an operator the account checks needed before EdgarTools implementation
phases depend on Neo4j Graph Analytics for Snowflake.

The target is the Snowflake Marketplace Neo4j Graph Analytics Native App installed under
the documented default application name `Neo4j_Graph_Analytics`. It replaces the external
Neo4j validation target for this milestone. It is not an Azure deployment, external
Container Apps runtime, Bolt endpoint swap, or a continuation of external `NEO4J_URI`,
`NEO4J_USER`, or `NEO4J_PASSWORD` credential flow.

All Phase 1 output remains under `.planning/workstreams/neo4j-snowflake/`. This runbook
does not instruct operators to edit sibling workstreams, source code, Terraform state,
generated application JSON, or non-AWS deployment paths.

## Preconditions

- A Snowflake account and region where the Marketplace listing for Neo4j Graph Analytics
  for Snowflake is available.
- A high-privilege Snowflake operator role, usually `ACCOUNTADMIN` or a delegated role
  that can install Native Apps, grant application privileges, create consumer roles, and
  grant access to the target database/schema objects.
- Operator acknowledgement that event sharing is required during installation and that
  app telemetry/log events may be shared according to the listing and Snowflake Native App
  event sharing controls.
- A proposed graph input schema for later phases, currently
  `EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH`, with graph-ready node and edge tables or views.
- A governed write schema where app-created algorithm output tables may be created and
  cleaned up by operator policy.

Do not store live Snowflake passwords, private keys, OAuth tokens, EDGAR identity values,
or application secrets in this planning directory.

## Marketplace Install And Activation

1. In Snowsight, open the Snowflake Marketplace listing for Neo4j Graph Analytics for
   Snowflake.
2. Install the Native App using the default application name `Neo4j_Graph_Analytics`
   unless an operator records a different name in the phase decision log.
3. Enable event sharing when prompted. The Neo4j getting-started documentation identifies
   event sharing as required for installation.
4. Open `Data Products -> Apps -> Neo4j Graph Analytics -> Privileges`.
5. Grant the required application privileges listed in the next section.
6. Click `Activate` from the same app page. Activation triggers app-managed internal
   resources, including compute pools.
7. Confirm the app is visible and active:

```sql
SHOW APPLICATIONS LIKE 'Neo4j_Graph_Analytics';
SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION Neo4j_Graph_Analytics;
```

If event sharing was disabled after installation, re-enable it only after the operator
reviews the event definitions:

```sql
ALTER APPLICATION Neo4j_Graph_Analytics SET AUTHORIZE_TELEMETRY_EVENT_SHARING = true;
```

Optional event types, such as broad `SNOWFLAKE$ALL` sharing, require explicit operator
approval before use in this platform.

## Required Application Privileges

The app requires these Snowflake application privileges before activation can create the
expected internal resources:

- `CREATE COMPUTE POOL`
- `CREATE WAREHOUSE`

Snowflake Native Apps with Snowpark Container Services require consumer-granted
privileges before the app can create services or compute pools in the consumer account.
Snowflake's app guidance recommends a single validation or setup procedure pattern that
checks whether required privileges were granted before creating resources.

Validate grants from Snowsight where possible:

```text
Data Products -> Apps -> Neo4j Graph Analytics -> Privileges -> Grant
```

If SQL-based validation is needed, inspect app privileges through Snowflake account
metadata with the operator role rather than adding broad grants. This platform must not
copy example grants such as `ALL PRIVILEGES` into production. Any broad example grant in
upstream documentation must be narrowed to the explicit privileges required here or
approved in a separate operator review.

## Consumer Roles

Create two consumer roles so ordinary users can execute algorithms without app
administration rights.

```sql
USE ROLE <privileged_role>;

CREATE ROLE IF NOT EXISTS EDGARTOOLS_GRAPH_APP_USER;
GRANT APPLICATION ROLE Neo4j_Graph_Analytics.app_user
  TO ROLE EDGARTOOLS_GRAPH_APP_USER;

CREATE ROLE IF NOT EXISTS EDGARTOOLS_GRAPH_APP_ADMIN;
GRANT APPLICATION ROLE Neo4j_Graph_Analytics.app_admin
  TO ROLE EDGARTOOLS_GRAPH_APP_ADMIN;
```

Role intent:

- `Neo4j_Graph_Analytics.app_user`: run graph algorithm procedures and utility functions.
- `Neo4j_Graph_Analytics.app_admin`: administer the app warehouse and monitor or operate
  app compute pools.

Grant `EDGARTOOLS_GRAPH_APP_USER` to the deployer/operator identities that run validation
queries. Grant `EDGARTOOLS_GRAPH_APP_ADMIN` only to Snowflake platform operators who need
to inspect compute pools or the app warehouse.

## Data Access Grants

The app reads graph projection inputs from Snowflake tables or views and writes algorithm
outputs back to Snowflake tables. Later implementation phases should expose graph-ready
views or tables with the Native App contract:

- Node input rows include `nodeId`.
- Relationship input rows include `sourceNodeId` and `targetNodeId`.
- Additional columns become node or relationship properties.
- Views can adapt existing EdgarTools column names into the required Native App names.

Use database roles to bind the minimum graph schema privileges to the application:

```sql
USE ROLE <privileged_role>;
USE DATABASE EDGARTOOLS_<ENV>;

CREATE DATABASE ROLE IF NOT EXISTS EDGARTOOLS_GRAPH_APP_DATA;

GRANT USAGE ON DATABASE EDGARTOOLS_<ENV>
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;
GRANT USAGE ON SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;

GRANT SELECT ON ALL TABLES IN SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;
GRANT SELECT ON ALL VIEWS IN SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;
GRANT SELECT ON FUTURE TABLES IN SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;

GRANT CREATE TABLE ON SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA;

GRANT DATABASE ROLE EDGARTOOLS_GRAPH_APP_DATA
  TO APPLICATION Neo4j_Graph_Analytics;
```

Grant read access to result tables for the consumer user role without transferring
ownership by default:

```sql
GRANT USAGE ON DATABASE EDGARTOOLS_<ENV>
  TO ROLE EDGARTOOLS_GRAPH_APP_USER;
GRANT USAGE ON SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO ROLE EDGARTOOLS_GRAPH_APP_USER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
  TO ROLE EDGARTOOLS_GRAPH_APP_USER;
```

Do not grant ownership on future app output tables unless an operator explicitly accepts
that the consumer role can drop those tables.

## Compute Pools And Warehouse

The application creates compute pools automatically during activation. Neo4j documents
compute pool selectors such as `CPU_X64_XS`; selector availability depends on the
underlying Snowflake instance family support in the consumer region.

Validate available selectors:

```sql
CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();
```

For the first low-cost validation, use `CPU_X64_XS` unless the account reports that the
selector is unavailable.

Algorithms run as Snowpark Container Services job services inside app-managed compute
pools. Default pool behavior is run-on-demand oriented: pools start for a job, stop job
services after completion, and suspend when no jobs are running. Before implementation
phases assume availability, an operator must check pool state and account quotas.

The application also creates an app warehouse named after the application. With the
default application name, expect:

```text
Neo4j_Graph_Analytics_app_warehouse
```

The `Neo4j_Graph_Analytics.app_admin` role is the narrow app role for administering the
query warehouse and monitoring or operating compute pools.

## Live Account Validation

Run these checks in a non-production or approved Snowflake account before Phase 2 depends
on the app path.

1. Confirm installation and activation:

```sql
SHOW APPLICATIONS LIKE 'Neo4j_Graph_Analytics';
SHOW TELEMETRY EVENT DEFINITIONS IN APPLICATION Neo4j_Graph_Analytics;
```

2. Confirm application roles can be granted to consumer roles:

```sql
USE ROLE EDGARTOOLS_GRAPH_APP_USER;
USE DATABASE Neo4j_Graph_Analytics;
```

3. Confirm compute pool selector availability:

```sql
CALL Neo4j_Graph_Analytics.graph.show_available_compute_pools();
```

Expected result: `CPU_X64_XS` is present, or the operator records the supported replacement
selector for this account and region.

4. Confirm graph input tables or views expose required columns:

```sql
DESC TABLE EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_NODES;
DESC TABLE EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_EDGES;
```

Expected result: nodes contain `nodeId`; edges contain `sourceNodeId` and `targetNodeId`.
If these are views rather than tables, use `DESC VIEW`.

5. Run a bounded WCC smoke test against a small graph fixture or sample MDM graph views:

```sql
CALL Neo4j_Graph_Analytics.graph.wcc('CPU_X64_XS', {
  'project': {
    'defaultTablePrefix': 'EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH',
    'nodeTables': ['MDM_GRAPH_NODES'],
    'relationshipTables': {
      'MDM_GRAPH_EDGES': {
        'sourceTable': 'MDM_GRAPH_NODES',
        'targetTable': 'MDM_GRAPH_NODES',
        'orientation': 'NATURAL'
      }
    }
  },
  'compute': { 'consecutiveIds': true },
  'write': [{
    'nodeLabel': 'MDM_GRAPH_NODES',
    'outputTable': 'EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_WCC_SMOKE'
  }]
});
```

6. Inspect app-created output:

```sql
SELECT COUNT(*) AS node_count
FROM EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_WCC_SMOKE;
```

7. Capture job logs only for troubleshooting. Do not copy log output containing sensitive
   data into planning docs:

```sql
CALL Neo4j_Graph_Analytics.graph.job_log('<job_id>');
```

## Failure Modes

| Symptom | Likely cause | Operator response |
| --- | --- | --- |
| Marketplace listing unavailable | Unsupported account, cloud, or region | Stop Phase 2 planning for this account and record listing/region evidence. |
| Install blocks on event sharing | Mandatory app event sharing not enabled | Review event definitions, approve required event sharing, and retry installation. |
| Activation fails | Missing `CREATE COMPUTE POOL` or `CREATE WAREHOUSE` | Grant only the missing application privilege, then activate again. |
| `CPU_X64_XS` missing | Instance family unavailable in region | Record supported selector from `show_available_compute_pools()` and update later plan inputs. |
| Algorithm cannot read graph inputs | Missing database/schema/table/view privileges | Re-check database role grants to the application and avoid broadening beyond usage/select. |
| Algorithm cannot write output | Missing `CREATE TABLE` on output schema | Grant `CREATE TABLE` on the governed graph output schema only. |
| Consumer cannot inspect output | Consumer role lacks future table select | Grant `SELECT ON FUTURE TABLES` in the output schema to `EDGARTOOLS_GRAPH_APP_USER`. |
| Compute cost or pool stays active | Long-running job, concurrent jobs, or pool setting mismatch | Use `app_admin` to inspect pool state and suspend/resize under operator policy. |
| Logs expose sensitive values | Query or properties included sensitive data | Redact logs before sharing and adjust validation fixtures to avoid secrets. |

## Sources

- Neo4j Graph Analytics for Snowflake getting started:
  https://neo4j.com/docs/snowflake-graph-analytics/current/getting-started/
- Neo4j Graph Analytics for Snowflake administration:
  https://neo4j.com/docs/snowflake-graph-analytics/current/administration/
- Snowflake Native Apps with Snowpark Container Services:
  https://docs.snowflake.com/en/developer-guide/native-apps/container-services
- Snowflake developer guide, practical graph analytics with Neo4j:
  https://www.snowflake.com/en/developers/guides/practical-graph-analytics-neo4j-snowflake/

