Type: task
Status: resolved

Blocked by: 04

## Question

Implement the concrete fix Ticket 04 identified but deliberately left out of
scope: `edgar_warehouse/mdm/snowflake_graph.py`'s graph-materialization and
verify-graph queries filter relationship instances on `RI.IS_ACTIVE = TRUE`
but never `RI.QUARANTINED = FALSE`, so a quarantined row and the row it
conflicted with both materialize as separate, simultaneously-live graph
edges, and the parity checks meant to catch drift have the identical
omission on their "expected" side, so they silently agree instead of
flagging it.

## Answer

Ticket 04's own writeup named 3 sites; a full `grep -n "RI.IS_ACTIVE = TRUE"`
found 6 sites across 6 functions, plus a 7th (`_render_extra_edges`) that
needed the *inverse* check added (it flags graph edges that shouldn't
exist — a quarantined row's edge is exactly one of those, so it needed
`OR RI.QUARANTINED = TRUE` added to its existing "shouldn't be an edge"
condition, not the `= FALSE` filter every other site got):

- `SnowflakeGraphSyncExecutor.sync`'s eligible-edge preflight count
- `render_graph_tables`'s edge-build `INSERT` (the actual graph materialization)
- `render_validation`'s inline `active_mdm_relationship_parity` check
- `_render_verify_relationship_counts`'s "expected" CTE (`mdm verify-graph`)
- `_render_exact_relationship_parity`'s content-hash `mdm_side` CTE
- `_render_missing_edges`
- `_render_extra_edges` (inverse condition)

All additive filter changes — no schema change needed (the `QUARANTINED`
column already exists on the Snowflake mirror table, confirmed in Ticket
04's own investigation).

## Code review

Ran a combined Standards/Spec/GoF review. Spec found a real miss on the
first pass: `render_validation`'s standalone `mdm_relationship_instances_active`
metric read the table with no alias (`WHERE IS_ACTIVE = TRUE`, no `RI.`
prefix) -- a naive `grep -n "RI.IS_ACTIVE"` didn't catch it. GoF
independently recommended extracting a shared `_active_relationship_filter()`
helper (mirroring this file's own existing `_active_generation_filter`
precedent), citing the missed site itself as live evidence of the exact
"same fragment pasted at N sites, one gets missed" failure this file's
`git log` already shows recurring several times. Both fixed: added
`_active_relationship_filter(alias="RI")` next to `_active_generation_filter`,
switched all 7 sites plus the newly-found 8th to call it (added a table
alias to the previously-unaliased metric query). `_render_extra_edges`
keeps its inverse condition inline, as recommended -- it's genuinely a
different check, not the same fragment negated.

Tests: 1 new (`test_verify_graph_render_functions_exclude_quarantined_relationship_instances`)
covering the 4 verify-graph-only functions directly, plus 2 new assertions
in the existing `test_generated_sql_exposes_phase_2_graph_projection_contract`
covering the graph-build and inline-validation sites. All 43 pre-existing
tests in `tests/mdm/test_snowflake_graph_migration.py` pass unchanged.
Full `tests/mdm/` suite green (720 passed) after the extraction refactor.

Does not retroactively fix already-materialized duplicate edges in any
existing graph generation — that needs a fresh `sync-graph` full generation
rebuild (already the normal, expected way this system corrects itself;
per the generation-scoped design, `sync-graph` always does a full rebuild,
not an incremental patch) or, per Ticket 05's own note, an explicit
re-sync after the Postgres-side backfill runs.
