# Decide the target architecture for Stage0CompanyIdentity's windowed silver read/write

Type: grilling
Status: resolved
Blocked by: 01, 02, 04

## Question

Given ticket 01's verdict on whether daily_incremental's delta-then-reduce
Identity Refresh pattern generalizes to load_history's Stage0
CompanyIdentity, and ticket 02's cost breakdown of hydrate vs. per-window
merge-publish, decide the target architecture for how Stage0
CompanyIdentity's windowed (no explicit `--cik-list`) capture should
resolve its CIK batch and read/write silver data — eliminating both the
full-canonical hydrate and the repeated full-canonical merge-publish,
while preserving:

- Stage0's fail-closed sequencing invariant (company data must be fully
  landed in canonical before Stage1Parallel/ownership/ADV work starts).
- SEC-fetch idempotency (must not silently multiply real SEC API calls
  beyond what's already necessary).
- Stage0's strict `ToleratedFailurePercentage=0` semantics (no silent
  proceed-past-failure).

Candidate directions to weigh (not exhaustive — ticket 01/02 may surface
others):

1. Selective/minimal-table hydrate: attach only the small tables
   company-identity mode reads/writes, skip 13F/financial-fact tables,
   keep the current per-window merge-into-canonical publish.
2. Restructure to delta-then-reduce, mirroring daily_incremental's bounded
   Identity Refresh: each window produces a small immutable delta, a
   single reduce step (gated appropriately so Stage1Parallel still waits
   for it) folds all deltas into canonical once.
3. Some hybrid, or a different mechanism ticket 01/02's findings suggest.

Also decide: does the same fix apply verbatim to `daily_incremental`'s own
(currently unbounded) Stage0CompanyIdentity if/when it runs without a
narrowed CIK set, or is that explicitly out of scope for this decision
(see map's Notes on the existing duplication-convention between the two
state-machine-generation functions)?

## Progress (grilling session, 2026-08-05)

Locked so far, pending ticket 04's redrive verification before this
ticket can be marked `resolved`:

1. **Direction: option 2, the full fix** (selective/minimal-table hydrate
   *and* delta-then-reduce restructuring), not option 1 (hydrate-only) or
   a middle path. The ~2.1hr repeated-I/O cost ticket 02 found is worth
   solving now, not deferring.
2. **Sequencing: the `reduce_identity_refresh` disk-accumulation fix
   (ticket 01's Q5) ships as its own standalone prerequisite**, before the
   Stage0 restructuring — it's a real, independent bug already affecting
   `daily_incremental` today (not load_history-specific), small and
   mechanical (stop accumulating `merged-{index}.duckdb` files between
   candidates — reuse a single output path or delete the prior file after
   each merge), and gates the larger restructuring safely. Does not need
   its own wayfinder ticket — no open design question about *whether* to
   fix it, only a small, already-sketched-in-ticket-01 implementation
   choice left to the engineer doing the fix.
3. **Failure isolation: verified redrive does not apply (ticket 04) —
   fallback locked.** Ticket 04 confirmed, against AWS's primary
   documentation, that Step Functions Distributed Map redrive excludes
   errors routed to a terminal `Fail` state via `Catch` — exactly this
   repo's `sec_fetch_task_catch()` wiring (added by release-readiness
   ticket 86 to release the `sec_fetch_active` lease promptly). Redrive
   is therefore not usable here, and dropping that `Catch` to make redrive
   eligible would reintroduce ticket 86's 18h stale-lease-wedging
   regression — not an acceptable trade. **Decision: build an explicit
   CLI-level partial-resume path** on top of the existing manifest/outcome
   contract (`identity_refresh_publication.py`) — e.g. a
   `--resume-failed-batches`-shaped input that lets an operator re-run
   `reduce_identity_refresh` (or the batch stage) against only the
   batches a prior run's manifest shows as not-`succeeded`, reusing each
   already-durable delta rather than redoing successful work. This
   sidesteps SFN's own redrive mechanism entirely and does not touch
   ticket 86's Catch/lease-release fix.
4. **Scope: `load_history` only.** `daily_incremental`'s Stage0
   CompanyIdentity is only ever exercised in its already-bounded
   (CIK-list + `identity_refresh_run_id`) form in production — its
   unbounded path has zero prod executions ever (per CLAUDE.md). No live
   urgency there; this decision does not extend to restructuring it. The
   existing duplication-convention comments between
   `write_load_history_definition` and `write_warehouse_mdm_gold_
   definition` mean the two Stage0CompanyIdentity definitions may drift
   apart as a result — accepted, not treated as a defect of this decision.

## Answer

**Locked architecture for `load_history`'s Stage0CompanyIdentity:**

1. Selective/minimal-table hydrate (load only `sec_company`,
   `sec_company_filing`, `sec_company_address`, `sec_company_former_name`,
   `sec_raw_object` — skip `sec_thirteenf_holding`/`sec_financial_fact`/etc)
   to fix the OOM's actual root cause (peak memory during hydration).
2. Restructure Stage0's windowed capture to delta-then-reduce, mirroring
   `daily_incremental`'s bounded Identity Refresh: each window emits an
   explicit CIK-list batch (not offset/limit windowing) and produces a
   small immutable delta via `persist_batch_outcome`; a single
   `reduce_identity_refresh`-shaped step folds all deltas into canonical
   once, gated ahead of `Stage1Parallel` the same way today's Map is.
3. **Prerequisite, standalone fix (ships first, independently):** fix
   `reduce_identity_refresh`'s per-candidate local-disk accumulation —
   intermediate `merged-{index}.duckdb` files are never deleted between
   candidates (ticket 01's Q5) — before restructuring Stage0 onto this
   path, since load_history's ~53-54-candidate scale would otherwise hit
   an un-exercised tens-to-100+GB local-disk regime.
4. **Failure-isolation mitigation:** an explicit CLI-level partial-resume
   path on the manifest/outcome contract (not SFN redrive, which ticket 04
   verified does not apply to this repo's Catch-to-Fail wiring; not a
   change to ticket 86's lease-release Catch).
5. Scope: `load_history` only — `daily_incremental`'s Stage0CompanyIdentity
   is out of scope for this decision (see Progress note 4).

**Not locked here (implementation detail for the follow-up session, per
this map's Notes — decision only, execution separate):** exact CLI flag
names/shapes, state-machine wiring specifics, the precise mechanics of the
partial-resume path, and the concrete fix for the disk-accumulation bug
(reuse-one-output-path vs. delete-after-each-merge).

## Implementation update (follow-up session, 2026-08-05)

Per this map's Notes, implementation happens outside the map — recorded
here only because it changes what's actually true about the locked answer
above, not as a new decision.

- **Point 3 (disk-accumulation prerequisite): shipped standalone, PR #360**
  (`edgar_warehouse/application/identity_refresh_publication.py`'s
  `reduce_identity_refresh` merge loop now unlinks the superseded `current`
  file each iteration — bounds peak local disk to ~2 canonical-sized files
  instead of O(candidate_count)). Merged to `main` before this update.
- **Point 1 (selective/minimal-table hydrate) turned out to be moot, not
  implemented as its own change.** `bootstrap_fundamentals.py`'s existing
  hydrate branch is `if not (mode == "company-identity" and raw_cik_list):
  _hydrate_silver_database_from_storage(context)` — once point 2's
  delta-then-reduce restructuring makes every Stage0CompanyIdentity call
  pass an explicit `--cik-list`, this condition is already false on every
  call, so hydrate is skipped **entirely**, not selectively. There is no
  remaining hydrate call to make selective. This was flagged as a
  suspected redundancy before implementation and confirmed true once point
  2 was built — the original "Answer" above listed points 1 and 2 as
  separately-necessary; in practice implementing 2 subsumes 1 completely.
- **Point 2 (delta-then-reduce restructuring): implemented for
  `load_history` only, per the locked scope.**
  `edgar_warehouse/application/warehouse_orchestrator.py`'s `compute-windows`
  handler now also calls `_sync_reference_data` once (previously called
  53x, once per Stage0 window — a bonus fix) and pre-batches the same
  ordered CIK list into `cik_batches.jsonl` (`_write_cik_universe_batches`),
  declaring it via `metrics["_identity_refresh_batches"]`. The publish
  special-case at `warehouse_orchestrator.py`'s `command_name ==
  "compute-identity-refresh-window"` branch (~line 656) was extended to
  also cover `"compute-windows"`, so it persists a run manifest + reference
  snapshot instead of a full-canonical publish, exactly mirroring how
  `compute-identity-refresh-window` already works.
  `infra/scripts/deploy-aws-application.sh`'s `write_load_history_definition`
  Stage0CompanyIdentity Map was restructured to read `cik_batches.jsonl`
  (ItemSelector wiring `cik_list` + the **parent** `identity_refresh_run_id`
  via `$$.Execution.Name`, since a DISTRIBUTED child's own
  `$$.Execution.Name` is the child's, not the parent's), each batch calling
  `bootstrap-fundamentals --cik-list ... --identity-refresh-run-id ...`
  instead of `--cik-offset/--cik-limit`, followed by a new
  `ReduceIdentityRefresh` state (`reduce-identity-refresh --run-id
  $$.Execution.Name --max-attempts 3`, kept on the `large` task def, not
  downgraded to `medium` alongside this restructuring — a downgrade is a
  separate, measured follow-up given load_history's batches are 500 CIKs of
  full submissions history with `include_pagination=True`, unlike
  daily_incremental's bounded daily deltas) before `Stage1Parallel`.
  `reduce_identity_refresh["ResultPath"]` was explicitly set to `None` (a
  real D-15-class bug that would otherwise have clobbered
  `$.artifact_policy`/`$.filing_lookback_years` before Stage1Parallel's
  WindowedBootstrap ItemSelector reads them — caught before merge, not
  live). Tests: `tests/architecture/test_load_history_state_machine.py`
  (generated-ASL shape) and `tests/unit/test_windowing.py` (handler-level
  metrics plus one real end-to-end test exercising
  `_execute_warehouse_bronze_capture` against a real local
  `SilverDatabase`/`StorageLocation`, confirming the run manifest +
  reference snapshot actually land and canonical silver is *not* touched
  directly by `compute-windows`).
- **Point 4 (CLI-level partial-resume path): still deferred, not
  implemented this pass.** Explicitly naming the accepted regression per
  this decision's own standard (don't leave a known gap implicit): with
  this restructuring live and no partial-resume mechanism yet, a
  Stage0CompanyIdentity failure now means **no** batch's delta reaches
  canonical for that run (`ReduceIdentityRefresh` never runs), so the
  *entire* Stage0 stage must be re-run from scratch on retry — strictly
  worse than the pre-restructuring windowed shape, where each window
  published directly to canonical and a later window's failure left
  earlier windows' data durably in place. This trade was made knowingly in
  the "Progress" section above (ticket 04 ruled out SFN redrive as a
  rescue), but is being re-stated here at the point where it actually took
  effect in code, not just in the decision record.
- **Map's own named constraint (SEC-fetch idempotency) verified, not just
  assumed.** The map's Notes flagged that the hydrate's local-DB read feeds
  `_resolve_submissions_main_cached_snapshot`'s cache-skip, and that "any
  fix here must not reintroduce" redundant-SEC-call regressions. Read the
  actual call chain: `_resolve_submissions_main_cached_snapshot`
  (`warehouse_orchestrator.py:4918`) tries the silver-checkpoint cache
  first (`_read_bronze_if_cached`, needs `db`), but on a miss — which is
  now guaranteed for every Stage0CompanyIdentity batch, since none of them
  hydrate — falls back to `_read_bronze_by_glob_if_present`
  (`warehouse_orchestrator.py:4952`), a **bronze-storage-only** check (S3
  glob by CIK, no `db` access at all) explicitly built for exactly this
  "fresh silver DB that never processed this CIK" case. An empty local db
  therefore does not multiply SEC calls for CIKs whose bronze objects
  already exist — it only adds one extra storage list/glob call per CIK
  before falling through to a live fetch, not a live fetch itself. No
  regression here.
- **New, real risk found during the advisor pass, fixed:** `ComputeWindows`
  was still on `wh_medium_arn` (4096MB) even though it now also calls
  `persist_run_manifest`, which reads the entire canonical `silver.duckdb`
  (`reference_snapshot_file.read_bytes()`) into a Python bytes object on
  top of the pre-existing full hydrate — the same OOM class this whole map
  exists to fix, relocated one state upstream. Fixed by moving
  `ComputeWindows` to `wh_large_arn` (same belt-and-suspenders precedent as
  Stage0CompanyIdentity/`run_wh` elsewhere in this file); regression test
  `test_compute_windows_uses_large_task_definition` added.
- **New risk found during the advisor pass, documented but NOT fixed (out
  of scope for this pass):** `persist_run_manifest`/`persist_batch_outcome`
  use `write_immutable_bytes`, which fails closed
  (`WarehouseRuntimeError: ... already exists with different content`) if
  the same key is written twice with different bytes. `ComputeWindows`
  keeps `ecs_state`'s default 3-attempt ECS task retry; the manifest/
  snapshot keys are derived from `run_id` (`$$.Execution.Name`), identical
  across retries of the same Step Functions execution. If attempt 1 writes
  the manifest/snapshot and then something *downstream* in the same task
  fails before the task exits successfully, Step Functions retries the
  whole task; attempt 2 re-hydrates and re-derives a new local
  `silver.duckdb` whose raw bytes will almost certainly differ from
  attempt 1's (DuckDB file layout is not byte-stable across independent
  runs even for identical logical rows) — so the retry fails closed
  instead of recovering, requiring an operator to either restart the whole
  execution under a fresh name or manually delete the stale
  `identity_refresh/runs/<run_id>/{run_manifest.json,reference/
  reference_snapshot.duckdb}` objects. **This is not a new mechanism** —
  `compute-identity-refresh-window` (daily_incremental) already has the
  identical exposure today, unfixed and unverified in prod (near-zero
  executions). This pass extends the same pre-existing gap to
  `ComputeWindows`, which is busier (every `load_history` run, not just
  scheduled daily refreshes). Fixing it properly (e.g., attempt-scoped
  manifest keys reconciled back to the parent run at reduce time, or
  tolerant-overwrite semantics) is a structural change to the shared
  `identity_refresh_publication.py` contract, not a `load_history`-only
  fix — out of scope for this decision's point 5. Flagged here so it isn't
  silently rediscovered from a wedged production retry.
- **Related, out-of-scope finding surfaced during implementation:**
  `write_warehouse_mdm_gold_definition`'s own (daily_incremental)
  `reduce_identity_refresh` state appears to have the identical missing
  `ResultPath: None` bug this implementation had to fix for load_history's
  copy — `RunWarehouseTask`(`run_wh`) downstream sets its *own*
  `ResultPath = None` (line ~3335), but that only protects `$` *after*
  `run_wh` runs; if `ReduceIdentityRefresh`'s ECS result already clobbered
  `$` before `run_wh`, `$.force`/`$.dataset_period`/`$.refresh_mode` would
  already be gone by the time `run_wh["ResultPath"]=None` preserves
  whatever `$` currently is. Not fixed here — out of scope per this
  decision's point 4 (`daily_incremental` excluded), and not verified live
  (daily_incremental has had zero-to-few prod executions per this map's
  Notes) — flagged for a separate ticket, not silently left for someone to
  rediscover from a live incident.
