# Decide the target architecture for Stage0CompanyIdentity's windowed silver read/write

Type: grilling
Status: open
Blocked by: 01, 02

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
