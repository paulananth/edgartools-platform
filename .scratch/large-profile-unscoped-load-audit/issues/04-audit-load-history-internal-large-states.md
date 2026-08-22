# 04 — Audit load_history's internal large-profile states for the unscoped-load shape

Type: task
Status: resolved

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

## Answer

Fixed one genuine, real gap (mirroring ticket 02's identical fix on a
sibling function); confirmed the rest safe with evidence, including
correcting a factual error in this ticket's own original framing.

**`ComputeWindows` — confirmed already covered by `seed-universe-narrow-
hydrate`, not a new gap. The `persist_run_manifest` claim in this ticket's
original framing was factually wrong for `ComputeWindows` specifically.**
Traced `warehouse_orchestrator.py`'s `compute-windows` handler directly:
it calls `db.get_tracked_ciks(...)` (a bounded metadata query, not a full
hydrate) and `_sync_reference_data(...)`, then falls through to the
shared publish path. `persist_run_manifest` — which genuinely does read
an entire canonical file into a Python `bytes` object
(`snapshot_payload = reference_snapshot_file.read_bytes()`, confirmed by
reading `identity_refresh_publication.py` directly) — is called only for
`command_name == "compute-identity-refresh-window"`, a *different*
command entirely (part of `bootstrap`/`daily_incremental`'s own identity-
refresh sub-pipeline, not `load_history`). The code's own comment at the
call site is explicit: "`compute-windows` (`load_history`) used to join
this same branch... but no longer does" (removed by the already-resolved
stage0-stage1-consolidation map). `compute-identity-refresh-window` also
runs on `wh_medium_arn`, not `large` — outside this entire map's
`large`/`mdm-large` scope, so not pursued further here; noted for the
record, not graduated as fog since this map is closing.

`ComputeWindows`'s real remaining hydrate cost is
`_hydrate_silver_database_from_storage` — called unconditionally for
every non-sharded command including `compute-windows`, confirmed via the
actual dispatch code (`warehouse_orchestrator.py` line ~581). This is the
**exact function name** the `seed-universe-narrow-hydrate` map's own
Destination text already names as a target, explicitly listing
`ComputeWindows` as one of the commands that benefits from that map's
"shared streaming-buffer fix" (fix #1) once it lands — confirming this
isn't a new, unaudited risk; it's the identical, already-tracked pattern.
Live-measured today: the canonical `silver.duckdb` S3 object is
1,590,702,080 bytes (1.59GiB, `s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`,
2026-08-18). On `ComputeWindows`'s `large` (8192MB) profile this leaves
~6.6GB headroom today — comfortable, though the underlying buffering
pattern is real and not yet streaming-fixed. No new fix built here:
re-fixing this would duplicate work `seed-universe-narrow-hydrate`
already owns, per this map's own Out-of-scope section.

**3 fundamentals-fetch commands (`fetch-entity-facts`/`fetch-per-filing-
fundamentals`/`fetch-thirteenf-holdings`) — confirmed already fixed with
exactly this map's established pattern, before this ticket existed.**
`infra/scripts/deploy-aws-application.sh`'s own comment at the
`per_window_fundamentals_entity_facts` state documents real, already-
root-caused prod OOM history (ecs-cost-sizing ticket 20, 2026-08-14): "a
500-CIK entity-facts window OOM'd (exit 137) on all 3 configured attempts
on `wh_medium_arn`... root-caused to the shared silver-publish merge step
(`merge_candidate_into_canonical`) materializing a cold-start table's
entire delta into Python (~2.3GB for this window's `sec_financial_fact`
table alone)." Verified the claimed structural fix is genuinely live, not
just described: `silver_protection.py`'s `_merge_chunk_size()`
(default 50,000 rows/chunk, `WAREHOUSE_SILVER_MERGE_CHUNK_SIZE` override)
explicitly documents bounding "Stage1BEntityFacts and Stage1BPerFiling"'s
merge — the exact batch-scope pattern this whole map enforces, already
applied. All 3 modes write through the same unified SEC silver DuckDB
file via the same merge path (per the deploy script's own comment), so
`FetchThirteenFHoldings` is covered by the identical fix. The
`wh_large_arn` task-profile move is explicit "belt-and-suspenders"
headroom *alongside* that code fix, not a substitute — same shape as
ticket 02's `ReduceIdentityRefresh` finding. No fix needed.

**`silver_mdm_gold`'s hardcoded `SeedUniverse` — genuine gap, fixed
(mirrors ticket 02's identical fix on `write_warehouse_mdm_gold_definition`).**
`write_silver_mdm_gold_definition` still hardcoded this state to
`wh_task_large_arn`, justified by a stale comment citing the same
full-hydrate OOM history `load_history`'s own `SeedUniverse` was fixed
for — but never ported to the ticket 06/07-decided
`command_task_profile('seed-universe') == "medium"` routing, exactly the
same "fixed elsewhere, not yet ported here" pattern ticket 02/03 found
and fixed on the sibling function. Fixed identically: bash-side
`command_task_profile("seed-universe")` call, routed to the ECS task ARN,
replacing the hardcode. Unlike `write_warehouse_mdm_gold_definition`
(which needed a conditional guard since it only sometimes includes a
`SeedUniverse` state), this function always includes one, so no guard was
needed — mirrors `write_load_history_definition`'s own unconditional
pattern exactly.

Tests: new `tests/architecture/test_silver_mdm_gold_seed_universe_task_profile_routing.py`
(3 tests, mirroring `test_warehouse_mdm_gold_seed_universe_task_profile_routing.py`'s
exact technique). Confirmed red without the fix via `git stash` (all 3
failed correctly). Fixing this also broke 3 pre-existing tests in
`test_mdm_pipeline_machine_tails.py` that source
`write_silver_mdm_gold_definition`'s function body in isolation without
`command_task_profile()` — updated that file's harness to also extract
and source `command_task_profile()`, since the function now genuinely
calls it. All 3 re-pass after that update.

`tests/architecture/`: 529 passed, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures. This was the map's
last open ticket — the Large-profile unscoped-load audit is now
complete: every `large`/`mdm-large` consumer has been checked against
the MANAGES_FUND-shape risk, with 3 genuine gaps found and fixed
(tickets 01/02/03-correction/04) and the rest confirmed safe with
recorded evidence. Not yet deployed — this ticket's mandate is
investigate-and-fix in the codebase; deployment is a separate, explicit
follow-up.
