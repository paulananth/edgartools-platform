# Decide the target architecture for Stage0CompanyIdentity's windowed silver read/write

Type: grilling
Status: claimed
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
3. **Failure isolation: do not accept the tradeoff on faith.** Per the
   operator's explicit instruction, this ticket cannot resolve to
   delta-then-reduce as a locked answer until ticket 04 verifies (with
   primary-source evidence, not "plausible") that AWS Step Functions
   Distributed Map redrive actually provides safe, batch-level
   resumability for this exact manifest/delta shape. If ticket 04 finds
   redrive does NOT cleanly apply, this ticket reopens the failure-
   isolation question (design an explicit partial-promotion mechanism, or
   a different mitigation ticket 04's own Q4 may surface) before final
   answer.
4. **Scope: `load_history` only.** `daily_incremental`'s Stage0
   CompanyIdentity is only ever exercised in its already-bounded
   (CIK-list + `identity_refresh_run_id`) form in production — its
   unbounded path has zero prod executions ever (per CLAUDE.md). No live
   urgency there; this decision does not extend to restructuring it. The
   existing duplication-convention comments between
   `write_load_history_definition` and `write_warehouse_mdm_gold_
   definition` mean the two Stage0CompanyIdentity definitions may drift
   apart as a result — accepted, not treated as a defect of this decision.

**Not yet locked:** the concrete implementation shape (exact CLI flags,
state-machine wiring, redrive-triggering mechanism if needed) — that's
implementation detail for the follow-up session per this map's Notes, not
this ticket's job to specify.
