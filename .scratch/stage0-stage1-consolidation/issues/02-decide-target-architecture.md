# Decide target architecture: how Stage0 merges into Stage1, and whether Stage1's streaming fix ships combined or sequenced

Type: grilling
Status: resolved

## Question

Given ticket 01's findings — Stage0's output is a strict subset of Stage1's
own capture, the "Stage0-must-run-first" invariant is unenforced, and
Stage1's `WindowedBootstrap` has its own unfixed, un-streamed
full-window-accumulation OOM stopgap (the same class Stage0's
delta-then-reduce restructuring just fixed) — decide:

1. **Merge shape.** Confirm or revise ticket 01's sketched mechanical
   shape (delete `Stage0CompanyIdentity` Map + `ReduceIdentityRefresh`,
   let Branch A's `WindowedBootstrap` stand alone since it already
   produces Stage0's output as a byproduct). Does anything about the
   *live-backfill* context (task #35 mid-execution) change what shape is
   safe to build toward, even though nothing deploys until ticket 03's
   gate opens?

2. **Sequencing: combined or two separate restructurings?** Stage1's own
   `_capture_submission_bronze_snapshots` accumulation problem
   (`warehouse_orchestrator.py`, flagged at `deploy-aws-application.sh
   :2255-2263`) gets *worse*, not better, if Stage0's identity-capture
   work is folded into Stage1 without first (or simultaneously) fixing
   Stage1's own streaming — Stage1 would now carry more per-window work
   inside the same un-streamed accumulation loop. Decide: fix Stage1's
   streaming first as an independent prerequisite (mirrors how the
   sibling map treated the `reduce_identity_refresh` disk-accumulation fix
   as a standalone prerequisite before its own restructuring), fix both in
   one combined change, or merge Stage0 first and treat streaming as an
   explicitly-deferred follow-up (name the accepted regression if so, per
   this repo's own standard of not leaving known gaps implicit).

3. **Scope of the streaming fix, if it ships here.** `_run_submissions_
   bronze_then_silver`/`_capture_submission_bronze_snapshots` is called by
   more than just Stage1's `WindowedBootstrap` — decide whether the
   streaming fix should be scoped narrowly to the `load_history` caller
   path or fixed once for every caller (affects blast radius and how much
   this ticket needs to design vs. defer to implementation).

4. **`identity_refresh_publication.py` machinery fate for `load_history`.**
   If Stage0 is deleted as a stage, does anything about `ReduceIdentityRefresh`
   /`persist_batch_outcome`/`merge_candidate_into_canonical`'s
   `load_history`-specific wiring need explicit teardown, or does it
   simply go unused (dead code, cleaned up separately) since
   `daily_incremental` keeps using the same shared module? Sketch the
   answer here; ticket 04 owns the actual decision + detail.

Also revisit: does the Stage0 sequencing invariant's *replacement*
(nothing enforces identity-before-ownership anymore once Stage0 is gone)
need any new safeguard, or was it truly never load-bearing (ticket 01
found no code path depends on it) — i.e. is "remove it entirely, add
nothing" the correct answer, or should something explicit replace the
comment's stated intent even though nothing currently enforces it?

## Pre-grill fact-finding

Before grilling, checked the blast radius of question 2/3's streaming fix:
`_capture_submission_bronze_snapshots` (`warehouse_orchestrator.py:4555`,
docstring at 4568-4573) is **the single shared function behind all 5
SEC-fetching commands** — `daily_incremental`, `bootstrap`,
`bootstrap_full`, `targeted_resync`, `bootstrap_batch` — plus
`bootstrap-next`/`bootstrap-fundamentals` (confirmed via 6 call sites of
`_run_submissions_bronze_then_silver` across `warehouse_orchestrator.py`:
lines 1353 `daily-incremental`, 1420 `bootstrap`, 1450 `bootstrap-full`,
1490 `bootstrap-next`, 2017 (a third `_capture_bronze_raw` branch), 2983
`submissions_orchestrator`/`bootstrap-fundamentals`). It was already
deliberately restructured for throughput as a two-wave, worker-pool-backed
batch capture by pipeline-throughput-architecture ticket 06/78 (per its
own docstring), replacing a sequential per-CIK loop. "Stream bronze-capture
into silver-apply per CIK instead of materializing the whole window" is a
real restructuring of that shared, already-optimized wave design — not a
small Stage1-local patch.

## Answer

1. **Merge shape: confirmed as sketched in ticket 01, no changes.** Delete
   `Stage0CompanyIdentity` (Distributed Map) and `ReduceIdentityRefresh`
   from `write_load_history_definition`; Branch A's existing
   `bootstrap-next` call (`artifact_policy="all_attachments"`, a superset
   of Stage0's `company-identity` capture) stands alone.
   `SeedUniverse`→`MdmSeedUniverse`→`ComputeWindows` remain (they seed MDM
   and write `cik_windows.jsonl`), minus the `cik_batches.jsonl`
   pre-batching step that only Stage0 consumed.

2. **Sequencing: separate efforts, not combined.** Merge Stage0 now — it's
   small, mechanical, and already fully understood (gated on ticket 03's
   rollout gate). The streaming fix is explicitly **out of scope for this
   map** — it has platform-wide blast radius across all 5 SEC-fetching
   commands, and forking `_capture_submission_bronze_snapshots` just for
   `load_history`'s benefit would recreate the exact duplication
   pipeline-throughput-architecture ticket 78 eliminated. It deserves its
   own future wayfinder map, scoped platform-wide, not bundled here.
   **Accepted, explicitly named interim state:** once merged, Stage1 (the
   sole surviving stage) inherits Stage0's identity-capture work into its
   still-un-streamed accumulation loop — a real, known cost, not silently
   deferred. `deploy-aws-application.sh:2255-2263`'s stale "tracked
   separately" comment should be corrected to point at this map's finding
   (still no ticket exists for the streaming fix itself — that's the next
   map's charting job, not this one's).

3. **Sequencing invariant: remove entirely, add nothing.** Ticket 01 found
   no code path depends on Stage0-before-Stage1 ordering — Stage 2's
   `mdm run` (IS_INSIDER derivation) already only starts after Stage1/1B
   complete via the state machine's own sequential structure, independent
   of whatever Stage0 did or didn't do. The `deploy-aws-application.sh
   :2249-2259` comment is stale/incorrect and should be deleted or
   corrected as part of implementing this ticket's merge, not left as
   misleading documentation.

**Map destination reached for the Stage0/Stage1 half.** Stage1B remains
untouched (ticket 01 confirmed disjoint) — no further consolidation ticket
needed for it.

## Addendum (found during ticket 04, 2026-08-10) — corrects "no new code needed"

Ticket 04's cleanup investigation found a real correctness gap in this
answer's merge shape, not just leftover dead code. `compute-windows`
(`warehouse_orchestrator.py:699-708`) is documented as **"the sole owner
of the global reference snapshot. It deliberately does not publish
canonical silver: the reducer will merge this."** `ReduceIdentityRefresh`
is the *only* thing that ever merges that reference sync
(`company_tickers`/`company_tickers_exchange`, synced once per run at
`warehouse_orchestrator.py:2644-2652`) into canonical.
`bootstrap-next`/Stage1 never calls `_sync_reference_data` itself
(confirmed: its only caller besides `compute-windows` and
`compute-identity-refresh-window` is `targeted-resync`'s
`scope_type == "reference"` branch, `warehouse_orchestrator.py:1527-1537`
— unrelated). **Deleting `ReduceIdentityRefresh` as originally specified
would silently stop refreshing reference data for `load_history`
entirely** — point 1's "no new code needed" claim was wrong on this one
point. Fix (small, mechanical, folded into ticket 04's checklist): remove
`"compute-windows"` from the publish special-case tuple at line 699
(leave `"compute-identity-refresh-window"` alone — untouched,
`daily_incremental`-only), so `compute-windows` falls through to the
normal direct-publish path and its one-per-run reference sync lands in
canonical on its own, without needing a reducer at all.
