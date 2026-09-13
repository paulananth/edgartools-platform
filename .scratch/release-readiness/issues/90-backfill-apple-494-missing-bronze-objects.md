# 90 — Backfill Apple's 494 missing bronze objects

Type: task
Status: in_progress (operator decision made 2026-09-12: option (b), full CIK
targeted-resync; execution is armed and waiting on `daily_incremental`'s
`sec_fetch_active` lease to free -- see "Decision and current status" below)

## Question

[Ticket 88](88-missing-s3-object-for-cached-accession-text-extraction.md) found
(not fixed as data) that 494 of Apple (CIK 320193)'s 1,044 `sec_raw_object` rows
reference S3 keys that don't exist in the bronze bucket (477 attachment
children, 17 primary documents), most likely from one-off manual/repair
scripts run 2026-07-25 and 2026-07-31 that updated DB rows for a broader set
of documents than they actually wrote to S3. Ticket 88's code fix makes this
self-healing on next read (a cache-hit that finds the object missing now
transparently re-fetches it), so this ticket is purely about closing the data
gap proactively rather than waiting for something to read each accession.

Options: (a) do nothing -- ticket 88's self-heal means the gap closes lazily,
accession by accession, whenever something reads it; (b) a scoped backfill run
targeting exactly Apple, e.g. `targeted-resync --scope-type cik --scope-key
320193` (now safe per ticket 86/87's fixes) to force all 494 through the
self-heal path in one pass; (c) something narrower, re-fetching only the known
494 keys directly rather than a full CIK resync.

## Done when

An operator decision is made and, if a backfill is chosen, it's run and
verified (re-diff Apple's `sec_raw_object` storage paths against a fresh S3
listing, expect 0 missing).

## Decision and current status (2026-09-12)

Operator chose option (b): a scoped `targeted-resync` run against Apple only
(`--scope-type cik --scope-key 320193`), per ticket 86/87's fixes making this
safe.

`targeted-resync` and `daily_incremental` share the cross-command
`sec_fetch_active` lease (mutual exclusion, release-readiness Ticket 80/84),
so the resync can't start while a `daily_incremental` execution holds it. A
monitor (`retry_ticket90_when_free.sh`, still running as of this entry) polls
`daily-incremental-retry-1789236915`'s execution history for it entering
`ReleaseSecFetchLease` (or reaching a terminal status) and will
auto-start a fresh `ticket90-apple-backfill-retry-<timestamp>` execution
against `edgartools-prod-targeted-resync` the moment the lease frees.

As of this entry, `daily-incremental-retry-1789236915` is still `RUNNING`
(started 2026-09-12T14:15:18-04:00, ~4 hours in) and has only progressed
through `FetchEntityFacts` -- several stages remain (Stage 1B's remaining
fundamentals/13F fetches, Stage 1C's ADV/Firm Roster, the MDM chain, gold
refresh) before it reaches the point where the lease is released. The
targeted-resync has not yet fired. Once it completes, verify Ticket 90's
"Done when" criterion directly (re-diff Apple's `sec_raw_object` storage
paths against a fresh S3 listing of
`s3://edgartools-prod-bronze-690839588395/warehouse/bronze/filings/sec/` for
CIK 320193, expect 0 missing) before marking this ticket resolved.
