# Decide fate of Stage0's delta-then-reduce/identity_refresh_publication.py machinery for load_history post-merge

Type: task
Status: resolved
Blocked by: 02

## Question

Once ticket 02 locks the merge shape (Stage0CompanyIdentity /
`ReduceIdentityRefresh` deleted from `load_history`'s definition),
`identity_refresh_publication.py`'s `persist_batch_outcome`/
`reduce_identity_refresh`/`merge_candidate_into_canonical` machinery loses
its `load_history` caller but stays alive via `daily_incremental`'s own
bounded Identity Refresh path (out of scope for this map — see map's Out
of scope section). Decide:

1. Does anything `load_history`-specific need explicit cleanup (dead
   `--identity-refresh-run-id`-shaped ASL wiring left in
   `write_load_history_definition`, unused `cik_batches.jsonl` writer in
   `compute-windows`'s handler), or is "stop calling it, leave the shared
   module as-is" sufficient since `daily_incremental` still exercises it?
2. Do the tests added for the Aug 5-9 restructuring
   (`tests/architecture/test_load_history_state_machine.py`,
   `tests/unit/test_windowing.py`) need updates/removal once
   `load_history`'s Stage0 states are gone, or do they stay as
   regression coverage for `daily_incremental`'s still-live equivalent
   path?

This is a `task`-shaped ticket (implementation-adjacent decision, not a
design question) — resolve with a short checklist an implementing engineer
can follow directly, not a design discussion.

## Answer

Investigation while writing this checklist found a real correctness gap,
not just dead code — see ticket 02's Addendum. `compute-windows` is the
sole path that syncs global reference data
(`company_tickers`/`company_tickers_exchange`) for `load_history`, and it
only ever reaches canonical via `ReduceIdentityRefresh`'s merge. Item 3
below is a required correctness fix, not optional cleanup — skipping it
silently breaks reference-data refresh for `load_history`.

**Checklist (all in `write_load_history_definition`/`compute-windows`'s
handler unless noted; `daily_incremental`'s separate
`compute-identity-refresh-window`/`Stage0CompanyIdentityBounded`/
`ReduceIdentityRefresh` copies are a different code path entirely and are
untouched by every item here — verified duplicated, not shared, so no
cross-machine risk):**

1. `infra/scripts/deploy-aws-application.sh`, `write_load_history_definition`:
   delete the `Stage0CompanyIdentity` Map state and the
   `reduce_identity_refresh` state/variable (~lines 2249-2361). Point
   `ComputeWindows`'s `Next` directly at `Stage1Parallel`.
2. `edgar_warehouse/application/warehouse_orchestrator.py`,
   `compute-windows` handler (~lines 2654-2671): delete the
   `_write_cik_universe_batches` call (`batches_path`), the
   `metrics["_identity_refresh_batches"]` assignment, and
   `metrics["cik_universe_path"]` — all three exist solely to feed
   `Stage0CompanyIdentity`'s Map/`ReduceIdentityRefresh`'s
   `persist_run_manifest` call, which no longer runs for this command.
3. **Required correctness fix** (ticket 02 addendum): remove
   `"compute-windows"` from the tuple at
   `warehouse_orchestrator.py:699` (`if command_name in
   ("compute-identity-refresh-window", "compute-windows"):`) so
   `compute-windows` falls through to the normal
   `_publish_silver_database_with_retry(context)` direct-publish path
   instead of the reducer-only run-manifest path. Keep the
   `_sync_reference_data` call (~lines 2644-2652) — it now publishes
   directly, once per `load_history` run, same total merge cost
   `ReduceIdentityRefresh` used to pay for this piece, just without a
   separate reducer stage. Update the stale comment at lines 699-708 to
   describe only `compute-identity-refresh-window`'s continued use of
   this branch.
4. `identity_refresh_publication.py` module itself: **no change.** Stays
   fully alive — `daily_incremental`'s own `reduce_identity_refresh`/
   `persist_batch_outcome`/`persist_run_manifest` calls are a separate,
   untouched ASL copy (`deploy-aws-application.sh:3364` vs. the deleted
   `load_history` copy at `:2347`) and keep using it exactly as today.
5. **Tests to remove** (`tests/architecture/test_load_history_state_machine.py`):
   the block asserting `Stage0CompanyIdentity`/`ReduceIdentityRefresh`
   existence, ordering, and Catch/task-def wiring in
   `write_load_history_definition`'s output (~lines 343-470 and
   ~1017-1049 per the grep — re-locate exact ranges at implementation
   time, since line numbers will have shifted). Keep every test that
   doesn't reference those two states (ComputeWindows ordering vs.
   `SeedUniverse`/`MdmSeedUniverse`/`Stage1Parallel`, tracking-status-filter
   parity with `bootstrap-next`, `ComputeWindows`'s own task-definition
   sizing) — those assertions remain true post-merge.
6. **Tests to rewrite** (`tests/unit/test_windowing.py`):
   `test_compute_windows_publishes_identity_refresh_run_manifest_not_full_canonical`
   (~line 610) must flip to assert the opposite —
   `compute-windows` now publishes directly to canonical silver, no run
   manifest. Add a new regression test confirming `_sync_reference_data`'s
   rows actually land in canonical after a real `compute-windows` run
   (mirrors the original restructuring's own precedent of "one real
   end-to-end test... confirming the run manifest + reference snapshot
   actually land," inverted for the new behavior) — this is the test that
   would have caught the addendum's gap had it existed before. Remove the
   `_identity_refresh_batches`/`cik_universe_path` assertions in
   `test_compute_windows_total_cik_limit_bounds_universe` and any sibling
   test tied to the batches-path plumbing removed in item 2.
7. Run the full suite green before merging; this repo's own convention
   (CLAUDE.md) requires it for any change touching production-critical
   orchestration logic.
