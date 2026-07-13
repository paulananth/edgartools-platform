# Phase 8 Native App/API Compatibility — Consolidated Findings

**Captured:** 2026-07-12  
**Environment:** Snowflake dev  
**Connection:** `SNOW_CONNECTION=snowconn`  
**Scope:** Read-only/native-app smoke investigation plus temporary or uniquely named smoke output  
**Status:** GRAPH_INFO and BFS compatibility resolved experimentally; LIST_GRAPHS remains an external Native App blocker; platform changes are still uncommitted and require main-thread verification.

## Executive Summary

The primary GRAPH_INFO and BFS failures were caused by obsolete repository call shapes, not missing
Native App capabilities. The current Neo4j Graph Analytics for Snowflake API takes the compute-pool
selector as the first argument and a sectioned `project` / `compute` / `write` object as the second.
After using that contract, GRAPH_INFO and BFS both succeeded live against the existing EdgarTools
graph projection.

`LIST_GRAPHS` is different. The installed procedure exists only in the application's
`EXPERIMENTAL` schema, and a correctly located call fails inside the Marketplace application's
Python handler. That is an external application defect, not a repository SQL naming problem.

The platform verifier also needs to distinguish three independent failure domains:

1. **Readiness:** application installation, roles, grants, compute pools, and readable graph input.
2. **Parity:** MDM versus Snowflake graph node/edge identity and endpoint mismatches.
3. **Capability:** Native App jobs such as GRAPH_INFO, BFS, WCC, and optional LIST_GRAPHS.

## Installed Native App

Live `SHOW APPLICATIONS` evidence:

- Application: `NEO4J_GRAPH_ANALYTICS`
- Listing version: `V1_0`
- Installed patch: `32`
- Upgrade state: complete
- Available compute selector includes `CPU_X64_XS`

The current public Neo4j changelog lists patch `1.0.33`. Its published changes concern estimation
schema promotion and visualization removal; no advertised fix was found for GRAPH_INFO, BFS, or
LIST_GRAPHS.

Official references consulted:

- <https://neo4j.com/docs/snowflake-graph-analytics/current/reference/>
- <https://neo4j.com/docs/snowflake-graph-analytics/current/algorithms/bfs/>
- <https://neo4j.com/docs/snowflake-graph-analytics/current/jobs/>
- <https://neo4j.com/docs/snowflake-graph-analytics/current/changelog/>

## Existing Graph Contract

The live contract views were readable:

| Object | Count |
| --- | ---: |
| `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES` | 15,285 |
| `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_EDGES` | 1,117 |

The graph uses string node identifiers and directed relationships. A live GRAPH_INFO result
reported density `4.781351820428006e-06`, 15,285 nodes, and 1,117 relationships.

## Current API Contract

The correct family of calls is:

```sql
CALL Neo4j_Graph_Analytics.GRAPH.<PROCEDURE>(
  'CPU_X64_XS',
  {
    'project': {
      'nodeTables': ['<fully-qualified-node-view>'],
      'relationshipTables': {
        '<fully-qualified-edge-view>': {
          'sourceTable': '<fully-qualified-node-view>',
          'targetTable': '<fully-qualified-node-view>',
          'orientation': 'NATURAL'
        }
      }
    },
    'compute': {...},
    'write': [...]
  }
);
```

The obsolete repository shape used a graph-name first argument and snake_case configuration keys
such as `project_name`, `compute_pool`, `node_tables`, `relationship_tables`, `source_node_id`,
`max_depth`, and `write_options`. Patch 32 rejects those keys.

## GRAPH_INFO

### Failed shapes

- Old graph-name-first call: rejected root keys `compute_pool`, `node_tables`, and
  `relationship_tables`.
- Current sectioned call with `compute.consecutiveIds`: rejected because GRAPH_INFO does not allow
  `consecutiveIds` in its compute configuration.

### Working live shape

```sql
CALL Neo4j_Graph_Analytics.GRAPH.GRAPH_INFO(
  'CPU_X64_XS',
  {
    'project': {
      'nodeTables': [
        'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES'
      ],
      'relationshipTables': {
        'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_EDGES': {
          'sourceTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
          'targetTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
          'orientation': 'NATURAL'
        }
      }
    },
    'compute': {}
  }
);
```

Live result:

- Job ID: `job_13611721ef3a485da7675b9881d135ac`
- Status: `SUCCESS`
- Graph projection: 15,285 nodes and 1,117 relationships
- Job compute interval: approximately four seconds

## BFS

Official current BFS documentation requires:

- `compute.sourceNodeTable`
- `compute.sourceNode`
- `compute.targetNodesTable`
- `compute.targetNodes`
- optional `compute.maxDepth`
- `write[{'outputTable': ...}]`

The documentation describes `targetNodesTable` as conditionally required, but installed patch 32
returned `No value specified for the mandatory configuration parameter targetNodesTable` when it
was omitted even though no targets were requested. Supplying the node view and an empty
`targetNodes` list succeeded.

### Working live shape

```sql
CALL Neo4j_Graph_Analytics.GRAPH.BFS(
  'CPU_X64_XS',
  {
    'project': {
      'nodeTables': [
        'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES'
      ],
      'relationshipTables': {
        'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_EDGES': {
          'sourceTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
          'targetTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
          'orientation': 'NATURAL'
        }
      }
    },
    'compute': {
      'sourceNodeTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
      'sourceNode': '0002656c-34b6-4063-9590-2c433e66cd17',
      'targetNodesTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
      'targetNodes': [],
      'maxDepth': 2
    },
    'write': [{
      'outputTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.PHASE8_BFS_20260712'
    }]
  }
);
```

Live result:

- Job ID: `job_5ba39f41164a4620be439fe86c1a51d2`
- Status: `SUCCESS`
- Projected nodes: 15,285
- Projected relationships: 1,117
- BFS compute time: 18 ms
- Rows written: 0 for the selected source/depth fixture

Zero written rows do not invalidate the API compatibility proof: the Native App projected the
graph, executed BFS successfully, and completed its governed write stage.

## LIST_GRAPHS

Installed procedure inventory:

```text
EXPERIMENTAL.LIST_GRAPHS()
  RETURN TABLE (GRAPHNAME VARCHAR, BYTES NUMBER, CREATED_AT VARCHAR)
```

No `GRAPH.LIST_GRAPHS` procedure exists. The exact installed call is:

```sql
SELECT *
FROM TABLE(Neo4j_Graph_Analytics.EXPERIMENTAL.LIST_GRAPHS());
```

Live result: failure inside the Native App Python handler. The handler attempted an invalid
`LIST_FILES` child-job statement from a stored procedure used in a `FROM` clause.

Classification: **external Native App blocker**. The repository cannot safely repair Marketplace
application internals. Phase 8 requirement GVER-02 explicitly permits dated reproduction evidence
for an app-side blocker.

The current public operations reference does not list LIST_GRAPHS as a stable graph or
administrative endpoint. It lists GRAPH_INFO and algorithm/admin operations, while LIST_GRAPHS
remains experimental in the installed application.

## Strict Verifier Finding

A live `mdm verify-graph` run initially failed before clean Native App proof because named node
parity rows were absent or incomplete even though missing/extra diagnostics were empty. Required
environment variables included:

```bash
SNOW_CONNECTION=snowconn
SNOWFLAKE_CONNECTION=snowconn
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV
```

This demonstrated why a single overall `failed` status is insufficient. A graph parity/readiness
problem can prevent capability proof, and operators need to see the failure domains independently.

Recommended payload additions:

```text
failure_domains: [readiness | parity | capability]
failure_summary:
  readiness: ok|failed|skipped
  parity: ok|failed
  capability: ok|failed|skipped
```

LIST_GRAPHS may be reported as a non-blocking `external_blocker` for Phase 8 because it is not a
stable documented endpoint and GVER-02 allows documented external failure. GRAPH_INFO, BFS, and WCC
remain blocking platform capability checks.

## Job Result Handling

Snowflake SQL execution can return exit code zero while the Native App result contains
`JOB_STATUS=ERROR`. Platform verification must inspect result-row values, including dictionary
rows returned by tests/connectors, and fail the capability check when `ERROR` is present.

## Temporary Output Cleanup

The BFS output table was application-owned. A direct `DROP TABLE` by ACCOUNTADMIN failed because
the application owned the object. Cleanup required:

```sql
GRANT OWNERSHIP
ON TABLE EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.PHASE8_BFS_20260712
TO ROLE ACCOUNTADMIN
REVOKE CURRENT GRANTS;

DROP TABLE EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.PHASE8_BFS_20260712;
```

Both statements succeeded. Future live runners must include this ownership-transfer cleanup for
application-created smoke output, including failure paths. `COPY CURRENT GRANTS` cannot be used
when the object is application-owned.

## Automated Verification Observed

After the Phase 8 renderer and failure-domain changes, the focused graph suite reported:

```text
29 passed, 3 deprecation warnings
```

Covered behavior included:

- Current GRAPH_INFO/BFS sectioned SQL rendering
- Required BFS target-node fields
- Correct `EXPERIMENTAL.LIST_GRAPHS()` location
- Readiness-only failure classification
- Capability-only failure classification
- Non-blocking LIST_GRAPHS external-blocker classification
- Dictionary and tuple Native App job-result handling

These changes remain uncommitted in the shared worktree and must be rechecked by the main thread
before any summary, requirement completion, or Phase 8 closure is recorded.

## Phase 7 Impact

Phase 7's `RPRE-01` gate currently requires LIST_GRAPHS to pass. Phase 8 can close GVER-02 with
LIST_GRAPHS documented as an external blocker, but Phase 7 cannot silently weaken its separately
approved gate.

After Phase 8 verification, the user must choose one of two paths:

1. Keep LIST_GRAPHS mandatory and leave Phase 7 blocked pending an upstream Native App fix.
2. Revise RPRE-01 to require stable documented capabilities only (GRAPH_INFO, BFS/multi-hop, WCC,
   contract loading, typed dates, and generation switching), while retaining LIST_GRAPHS as a
   monitored external diagnostic blocker.

Recommendation: use path 2 because generation-based MDM/Neo4j serving does not depend on the
experimental LIST_GRAPHS handler, while GRAPH_INFO and BFS directly prove projection and traversal.

## Remaining Work

- Re-run focused tests after any main-thread edits.
- Add a Phase 8 live runner with unique output names and application-owned cleanup.
- Run corrected `mdm verify-graph` with complete parity inputs.
- Capture the final Phase 8 live artifact and verification ledger.
- Obtain explicit user approval before changing Phase 7's LIST_GRAPHS gate.
- Do not mark GVER-01/GVER-02 or Phase 8 complete until main-thread verification is finished.

