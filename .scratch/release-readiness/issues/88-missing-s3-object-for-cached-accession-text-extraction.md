Type: task
Status: open

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

Not investigated further this session -- found during ticket 86/87's
live verification, filed to avoid losing the finding, not chased given
session length. The full task log is not preserved beyond this session;
re-triggering the same `targeted-resync --scope-type cik --scope-key
320193` (now safe to do, since ticket 87 isolates the immutable-conflict
noise and ticket 86 releases the lease cleanly on any other failure) will
reproduce it if still present.
