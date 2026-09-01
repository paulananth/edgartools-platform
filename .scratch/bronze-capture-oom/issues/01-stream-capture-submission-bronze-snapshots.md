# 01 — Stream `_capture_submission_bronze_snapshots` Instead of Materializing the Whole Batch

Type: task
Status: open

## Question

Fix a confirmed, reproducing production OOM in
`edgar_warehouse/application/warehouse_orchestrator.py` by converting
`_capture_submission_bronze_snapshots` from a function that returns one
fully-materialized `list[dict]` into a generator that yields bounded chunks,
mirroring the fix already applied once to `build_gold()` (now
`iter_gold_tables()`) for the identical class of bug.

## Live evidence (2026-09-01)

Execution `daily-incremental-ticket15-postfix-1788270018`
(`arn:aws:states:us-east-1:690839588395:execution:edgartools-prod-daily-incremental:daily-incremental-ticket15-postfix-1788270018`)
OOM'd twice on `RunWarehouseTask`, identically:

| Attempt | Task ARN suffix | Started | Failed | Duration | Exit |
|---|---|---|---|---|---|
| 1 | `cd5606da...` | 09:57:37 ET | 13:28:26 ET | ~3h31m | 137, `OutOfMemoryError: container killed due to memory usage` |
| 2 | `4f41b6e1...` | 13:30:56 ET | 16:29:01 ET | ~2h58m | 137, identical reason |
| 3 | `25ff3289...` | 16:33:35 ET | (in progress as of ticket filing) | — | — |

Both failures occurred on `edgartools-prod-large` (8192MB/2048 CPU),
`daily-incremental --recurring-index-lookback-days 7`. Each retry restarted
the entire run from scratch (re-hydrated the 1.8GB canonical
`silver.duckdb`, redid daily-index discovery, redid the apply phase from
0%) — no partial progress survived either OOM. Attempt 2 alone reached 92%
of its apply phase (11,140/12,068 CIKs, per live `silver_apply_progress`
logs) before dying minutes after entering the subsequent artifact-recovery
phase.

This run is processing 12,068 CIKs (documented separately in CLAUDE.md's
"daily_incremental multi-hour runtime after Bookkeeping Postgres cutover"
5-whys as a one-time full-universe reactivation, not the pipeline's normal
shape) — but the underlying memory bug is not scoped to that reactivation;
it will recur on any sufficiently large batch (a future re-bootstrap, a
large backlog catch-up, etc.), one-time or not.

## Root cause (confirmed via direct code reading, not inference)

`_capture_submission_bronze_snapshots`
(`edgar_warehouse/application/warehouse_orchestrator.py:4922`) fully
materializes every CIK's fetched submissions payload into memory before
returning:

- `main_checkpoint_by_cik`, `main_cache_by_cik`, `main_fetch_results`,
  `main_snapshot_by_cik` — each a `dict` keyed by every CIK in the batch,
  holding that CIK's full parsed `submissions.json` payload plus its bronze
  write record.
- The final `snapshots: list[dict]` (returned to the caller) assembles one
  entry per CIK containing `main_payload` (the full parsed submissions
  content) — for a 12,068-CIK batch, this is essentially the whole tracked
  universe's raw submissions content held in memory simultaneously.

This is the identical "materialize everything before consuming" shape
CLAUDE.md's own "Gold-build memory / daily_incremental OOM" 5-whys entry
already diagnosed and fixed once, for a different function: `build_gold()`
returned a fully-realized `dict[str, pa.Table]` before any table was
written; the fix (commit `86154db8`, "fix(gold): stream build_gold() per
table to prevent OOM") replaced it with `iter_gold_tables()`, a generator
yielding one table at a time. `_capture_submission_bronze_snapshots` — a
sibling function added later (`8eee149a`, release-readiness Ticket 78) —
was never given the same treatment.

**Only one call site exists** (confirmed via `grep`):
`edgar_warehouse/application/warehouse_orchestrator.py:3392`, inside the
function that also runs `_apply_submission_snapshot_to_silver` in a loop
immediately after (lines ~3380–3465). The caller currently does two full
passes over the fully-materialized list: (1) flattens every snapshot's
`write_records` into one list to compute `bronze_capture_completed`'s
counts (`raw_object_count`, `catalog_network_fetches`,
`catalog_silver_skips`); (2) loops over every snapshot, applying each to
silver, emitting `silver_apply_progress` every 10.

## Reviewed fix plan (approved via `/gof-refactor-reviewer`, not yet implemented)

Convert `_capture_submission_bronze_snapshots` into a generator that
internally chunks the `ciks` list into bounded windows (a new
module-level, env-var-configurable chunk size — mirroring this codebase's
existing `WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY`-style knobs, exact default
value not yet chosen, see below), running the *existing* wave-based
dispatch logic (`_dispatch_to_worker_pool`, unchanged) scoped to one
chunk's CIKs per iteration, and `yield`ing that chunk's list of snapshot
dicts instead of accumulating everything into one list.

Restructure the single caller
(`edgar_warehouse/application/warehouse_orchestrator.py:~3380-3465`) to
interleave: capture chunk N → apply chunk N to silver → let chunk N's
snapshots (the large parsed-JSON payloads) go out of scope → capture chunk
N+1. This bounds peak memory to O(chunk_size) instead of O(total CIK
count).

**Why chunking, not a true per-item generator:** confirmed via git history
that `_dispatch_to_worker_pool` (all 4 call sites internal to this one
function — no external callers, confirmed via grep) was already touched
once for a related memory/perf fix
(`995856c7`, "Stage 14 cutover fixes — OOM, promotion races, cache-hit
parallelization"), and the function's own docstring cites Ticket 78
replacing a *sequential* per-CIK loop specifically for throughput. A pure
per-item generator (yield-as-each-future-completes) would either abandon
that batched worker-pool dispatch shape or require rewriting
`_dispatch_to_worker_pool` itself into a generator — a bigger, riskier
change to a shared primitive that isn't necessary here, since bounding its
input via chunking already bounds its output.

**Real, honest behavior change flagged during review, not yet resolved:**
`bronze_capture_completed` currently fires once, after ALL capture
completes, strictly before any apply begins — its `duration_seconds`
measures pure capture time. Once capture and apply interleave per chunk,
this event can only fire once at the very end of the whole loop with
accumulated totals, and `duration_seconds` will then measure total
capture+apply wall time, not capture alone. `silver_apply_started`/
`silver_apply_progress`/`silver_apply_completed` keep their existing shape
and meaning, just fed from the interleaved loop instead of a separate
second pass. **This needs explicit test coverage pinning down the new
semantics, and should be called out clearly in the Spec axis of this
fix's eventual 3-axis code review** — not just documented in a comment.

## Why NOT `load_history`'s windowing (considered and rejected for this fix)

`load_history`'s `WindowedBootstrap` is a Step Functions Distributed Map —
each window is a *separate ECS task launch*, with Step Functions itself
tracking per-window retry/resumability. `daily_incremental`'s state
machine has no equivalent Map state; `RunWarehouseTask` is a single Task
state running one long-lived process end-to-end. Retrofitting that pattern
here would mean rewriting `daily_incremental`'s state machine
(`infra/scripts/deploy-aws-application.sh`), restructuring the
`daily-incremental` command to accept a bounded CIK slice per invocation,
and likely changing the local silver candidate's publish cadence (once per
window instead of once per run — reopening the exact promotion-conflict
risk class CLAUDE.md already documents for concurrent publishers to one
canonical object). That's a materially bigger, riskier change than an
in-process generator fix, disproportionate to a memory bug that the
generator fix solves directly. The one real benefit Step-Functions-level
windowing would add that this fix does not — resumability across *any*
task failure, not just OOM, since a completed window could survive a
crash — is a genuine, separate architectural investment; **not in scope
here**, worth its own ticket if wanted later.

## Resumability considered and rejected for this fix

Investigated whether Bookkeeping's per-CIK sync state could let a retry
skip CIKs already captured in a prior crashed attempt, avoiding a full
restart on top of this fix. **Confirmed unsafe as currently wired** —
see [Ticket 02](02-checkpoint-outruns-silver-publish-on-crash.md): a CIK's
checkpoint commits durably to Postgres immediately, but its Silver content
only becomes durable once, at the very end of the whole run. A crash
between the two leaves the checkpoint claiming content that was never
published — and worse, causes the *next* run's skip-if-unchanged
optimization to permanently skip re-staging it, since the checkpoint looks
current. This is a real, standing data-integrity bug (already live-exposed
by today's two OOMs, independent of this ticket), not something to build
resumability on top of. Do not attempt Bookkeeping-based skip-on-retry
until Ticket 02's structural fix lands.

## Not yet decided

- **Chunk size default.** Needs to be large enough to preserve worker-pool
  throughput efficiency (avoid excessive per-chunk dispatch overhead for
  small/normal daily runs) while small enough to meaningfully bound peak
  memory on a reactivation-scale run. No number has been chosen or
  measured yet — should be picked based on rough per-CIK payload size
  (unmeasured) against the 8192MB ceiling, then validated live.
- **Whether to expose the chunk size as an env var** (following the
  `WAREHOUSE_ARTIFACT_FETCH_CONCURRENCY` precedent) or hardcode a constant.
- **Whether other callers of the shared bronze-capture path** (the
  function's own docstring claims it backs `bootstrap`/`bootstrap_full`/
  `targeted_resync`/`bootstrap_batch` too, despite only one literal call
  site existing today — worth confirming those other commands actually
  route through this same call site before assuming the fix helps them
  too) need any additional verification post-fix.

## Deliverable

- [x] `_capture_submission_bronze_snapshots` converted to a chunked
      generator (`WAREHOUSE_SUBMISSION_SNAPSHOT_CHUNK_SIZE`, default 500);
      `_dispatch_to_worker_pool` left unchanged, called once per chunk
      from a new `_capture_submission_bronze_snapshots_for_chunk` helper
      holding the original wave-based dispatch logic verbatim
- [x] Caller (`_run_submissions_bronze_then_silver`) interleaves
      capture/apply per chunk. Proven two ways, not one:
      `test_chunks_are_yielded_lazily_not_materialized_upfront`
      (`tests/unit/test_submissions_fetch_concurrency.py`) proves the
      generator itself doesn't fetch chunk N+1 until chunk N is consumed;
      `test_multi_chunk_submission_flow_interleaves_bronze_and_silver_per_chunk`
      (`tests/unit/test_submission_phase_order.py`, replacing the old
      `test_bulk_submission_flow_captures_all_bronze_before_silver`, whose
      premise this fix deliberately changes) proves the caller applies
      each chunk before capturing the next, not "all bronze then all
      silver" globally. **Not proven**: that the caller's local
      references to a chunk's large payloads are actually garbage
      collected after that chunk's apply step (a `weakref`-based check) —
      flagged by the Spec review pass as the literal "provably not held"
      wording asks for; deliberately not built here given cost vs. the
      two proofs above already covering the behavioral claim that matters
      (bounded, lazy, per-chunk processing). Follow-up if ever in doubt.
- [x] `bronze_capture_completed`'s new timing semantics covered by an
      explicit test
      (`test_bronze_capture_completed_fires_after_the_whole_interleaved_loop`)
      and documented in the fix's comments — plus two more undocumented
      consequences the Standards/Spec review passes found and this fix
      then documented: `silver_apply_completed`'s duration now
      near-duplicates `bronze_capture_completed`'s (no clean way to
      measure apply-alone time once phases interleave, not built here),
      and `silver_apply_started` no longer reports `raw_object_count`
      (would always have been wrongly 0 once it fires before capture
      begins).
- [x] Full test suite green: 2994 passed, 6 skipped (only the 8
      pre-existing, unrelated Postgres-integration failures remain,
      confirmed via `git stash` comparison — not introduced by this fix)
- [x] 3-axis code review (Standards/Spec/GoF) run before commit, per
      CLAUDE.md's hard rule. GoF: clean, "ship as-is," no findings.
      Standards: two real findings (both fixed — see above). Spec: three
      findings — the two Standards also caught (fixed) plus the missing
      `bronze_capture_completed` timing test (fixed) and the
      caller-release memory proof gap (deliberately deferred, documented
      above, not silently dropped).
- [ ] Verified live against a real large-batch run — not yet done. The
      currently-running reactivation-scale `daily_incremental` execution
      started before this fix was built, so it does not exercise this
      code; needs its own dedicated verification run once deployed.
