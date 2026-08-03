# Clean up already-captured binary attachments in S3 bronze

Type: task
Status: in_progress

## Question

[Ticket 70](70-decide-exclude-binary-artifacts-from-fetch-policy.md) decided the
default artifact-fetch policy stops downloading/storing raster-image exhibits
(`.jpg`/`.jpeg`/`.png`/`.gif`) going forward. The operator also asked for
already-captured binary content in existing bronze storage to be cleaned up, not
just excluded from new fetches.

This needs its own scoped investigation before any deletion runs, per this repo's
general caution around destructive/bulk operations against prod S3 (see the AWS
teardown 5-whys and ticket 65's own careful, `--dry-run`-first approach to the
`silverstage/` orphan cleanup in CLAUDE.md):

1. **How much is there?** Scan `sec_filing_attachment` (or the raw
   `sec_raw_object` table) for rows whose `document_name`/`storage_path` ends in
   `.jpg`/`.jpeg`/`.png`/`.gif` and is not `is_primary` — get an exact object
   count and total byte size across all of prod bronze, not an estimate.
2. **Is anything provably safe to delete, or does this need a grace period?**
   CLAUDE.md's SEC data idempotency principle treats captured SEC artifacts as
   additive/immutable — deleting already-captured content is a different kind of
   operation than *not capturing* something new, and reverses that principle for
   this one content type. Confirm: does any other table/process reference these
   `raw_object_id`s (e.g. `sec_filing_attachment` rows that would need to be
   deleted too, or dangling foreign-key-shaped references) before removing the S3
   objects themselves?
3. **What's the actual deletion mechanism?** One-off script (matching
   `destroy-aws-complete.sh`'s pattern of dry-run first, then confirmed execution)
   vs. an S3 lifecycle rule scoped to a prefix/tag (if these objects can be
   distinguished by key pattern or object tag without a full inventory scan every
   time).
4. Does this share any machinery with [ticket 65](65-clean-up-orphaned-staged-promotion-blobs.md)
   (the unrelated `_staging/`/`silverstage/` orphaned-promotion-blob leak), or are
   they fully independent cleanups that happen to both touch S3 bronze/warehouse
   storage?

## Done when

A concrete plan exists (object count, byte size, deletion mechanism, safety
confirmation) and either an operator-approved cleanup has run, or this is
explicitly deferred with a documented reason (e.g. cost too low to justify the
risk/effort right now).

## Progress (2026-08-03) — investigation done, deletion not yet run

Downloaded the canonical `silver.duckdb` read-only (1.25GB, same file both ticket
64/65 sessions touched) and queried it directly with local DuckDB -- `sec_filing_attachment`
and `sec_raw_object` are silver-only tables, not part of Snowflake's native S3 pull
(confirmed live: `EDGARTOOLS_SOURCE.INFORMATION_SCHEMA.TABLES` has no such tables).

**1. How much is there?**
- 127,035 `sec_filing_attachment` rows match `.jpg`/`.jpeg`/`.png`/`.gif`, all
  `is_primary = false` (confirms ticket 70's exclusion policy assumption -- no binary
  image has ever been a filing's primary document).
- These collapse to 96,619 *distinct* `raw_object_id`s (content-addressed dedup: the
  same image bytes legitimately recur across different filings/exhibits, per
  `sec_raw_object`'s own documented policy).
- `sec_raw_object` reports **96,619 objects, 17,890,476,093 bytes (~16.66 GiB)** for
  those IDs -- all fetched between 2026-07-21 and 2026-07-31, i.e. entirely
  pre-dating ticket 70's fetch-policy fix (2026-08-02). This is a lower bound on
  actual bytes-on-disk, not a hard count -- see caveat below.

**2. Is anything provably safe to delete?**
- Checked for the unsafe case directly: any `raw_object_id` in the binary-image set
  that is *also* referenced by a non-binary-image `sec_filing_attachment` row (a
  content-dedup collision that would make deletion break a still-needed reference).
  **Zero matches** -- every one of the 96,619 IDs is referenced exclusively by
  binary-image rows. No `sec_filing_attachment` rows would need deleting alongside
  the S3 objects; the row data (accession linkage) is independent of whether the
  underlying bytes still exist in S3.
- **Real caveat found, not yet resolved:** `sec_raw_object.storage_path` records
  exactly **one** S3 location per `raw_object_id` (the first-observed one) -- but
  `write_immutable_bytes`'s conditional-create checks the *destination key*, not a
  global content hash, so the same image bytes fetched under a second accession's
  path can produce a **second real S3 object** at a different key that this table
  never tracks. Confirmed the path shape from a live sample
  (`s3://edgartools-prod-bronze-690839588395/warehouse/bronze/filings/sec/cik=.../
  accession=.../attachments/<name>.jpg`). Deleting only the 96,619 tracked paths is
  **safe** (no other silver table depends on those specific paths existing --
  `sec_filing_attachment`'s linkage runs through `raw_object_id`/DB rows, not S3
  paths) but is **not provably complete**: it may undercount true bytes-on-disk if
  duplicate-content copies exist under other accessions' paths. A full
  `ListObjectsV2` scan of the bronze `filings/sec/` prefix, cross-referenced by
  extension, would be needed for an exact total -- not run yet (expensive: bronze
  has 320,763 total attachment rows across an unknown, likely much larger, real
  object count once historical accessions are included).

**3. Deletion mechanism:** not yet decided. Two live options, not mutually
exclusive: (a) a one-off script following `destroy-aws-complete.sh`'s dry-run-first
convention, deleting the 96,619 tracked `storage_path`s directly (bounded, known-safe
set); (b) closing the caveat above first via a full bucket scan, if getting the
complete/exact figure matters more than moving fast on the known-safe subset.

**4. Relationship to ticket 65:** confirmed fully independent -- ticket 65's
`silverstage/`/`_staging/` leak is staged canonical-*silver.duckdb* promotion
candidates (one ~1GB blob per promotion attempt); this ticket is per-document
*bronze* attachment content (millions of small objects, a completely different S3
prefix and write path -- `write_immutable_bytes`, not `write_staged_bytes`/
`promote_staged`). No shared machinery, no shared risk.

**Not yet done:** the actual deletion. Per this ticket's own scope note
("before any deletion runs") and this repo's destructive-operation convention,
deliberately left for explicit operator confirmation -- this entry documents the
concrete plan (option a: 96,619 known-safe objects, ~16.66 GiB) but does not
execute it.
