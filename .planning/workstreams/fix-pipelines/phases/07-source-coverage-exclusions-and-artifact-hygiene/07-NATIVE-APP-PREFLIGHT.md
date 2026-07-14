# Phase 7 Native App Capability Preflight

**Date:** 2026-07-12 UTC  
**Environment:** dev  
**Snowflake connection:** `snowconn`  
**Database/schema:** `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`  
**Native App:** `NEO4J_GRAPH_ANALYTICS`, listing version `V1_0`, patch `32`  
**Results:** `/tmp/neo4j-phase7-preflight-20260712233410-87169.tsv`  
**Verdict:** **GO — all required RPRE-01 capabilities passed**

## Safety And Ownership

- No `edgartools-dev-load-history` Step Functions execution was running before the probe.
- No canonical graph object was modified.
- Date, registry, and A→B switching probes used session-scoped temporary objects.
- BFS wrote only uniquely named `PHASE7_BFS_20260712233410_87169`.
- Cleanup transferred that output to `ACCOUNTADMIN` with current grants revoked, then dropped it.

## Capability Matrix

| Capability | Result | Evidence |
| --- | --- | --- |
| Native App installation | PASS | `V1_0`, patch 32, upgrade state `COMPLETE` |
| Compute selector | PASS | `GRAPH.SHOW_AVAILABLE_COMPUTE_POOLS()` returned `CPU_X64_XS` |
| Contract views | PASS | `GRAPH_APP_NODES=15,285`; `GRAPH_APP_EDGES=1,117` |
| Semantic MDM↔graph parity | PASS | `mdm verify-graph` exited 0; parity/readiness/capability all `ok`; missing/extra node, edge, and endpoint diagnostics empty |
| Explicit zero states | PASS | adviser and fund named checks each emitted present `0 ↔ 0` parity rows |
| `GRAPH_INFO` | PASS | Job `job_f37f86e985de441babfac0d3ece3bb28` succeeded with 15,285 nodes and 1,117 relationships |
| BFS / bounded multi-hop | PASS | Job `job_39d164a449a54c289a355e40dd64c7da` succeeded with `maxDepth=2` |
| Typed dates | PASS | Temporary edge contract used typed `VALID_FROM_DATE` and `VALID_TO_DATE`; Snowflake returned `DATE` |
| Stable generation switch | PASS | The same consumer view returned `GEN_A`, switched, then returned `GEN_B` |
| Platform registry discovery | PASS | Temporary registry lookup returned the one `ACTIVE` generation, `GEN_B` |
| `LIST_GRAPHS` | EXTERNAL_BLOCKER, informational | Patch-32 experimental handler still fails internally on invalid `LIST_FILES`; it is not a health authority |
| Cleanup | PASS | BFS output dropped; temporary session objects expired; canonical objects unchanged |

## Commands

Complete preflight:

```bash
SNOW_CONNECTION=snowconn \
PHASE7_PREFLIGHT_RESULTS_DIR=/tmp \
bash scripts/ops/verify-neo4j-phase7-capabilities.sh
```

Semantic health authority:

```bash
SNOWFLAKE_CONNECTION=snowconn \
DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV \
uv run --extra snowflake edgar-warehouse mdm verify-graph
```

Supported Native App calls use the current sectioned API:

```sql
CALL Neo4j_Graph_Analytics.GRAPH.GRAPH_INFO(
  'CPU_X64_XS',
  {'project': {...}, 'compute': {}}
);

CALL Neo4j_Graph_Analytics.GRAPH.BFS(
  'CPU_X64_XS',
  {
    'project': {...},
    'compute': {
      'sourceNodeTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
      'sourceNode': '0002656c-34b6-4063-9590-2c433e66cd17',
      'targetNodesTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.GRAPH_APP_NODES',
      'targetNodes': [],
      'maxDepth': 2
    },
    'write': [{'outputTable': 'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION.PHASE7_BFS_20260712233410_87169'}]
  }
);
```

Informational external reproduction:

```sql
SELECT *
FROM TABLE(Neo4j_Graph_Analytics.EXPERIMENTAL.LIST_GRAPHS());
```

Patch 32 raises an application-internal Snowpark exception because `LIST_FILES` is not valid as a
child job from a stored procedure in a `FROM` clause. This remains visible but non-blocking under
the user-approved Phase 8 operating contract.

## Deviation Resolved During Execution

The first post-Phase-8 run found a false parity failure for zero-count adviser and fund entity
types. `_render_verify_node_counts` started from entity rows, so registered types with no rows
vanished instead of emitting explicit zero counts. The verifier now starts from the active entity
type registry and left-joins non-quarantined entities. The final run proved both types as present
`0 ↔ 0` rows without weakening named checks.

## Gate Decision

RPRE-01's automated evidence is complete and the verdict is **GO**. Stable documented operations
plus semantic MDM↔graph parity define health; the platform-owned generation registry defines
discovery; experimental inventory APIs are diagnostic only. Plan 07-01 may begin after the required
human review checkpoint approves this ledger.
