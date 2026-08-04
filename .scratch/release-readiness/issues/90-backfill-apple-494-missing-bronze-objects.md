# 90 — Backfill Apple's 494 missing bronze objects

Type: task
Status: open

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
