# Clean up already-captured binary attachments in S3 bronze

Type: task
Status: open

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
