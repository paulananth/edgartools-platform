# 91 — Scan other CIKs for the same missing-bronze-object pattern

Type: task
Status: resolved (2026-09-12) — pattern confirmed NOT Apple-specific; see
"Scan results" below. Follow-up backfill scoped as a new ticket (see bottom).

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

## Scan results (2026-09-12)

Method: downloaded canonical `silver.duckdb` (1.79 GB,
`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`),
queried `sec_raw_object` for every row with `fetched_at::date IN
('2026-07-25', '2026-07-31')` across **all** CIKs (not just Apple) — directly
targeting Ticket 88's own documented hypothesis about provenance, per the
operator's chosen scope for this ticket. 6,020 rows matched, across 34
distinct CIKs. For each of the 34 CIKs, listed its full bronze prefix
(`s3api list-objects-v2 --prefix warehouse/bronze/filings/sec/cik=<cik>/`,
one listing per CIK — 34 listings total, not per-object HEAD calls) and
diffed each suspect row's `storage_path` against that listing.

**The pattern is confirmed NOT Apple-specific.** 8 of the 34 CIKs have
missing bronze objects among their suspect-date rows, 1,768 missing objects
total (Apple's already-known 494 included):

| CIK | Entity | Checked | Missing |
|---|---|---|---|
| 21344 | Coca-Cola Co | 909 | 753 |
| 320193 | Apple Inc. | 887 | 494 |
| 1318605 | Tesla, Inc. | 1,207 | 125 |
| 789019 | Microsoft Corp | 624 | 203 |
| 1045810 | Nvidia Corp | 468 | 71 |
| 1067983 | Berkshire Hathaway Inc | 160 | 68 |
| 1018724 | Amazon.com Inc | 228 | 48 |
| 1652044 | Alphabet Inc. | 583 | 6 |

The remaining 26 CIKs (checked, 0 missing each) are not affected. Notably,
every affected CIK is a mega-cap, heavily-filed company — consistent with
the one-off manual/repair scripts (Ticket 88's suspected provenance) having
targeted a curated list of major issuers, not a random slice of the
universe. This is scoping evidence, not proof of the scripts' actual target
list.

Raw scan output (full missing-row detail per CIK, not just counts) was
written to this session's scratchpad during the investigation, but that
directory is session-scoped and will not survive into a future session —
whoever picks up Ticket 103 will need to regenerate the per-object missing
list by re-running the same method (query `sec_raw_object` for the affected
CIK, list its bronze S3 prefix, diff), not by reading a stale path from this
entry.

## Follow-up

A new ticket is needed to backfill the 7 additional affected CIKs (Coca-Cola,
Tesla, Microsoft, Nvidia, Berkshire Hathaway, Amazon, Alphabet) the same way
Ticket 90 backfills Apple — most likely via the same `targeted-resync
--scope-type cik --scope-key <cik>` mechanism, run once per CIK (or a
multi-CIK scope if `targeted-resync` supports one; not yet checked). See
that new ticket for scoping and execution.
