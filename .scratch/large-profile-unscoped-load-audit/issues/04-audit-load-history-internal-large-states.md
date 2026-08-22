# 04 — Audit load_history's internal large-profile states for the unscoped-load shape

Type: task
Status: open

## Question

**Corrected scope (via /to-spec investigation):** this ticket's original
draft, written while charting the map from an approximate line-number
inventory, misattributed 3 states to `load_history` that actually live in
`write_warehouse_mdm_gold_definition` (`bootstrap`/`daily_incremental`'s
shared state-machine builder) — `ReleaseSecFetchLease`,
`ReduceIdentityRefresh`, and one hardcoded `SeedUniverse`. Those moved to
ticket 02 (its exact scope). This ticket now covers what's genuinely
`load_history`-internal, plus one newly-found gap in a third state
machine.

`load_history`'s state machine (`write_load_history_definition`,
`infra/scripts/deploy-aws-application.sh`) runs several of its own states
on `wh_large_arn` beyond the already-covered `bootstrap-next`/
`seed-universe` (task-profile-consolidation map, tickets 06/07, both
resolved, both confirmed correctly routed through the shared
`command_task_profile()` lookup): `ComputeWindows` (window planning) and
3 per-window fundamentals fetches — `fetch-entity-facts`,
`fetch-per-filing-fundamentals`, `fetch-thirteenf-holdings`. None of
these four have been checked against the MANAGES_FUND-shape risk (an
unscoped full load of a shared table/dataset before scoping is known).

`ComputeWindows`'s own comment already documents a related, known
pattern: it "hydrated the full canonical silver.duckdb" and separately
calls `persist_run_manifest`, which "reads that same ~1GB+-and-growing
canonical file fully into a Python bytes object." Confirm whether this
hydrate is the same one the seed-universe-narrow-hydrate map already
fixed with streaming (PR #392) or a separate, still-unfixed call path —
if separate and still unbounded, this is a live, not just theoretical,
instance of the shape this ticket is hunting for, currently mitigated
only by generous task sizing (8GB), not an actual scoped-load fix.

**A genuinely new finding, folded in here rather than spun into a 5th
ticket:** `write_silver_mdm_gold_definition` (the `silver_mdm_gold`/
`BatchSilver` reprocessing pipeline's state-machine builder — not covered
by any of this map's other 3 tickets) has its own hardcoded `wh_large_arn`
`SeedUniverse` state, justified by a comment citing the *same* full-hydrate
OOM history `load_history`'s SeedUniverse was fixed for — but task-profile-
consolidation ticket 06 already fixed that root cause (streaming hydrate)
and settled `command_task_profile('seed-universe') == "medium"` as the
single answer everywhere. This state was never revisited after that
decision landed. Confirm whether it should now route through the same
shared lookup (mirroring `test_seed_universe_task_profile_routing.py`'s
already-proven pattern for `load_history`'s own SeedUniverse) or whether
`silver_mdm_gold` has a genuine reason to diverge that ticket 06 didn't
already rule out.

If a genuine gap is found in either area, fix it the same way MANAGES_FUND/
INSTITUTIONAL_HOLDS were (batch-scope, release-between-batches,
red-before-green test) — or, for the SeedUniverse routing question, the
same shared-lookup pattern task-profile-consolidation already established.
If nothing new is found, record that explicitly with the evidence checked
— a clean bill of health is a valid, useful answer here.

## Blocked by

None — can start immediately.
