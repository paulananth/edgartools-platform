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
