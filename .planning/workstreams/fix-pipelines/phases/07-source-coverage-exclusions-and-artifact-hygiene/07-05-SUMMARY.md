---
phase: 07
plan: 05
subsystem: snowflake-graph-generations
tags: [mdm, snowflake, neo4j, generation-activation, temporal-queries, entity-merge]
requires: [07-01, 07-02, 07-04]
provides: [additive-graph-generations, single-activation-pointer, exact-parity-verification, strict-temporal-traversal, canonical-merge-remap]
affects: [dashboard_readonly, api/routers/graph.py]
key-files:
  created:
    - tests/mdm/test_temporal_graph_queries.py
  modified:
    - edgar_warehouse/mdm/snowflake_graph.py
    - edgar_warehouse/mdm/cli.py
    - edgar_warehouse/mdm/api/routers/graph.py
    - edgar_warehouse/mdm/api/schemas/graph.py
    - tests/mdm/test_snowflake_graph_migration.py
    - tests/mdm/test_cli_snowflake_graph.py
    - tests/mdm/test_api.py
    - .planning/workstreams/fix-pipelines/REQUIREMENTS.md
key-decisions:
  - render_graph_tables moves from CREATE OR REPLACE TABLE (full blind replace)
    to additive GENERATION_ID-tagged rows: CREATE TABLE IF NOT EXISTS +
    generation-scoped DELETE+INSERT. This directly contradicted the pre-existing
    test_graph_sync_is_idempotent_full_rebuild's premise (asserted CREATE OR
    REPLACE / no INSERT-MERGE-UPDATE-DELETE) -- that test's premise was the
    architecture this plan intentionally supersedes, so it was rewritten to
    assert the new (still real) idempotency contract: repeated syncs of the
    SAME generation_id are byte-identical, and DELETE/INSERT are always scoped
    to that one generation_id so two different generations' rows never collide.
  - All stable GRAPH_APP_*/GRAPH_NODE_*/GRAPH_EDGE_* view NAMES are unchanged
    (Native App consumers see no breaking change) -- only their definitions
    changed, to join through one new GRAPH_ACTIVE_POINTER row
    (`WHERE GENERATION_ID = (SELECT ACTIVE_GENERATION_ID FROM ... WHERE
    POINTER_ID = 'active')`), so node and edge rows can never resolve to two
    different generations.
  - Exact identity/property parity uses Snowflake's HASH_AGG (order-independent
    aggregate hash) over MDM source rows vs. the newly-staged generation's rows.
    A matching row COUNT with even one different NODEID/EDGEID/property flips
    the hash and fails verification -- something the pre-existing count-only
    parity checks structurally cannot catch.
  - verify() is what promotes a generation from 'building' to 'verified' (or
    demotes it to 'failed' with reasons recorded) -- but only when called with
    an explicit generation_id (a candidate awaiting activation), never when
    verifying the default active generation (already 'activated', not a
    'building' candidate). Without this, activate_graph_generation's
    status=='verified' guard would have nothing that ever sets that status.
  - Entity-merge canonical remap is bounded (5 SQL join hops on the Snowflake
    side; 10-hop Python chain-following on the FastAPI side) rather than a true
    unbounded recursive resolution -- a pragmatic scope choice, generous enough
    for realistic merge-chain depths.
  - as_of_date traversal queries intentionally drop the is_active filter (using
    quarantined == False instead) so a since-superseded relationship version is
    still found when it was the version actually valid at that past date; the
    no-as_of "current" default is unchanged (is_active == True only). Caught
    and fixed during this plan -- the first draft still filtered is_active,
    which would have silently broken genuinely historical (pre-supersession)
    queries.
requirements-completed: [RSYNC-02, RSYNC-05, RTEMP-01, RTEMP-02, RLINE-01]
requirements-partially-addressed: [RSYNC-01]
completed: 2026-07-14
---

# Phase 7 Plan 05: One Verified Generation As The Only Consumer-Visible Relationship State

## Results

**Task 1 (additive generation schema + single active pointer):**
- New Snowflake tables: `GRAPH_GENERATION` (platform-owned discovery/lifecycle registry:
  `STATUS` `building`/`verified`/`activated`/`retired`/`failed`, `RULE_VERSION`,
  `SCHEMA_VERSION`, counts, timestamps, `FAILURE_REASONS`) and `GRAPH_ACTIVE_POINTER`
  (the one guarded row every stable view joins against).
- `MDM_GRAPH_NODES`/`MDM_GRAPH_EDGES` gain a `GENERATION_ID` column and become
  additive (`CREATE TABLE IF NOT EXISTS` + generation-scoped `DELETE`+`INSERT`,
  never `CREATE OR REPLACE`). Edges gain `RELATIONSHIP_ID`, `VALID_FROM_DATE`,
  `VALID_TO_DATE`, `DATE_PROVENANCE`, `RELATIONSHIP_KIND` (closing RTEMP-01's
  flagged gap) and canonical + original endpoint columns (`SOURCENODEID`/
  `TARGETNODEID` canonical, `SOURCENODEID_ORIGINAL`/`TARGETNODEID_ORIGINAL` raw),
  resolved via a new `GRAPH_ENTITY_MERGE_LINEAGE` view over `MDM_CHANGE_LOG`'s
  `merged_from` records (bounded 5-hop chain).
- Every `GRAPH_APP_*`/`GRAPH_NODE_*`/`GRAPH_EDGE_*`/count view now filters by the
  active-generation subquery; names unchanged for Native App compatibility.
- All six live-`verify_graph:*` render functions (`_render_verify_node_counts`,
  `..._relationship_counts`, `_render_missing/extra_nodes/edges`,
  `_render_missing_edge_endpoints`) gained an optional `generation_id` parameter
  (default `None` = verify the active generation, preserving pre-07-05 behavior)
  so a candidate generation can be verified before activation.
- `SnowflakeGraphSyncConfig.generation_id` is now required at `sync()` time
  (correlates MDM's own generation_id, 07-04, with the Snowflake staging tag).
  `mdm sync-graph --generation-id` is optional (defaults to a fresh UUID for
  standalone runs) — publishing alone never activates it.

**Task 2 (exact verification + guarded activation/rollback/retention):**
- `_render_exact_node_parity`/`_render_exact_relationship_parity`: `HASH_AGG`-based
  identity+property parity (nodes: id/type/label; edges: instance+relationship id,
  original endpoints, type, typed temporal fields) plus `_render_canonical_remap_leaks`
  (a discarded entity_id must never appear as a staged edge's canonical endpoint).
  All three wired into `SnowflakeGraphVerifier.verify()`'s `passed`/`parity_ok`.
- `verify()` now promotes an explicitly-verified candidate generation from
  `'building'` to `'verified'` (or demotes to `'failed'`) — the only status
  `activate_graph_generation` accepts.
- `activate_graph_generation`/`rollback_graph_generation`/`cleanup_retired_generations`
  (+ `mdm graph-activate`/`graph-rollback`/`graph-cleanup-generations` CLI commands):
  guard strictly before any pointer-mutating SQL executes (rejected activation/rollback
  leaves the previous pointer's SQL completely unissued); retention keeps the newest
  3 retired generations (always including the immediate predecessor) plus every
  generation from the last 30 days.

**Task 3 (strict temporal + canonical-remap query contracts):**
- `api/routers/graph.py`'s `neighborhood`/`traversal`: strict `as_of_date` on
  `valid_from_date`/`valid_to_date`/`date_provenance` (half-open, inclusive start/
  exclusive end); `date_provenance == 'unknown'` excluded by default, included +
  labeled `date_uncertain: true` via `include_unknown_dates=True`; historical queries
  (`as_of` given) intentionally see superseded (`is_active=False`) versions, since a
  past `as_of_date` can legitimately mean "whatever was valid then."
- Canonical entity-merge remap: `_canonical_groups`/`_canonicalize` resolve
  `mdm_change_log`'s `merged_from` lineage (bounded 10-hop); traversal/adjacency
  converges on the canonical id while `GraphNode.merged_from` and
  `GraphEdge.source_entity_id_original`/`target_entity_id_original` preserve
  the original identity.

## Deviations from Plan

**[Rule 1 - Bug, caught during Task 1] The pre-existing idempotency test's premise
was the architecture this plan replaces.** `test_graph_sync_is_idempotent_full_rebuild`
asserted `CREATE OR REPLACE TABLE` and forbade `INSERT`/`MERGE`/`UPDATE`/`DELETE` — a
direct contradiction with Task 1's explicit action ("Replace in-place `CREATE OR
REPLACE TABLE` publication with additive generation... tables"). Not a regression to
preserve; rewrote it to assert the new, still-real idempotency contract (same
generation_id syncs byte-identically; different generation_ids' DELETE/INSERT never
overlap), plus a new test proving two different generations never collide.

**[Rule 1 - Bug, caught during Task 2] `activate_graph_generation`'s `status ==
'verified'` guard had nothing that ever set that status.** 07-04's MDM-side
`fan_in_generation` only touches `mdm_graph_generation` (Postgres); the Snowflake-side
`GRAPH_GENERATION.STATUS` this plan added starts at `'building'` and nothing flipped it
to `'verified'`. Fixed by having `SnowflakeGraphVerifier.verify()` itself promote
(or demote to `'failed'`) an explicitly-named candidate generation, closing the loop:
plan → sync → verify (promotes) → activate (only accepts `'verified'`).

**[Rule 1 - Bug, caught during Task 3] First draft of strict `as_of_date` filtering
still filtered `is_active == True`, silently defeating genuinely historical queries.**
A since-superseded relationship version is exactly what "true at a past `as_of_date`"
can mean; filtering to only the currently-active version would make a historical query
see whatever happens to be current today. Fixed by dropping the `is_active` filter when
`as_of` is supplied (filtering `quarantined == False` instead) and keeping it for the
no-`as_of` "current" default. Added 3 regression tests covering superseded-version
lookup, current-version lookup, and current-default non-leakage.

**[Rule 3 - Scope] `RSYNC-01` and part of `RSYNC-02`'s "coverage-level... for every
type" are marked partial/caveated, not complete.** MDM's own FastAPI serving reads have
no generation-pinning concept at all (they read live current Postgres state); this is
architecturally reasonable (MDM leads, Neo4j follows on a verified lag) but isn't
literally the symmetric "same verified active generation on both sides" the requirement
describes. Similarly, coverage-exhaustive verification only activates when a caller
supplies a `relationship_coverage` manifest to `SnowflakeGraphVerificationConfig` — the
live `mdm verify-graph` CLI invocation doesn't default to building/passing one yet (a
pre-existing gap noted in 07-02's summary, not this plan's to close). Corrected in
REQUIREMENTS.md rather than repeating the overclaim pattern this workstream has caught
twice already (07-01's original summary).

## Verification

```text
uv run pytest "tests/mdm/test_snowflake_graph_migration.py" -k 'generation or view or temporal' -q
8 passed

uv run pytest tests/mdm/test_snowflake_graph_migration.py -k 'parity or activation or rollback or retention' -q
12 passed

uv run pytest tests/mdm/test_temporal_graph_queries.py -q
14 passed

uv run pytest tests/mdm/test_snowflake_graph_migration.py tests/mdm/test_cli_snowflake_graph.py tests/mdm/test_temporal_graph_queries.py tests/mdm/test_api.py -q
122 passed

uv run --extra s3 --extra snowflake --extra mdm pytest tests/ -q --ignore=tests/architecture/test_load_history_state_machine.py
733 passed
```

## Self-Check: PASSED

RSYNC-02, RSYNC-05, RTEMP-01, RTEMP-02, and RLINE-01 complete (with documented,
non-blocking caveats on CLI-default coverage wiring). RSYNC-01 partially addressed —
the Snowflake-side single guarded pointer is real, but MDM's own serving surface has no
generation-pinned read view to make the two sides literally symmetric. This closes
Phase 7's central architectural goal: a complete, verified generation is now the only
consumer-visible relationship state on the Snowflake/Neo4j side, activated and rolled
back through one guarded pointer, with exact (not count-only) verification gating
promotion. Plan 07-06 (semantic silver merge/promotion + bronze artifact idempotency/
repair audit) may begin.
