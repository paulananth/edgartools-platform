Type: task
Status: in_progress

## Question

Found live 2026-08-04 during ticket 86/87's post-deploy verification
(`targeted-resync --scope-type cik --scope-key 320193`, execution
`ticket86-87-liveverify-apple-1785851096`). Distinct from tickets 86/87 --
not an immutable-object conflict, not caught by `_is_immutable_object_conflict`.

Accession `0001140361-23-004439` (attachment `brhc10047294_defa14a.htm`)
logged an `accession_cache_hit` (2 attachments, implying `raw_object_id`
rows already exist in silver), but the subsequent `include_text` step
(`filing_text_projection.py:extract_text_for_accession` ->
`object_storage.py:read_bytes` -> `s3fs`) failed trying to open the actual
S3 object at
`edgartools-prod-bronze-690839588395/warehouse/bronze/filings/sec/cik=320193/accession=0001140361-23-004439/primary/brhc10047294_defa14a.htm`
-- traceback bottoms out in `fsspec`/`s3fs` `.info()`/`.details` (looks
like a `FileNotFoundError`-class failure, full stack not yet parsed to the
final exception line). This aborted the whole run (this exact failure is
what ticket 86's new `Catch` correctly caught and release-then-failed on
-- confirmed working: lease released cleanly, run_id matched, no manual
intervention needed, unlike the earlier session's two manual recoveries).

Open questions, not yet investigated:
1. Does silver's `raw_object` row for this accession point at a bronze key
   that was never actually written, or was written and later deleted/
   never-promoted (a staged-but-not-promoted object, cf. the orphaned-
   staged-blob cleanup work referenced elsewhere in this repo)?
2. Is this isolated to this one accession, or a broader class (same
   question ticket 87 asked and answered for immutable-object conflicts --
   not yet answered here)?
3. Should `include_text`'s cache-hit path verify the object actually
   exists before trusting the `raw_object_id` row, or is a hard failure
   here correct (real data missing) and the fix belongs in whatever wrote
   the row without the object landing?

## Investigation (2026-08-04)

**Not isolated -- a real, sizeable gap for Apple, not a one-accession fluke.**
Downloaded canonical `silver.duckdb`, extracted all 1,044 `sec_raw_object`
storage paths for CIK 320193, and diffed them against a real
`list-objects-v2` of the bronze bucket's `cik=320193/` prefix (2,336 live
keys). **494 of 1,044 (47%) reference S3 keys that do not exist** -- spot-
checked 3 with direct `head-object`: genuine 404s, not a listing artifact.
Bucket has versioning `Enabled`; `list-object-versions` on the ticket's
original accession prefix returned **zero** entries, not even a delete
marker -- weaker evidence than "provably never created" (only rules out
deletion for whatever window versioning has actually been on), but there is
no delete-marker evidence of deletion either. 477 of the 494 are attachment
children, only 17 are primary documents.

**Provenance, and a caution about it:** all 494 missing rows have
`fetched_at` on exactly two calendar days, 2026-07-25 (259) and 2026-07-31
(235). Initially read this as "two one-off scripts wrote DB rows without a
matching S3 write." That's too strong on its own -- checked the discriminating
case (advisor-prompted): the **550 present** objects for the same CIK
*also* cluster heavily on those same two days (242 and 151 respectively).
So the two days were high-volume operational days for Apple generally (both
present and missing), not exclusively bad-script days -- but the failure
rate within each of those two days is still striking (52% missing on
07-25, 61% missing on 07-31), far above what the standing pipeline should
produce: `fetch_filing_artifacts`/`write_immutable_bytes`
(`bronze_filing_artifacts.py`, `object_storage.py:265`) is source-confirmed
to write S3 durably (`put_object` with `IfNoneMatch: "*"`, verified against
a strongly-consistent bucket) *before* the DB row is ever upserted -- there
is no ordering gap in the current code that could produce this. The 07-31
date matches [ticket 46](46-decide-repair-apple-orphaned-8k-bronze.md)'s
own described repair methodology (hand-rolled boto3 restore with per-key
ETag preconditions, run outside the standard pipeline, and explicitly
scoped to only the 45 *primary* 8-K documents -- consistent with why 477 of
494 missing are attachment children, not primaries). 07-25 most likely
correlates with the Apple pilot-migration work referenced in CLAUDE.md's
manifest-pipeline incident, though that correlation is not independently
confirmed the way 07-31 is. **Net: most likely explanation is one-off
manual/repair scripts that updated DB rows for a broader set of documents
than they actually wrote to S3, not a defect in the standing pipeline** --
but this is not a fully closed investigation, and no other CIK has been
checked for the same pattern (deliberately out of scope for this pass, see
below).

## Decision (2026-08-04)

Fix shape: extend `fetch_filing_artifacts`'s existing self-heal machinery
rather than add a new code path. `_split_existing_attachment_rows`
(`bronze_filing_artifacts.py:364`) already buckets attachment rows into
`missing_rows` (real re-fetch) when `db.get_raw_object()` returns `None`;
extend that same bucketing to also treat a DB row whose S3 key is absent as
`missing` -- matches ticket 75's precedent (`find_existing`, one `LIST` per
accession prefix instead of a per-attachment `HEAD`) to avoid adding
per-cache-hit S3 latency at scale. `extract_text_for_accession`
(`filing_text_projection.py`) gets the same treatment so a dangling
`raw_object_id` doesn't crash text extraction. This is not a violation of
the `--force`-only re-fetch policy (CLAUDE.md's "SEC data idempotency"): a
dangling pointer is the *missing-data* case, not the *already-captured*
case -- nothing here re-fetches genuinely-captured content without
`--force`. Caveat worth carrying into the PR description: once an accession
self-heals, the re-fetch covers *all* its documents, so a genuinely
byte-drifted sibling that was previously masked by the false cache hit can
now surface a real immutable-object conflict -- `targeted-resync` already
isolates that via ticket 87; other commands would still hard-fail on it,
which is correct existing behavior, not a regression.

**Deliberately out of scope for this ticket** (per advisor review, filed
separately rather than folded in): backfilling the 494 known-missing Apple
objects ([ticket 90](90-backfill-apple-494-missing-bronze-objects.md)), and
scanning other CIKs for the same pattern
([ticket 91](91-scan-other-ciks-for-missing-bronze-objects.md)).

## Implemented and tested (2026-08-04) -- not yet deployed or live-verified

Implemented in `bronze_filing_artifacts.py` (`fetch_filing_artifacts`'s fast
accession-level cache-hit path and its per-document loop, both now verify via
one `find_existing` S3 LIST per accession before trusting a
`sec_raw_object` row -- gated behind `existing_rows and not force` so a
brand-new accession pays zero extra cost) and `filing_text_projection.py`
(`extract_text_for_accession` self-heals via `refresh_filing_artifacts` on a
dangling primary reference instead of crashing). New
`CaptureSpecFactory.filing_document_glob`/`WarehousePathResolver.filing_document_glob`
helper in `dataset_path_catalog.py`.

8 new tests (`tests/unit/test_bronze_filing_artifacts_verify_s3_presence.py`,
`tests/unit/test_filing_text_projection_verify_s3_presence.py`), 4 existing
test fixtures updated (`test_edgartools_filing_gateway.py` ×2,
`test_loader_idempotency.py` ×2 -- their fixtures asserted a cache hit while
pointing `storage_path` at a fabricated, never-written key; now write a real
object first). Full suite green: 1322 passed, 4 skipped, only the
pre-existing unrelated `test_go_live_wizard.py` failure.

**Live-verified the presence-check logic itself** (not the full fix, since
that requires a deploy) directly against real prod S3/silver.duckdb: for 5
real, present Apple raw-object rows, `find_existing`'s returned S3 key is
string-identical to `sec_raw_object.storage_path` (this mattered --
`find_existing`'s local vs. remote code paths construct paths differently,
and a mismatch would have made every cache hit a false miss); for the
original ticket-88 accession's known-missing key, `find_existing` correctly
returns nothing.

**Not yet deployed to prod, not yet live-verified end-to-end.**
