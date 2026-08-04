# 91 — Scan other CIKs for the same missing-bronze-object pattern

Type: task
Status: open

## Question

[Ticket 88](88-missing-s3-object-for-cached-accession-text-extraction.md) found
494 of Apple (CIK 320193)'s 1,044 `sec_raw_object` rows point at S3 keys that
don't exist. That investigation was deliberately scoped to Apple only (the
CIK where the failure was first observed live) -- no other CIK has been
checked for the same pattern. Given the likely provenance (one-off
manual/repair scripts, not the standing pipeline -- see ticket 88's
"Investigation" section), other CIKs that were touched by similar ad-hoc
work during the same window (2026-07-25, 2026-07-31) are the most likely
candidates, but this is unconfirmed.

Needs: a platform-wide (or at least sampled) diff of `sec_raw_object.storage_path`
against a real S3 listing, similar to ticket 88's Apple-scoped method (download
canonical `silver.duckdb`, `list-objects-v2` per CIK or in bulk, diff). Given
`sec_filing_attachment` has 320,763+ rows platform-wide (per ticket 71's
count), a full scan is nontrivial -- may want to sample rather than scan
every CIK first.

## Done when

Either a platform-wide/sampled scan confirms the gap is Apple-specific (no
further action needed beyond ticket 90), or it finds the same pattern
elsewhere and scopes a follow-up backfill.
