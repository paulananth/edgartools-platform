# Phase 8 Live Dev Run

**Date:** 2026-07-12 UTC  
**Connection:** `snowconn`  
**Database/schema:** `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`  
**Native App:** `NEO4J_GRAPH_ANALYTICS` `V1_0`, patch `32`  
**Platform verdict:** PASS  
**External capability:** `EXPERIMENTAL.LIST_GRAPHS()` blocked inside Marketplace app

## Automated verification

```text
31 passed, 3 warnings in 4.07s
```

The warnings are existing edgartools HTML API deprecations unrelated to Phase 8.

## Live capability results

| Check | Status | Evidence |
| --- | --- | --- |
| App/version | PASS | Installed listing app `V1_0`, patch 32, upgrade state COMPLETE |
| GRAPH_INFO | PASS | Job `job_f8ecb7efdde5407e9ae82821919e137b`, SUCCESS; 15,285 nodes and 1,117 relationships |
| BFS | PASS | Job `job_1484e82e1d344b6ca162b064c98bcb8b`, SUCCESS; current project/compute/write API |
| BFS cleanup | PASS | Unique table `PHASE8_BFS_20260712224724_85291` ownership transferred with REVOKE CURRENT GRANTS and dropped |
| LIST_GRAPHS | EXTERNAL_BLOCKER | Installed `EXPERIMENTAL.LIST_GRAPHS()` fails inside its Python handler on invalid `LIST_FILES` child-job statement |

Machine-readable run artifact was emitted to:

```text
/tmp/neo4j-phase8-20260712224724-85291.tsv
```

## Correct current API

Both GRAPH_INFO and BFS use:

```text
procedure(computePoolSelector, {project, compute, write})
```

GRAPH_INFO requires the graph project plus an empty compute object. BFS requires
`sourceNodeTable`, `sourceNode`, `targetNodesTable`, `targetNodes`, `maxDepth`, and a write
`outputTable`. The installed patch requires `targetNodesTable` even when `targetNodes` is empty.

## LIST_GRAPHS external reproduction

```sql
SELECT *
FROM TABLE(Neo4j_Graph_Analytics.EXPERIMENTAL.LIST_GRAPHS());
```

Result: Snowflake reports a Python interpreter error from the application handler. The nested
Snowpark error says `LIST_FILES` is an invalid child-job statement in this stored-procedure path.
The platform cannot repair Marketplace application internals. The repository now classifies this
optional diagnostic as a named external blocker without mislabeling it as readiness or parity.

## Failure-domain contract

`verify-graph` now reports independent domains:

- `readiness`: installation, roles/grants, compute pool, and graph source availability.
- `parity`: MDM versus graph nodes/edges/endpoints.
- `capability`: GRAPH_INFO, BFS, WCC, and optional LIST_GRAPHS diagnostics.

Overall verification still fails for required readiness, parity, or capability failures.
LIST_GRAPHS remains visible in `external_blockers` but does not make otherwise healthy platform
verification unusable.

