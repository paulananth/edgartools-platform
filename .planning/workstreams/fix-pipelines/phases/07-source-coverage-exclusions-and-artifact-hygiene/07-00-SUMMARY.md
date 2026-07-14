---
phase: 07
plan: 00
subsystem: neo4j-native-app-preflight
tags: [snowflake, neo4j, semantic-parity, graph-registry]
requires: [GVER-01, GVER-02]
provides: [live-native-app-go, zero-state-parity, repeatable-preflight]
affects: [07-01, 07-05, graph-verification]
key-files:
  created:
    - scripts/ops/verify-neo4j-phase7-capabilities.sh
    - tests/integration/test_neo4j_phase7_capabilities.py
    - .planning/workstreams/fix-pipelines/phases/07-source-coverage-exclusions-and-artifact-hygiene/07-NATIVE-APP-PREFLIGHT.md
  modified:
    - edgar_warehouse/mdm/snowflake_graph.py
    - tests/mdm/test_snowflake_graph_migration.py
key-decisions:
  - Stable supported Neo4j operations plus semantic MDM-to-graph parity define health.
  - The platform-owned generation registry defines graph discovery.
  - Experimental LIST_GRAPHS remains informational and non-blocking.
requirements-completed: [RPRE-01]
completed: 2026-07-12
---

# Phase 7 Plan 00: Native App Preflight Summary

The live dev preflight received a human-approved **GO** after proving semantic MDM↔graph parity,
supported graph metadata and BFS traversal, typed date properties, stable A→B generation switching,
platform-registry discovery, and safe output cleanup.

## Results

- Graph contract: 15,285 nodes and 1,117 relationships.
- Semantic verifier: parity, readiness, and capability all `ok`; no missing/extra diagnostics.
- Registered zero states: adviser and fund each explicitly verified as `0 ↔ 0`.
- `GRAPH_INFO`: job `job_f37f86e985de441babfac0d3ece3bb28`, SUCCESS.
- BFS: job `job_39d164a449a54c289a355e40dd64c7da`, SUCCESS at depth 2.
- Experimental `LIST_GRAPHS`: retained as a dated patch-32 external diagnostic.
- Cleanup: unique BFS output dropped; canonical graph objects unchanged.
- Tests: 16 targeted integration and graph-migration tests passed.

## Deviations from Plan

**[Rule 1 - Bug] Zero-count registered entity types disappeared from parity rows.** During the
first live rerun, adviser and fund matched at zero but the query omitted them because it started
from entity rows. The verifier now starts from the active entity-type registry and left-joins
non-quarantined entities, producing explicit fail-closed zero rows. Regression coverage was added.

**[Rule 1 - Bug] Runner used legacy API and result predicates.** The runner was updated to the
current Neo4j project/compute/write API and now evaluates semantic failure domains rather than a
legacy WCC-specific JSON fragment.

## Verification

```text
uv run pytest tests/integration/test_neo4j_phase7_capabilities.py \
  tests/mdm/test_snowflake_graph_migration.py -q

16 passed
```

Live evidence is recorded in `07-NATIVE-APP-PREFLIGHT.md` and the machine-readable run ledger at
`/tmp/neo4j-phase7-preflight-20260712233410-87169.tsv`.

## Self-Check: PASSED

RPRE-01 is complete. Plan 07-01 may begin when Phase 6 ownership/dependency coordination permits.
