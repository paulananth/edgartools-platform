Type: task
Status: resolved

## Question

Found live in prod 2026-08-04 while verifying ticket 84's cross-command
lease: `targeted-resync --scope-type cik --scope-key 320193` (Apple)
failed with:

```
"error_message": "immutable object 'filings/sec/cik=320193/accession=0000320193-24-000075/primary/wk-form4_1717453877.xml' already exists with different content"
```

This is the repo's existing immutable-bronze fail-closed guard (see
CLAUDE.md's "SEC data idempotency" section) correctly refusing to silently
overwrite a captured object whose freshly-fetched content differs from
what's stored -- not a bug in that guard. Two open questions this ticket
should resolve:

1. **Why does the content differ?** Is this a genuine SEC-side
   republish/amendment of the same accession/primary-document path
   (plausible for a Form 4, which can be amended), a bug in this repo's
   content hashing/comparison, or stale/corrupted bronze from an earlier
   capture? Needs the actual byte diff between what's stored and what SEC
   currently serves at that URL before deciding.
2. **Should one conflicting accession hard-fail the entire CIK resync?**
   `targeted-resync --scope-type cik` processes up to ~1000 historical
   accessions per CIK in one pass (confirmed live -- not the "check for new
   filings" operation it might sound like); the immutable-object conflict on
   this one accession aborted the whole run rather than skipping just that
   accession and continuing. Combined with ticket 86 (no `Catch` on
   `RunWarehouseTask`), this is also what wedged the `sec_fetch_active`
   lease during that verification. Worth deciding whether per-accession
   conflict isolation is the right fix here, independent of ticket 86.

Not yet investigated: whether this is isolated to this one CIK/accession or
symptomatic of a broader class of already-captured objects that would fail
the same way if resynced.

## Investigation (2026-08-04)

**Root cause confirmed: SEC-side, not a bug in this repo.**

1. Downloaded the stored bronze object
   (`s3api get-object`, ETag `2e989252cfd48ad96b44a907ad07e055`): 4141
   bytes, `LastModified: 2026-07-25T19:31:17Z`.
2. Fetched the same document fresh from
   `https://www.sec.gov/Archives/edgar/data/320193/000032019324000075/wk-form4_1717453877.xml`
   directly (bypassing this repo entirely -- plain `curl`): 4142 bytes.
   Diff is exactly one trailing `\n` after `</ownershipDocument>` -- the
   filing content itself (every element, attribute, and value) is
   byte-identical otherwise.
3. Re-fetched 3 more times, 1s apart: stable at 4142 bytes /
   `48e7ef7b6c4b6efb92e4f0d4a4c68ae8` every time -- not a flaky/random SEC
   response, a real, stable change from what we captured a week+ earlier.
4. Ruled out this repo's own capture path as the cause by reading the
   actual source, not guessing:
   `edgar_warehouse/infrastructure/filing_content_gateway.py` is
   explicitly documented "byte-preserving... bronze stores the exact
   archival response, not a library-normalized value", and
   `download_sec_bytes` (`edgar_warehouse/infrastructure/sec_client.py`)
   returns raw `response.content` from `httpx` with zero `.strip()`/
   `.rstrip()`/decode-reencode anywhere in the path. Confirmed no
   stripping happens on our side.
5. Checked whether this is systemic: sampled 3 other already-captured
   Form 4 XML documents for the same CIK
   (`0000320193-17-000003`/`-000013`/`-000014`) -- all 3 show
   byte-for-byte identical length between stored and freshly-fetched SEC
   content. **Isolated to this one accession, not a pattern.**

**Conclusion**: SEC's own archival serving is not perfectly byte-stable
over time, even for a document this repo (and presumably SEC's own
convention) treats as permanently immutable once filed. A one-byte
trailing-newline drift appeared on SEC's side sometime between our
2026-07-25 capture and today, on this one document only. The immutable-
object fail-closed guard worked exactly as designed here -- it caught a
real byte-level mismatch and refused to silently overwrite rather than
guessing which version is "correct." The open design question (item 2
above) is real, not manufactured: is a whitespace-only, semantically
inert SEC-side drift worth hard-failing an entire ~1000-accession CIK
resync over, or should conflict handling isolate to the one accession
and continue? Both are defensible -- isolating trades some of the
guard's conservatism for resync robustness; leaving it as-is means an
operator has to notice and pass `--force` (or otherwise intervene) for
any doc-level drift like this to be tolerated. Not resolved here --
recording the confirmed root cause for the next session to decide,
rather than picking a fix unilaterally on a repo-wide fail-closed
behavior with no clear objectively-correct answer.

## Decision + implementation (2026-08-04)

Decided via `AskUserQuestion`: isolate to the one accession. Implemented
in `edgar_warehouse/application/warehouse_orchestrator.py`'s
`targeted-resync --scope-type cik` accession loop -- wraps
`_run_accession_resync` in a `try/except` that reuses the existing
`_is_immutable_object_conflict` classification helper (already used by
the daily-artifact-resume path for the identical class of error).
Deliberately narrow: only that specific error class is caught and
skipped; any other exception (network error, real bug, etc.) still
propagates and fails the whole run, exactly as before. Emits a new
`accession_resync_conflict_skipped` event per skip and a
`conflict_skipped_count`/`conflict_skipped_accessions` summary on
`accession_resync_completed`, so a skip is visible in run output/logs,
never silent. `metrics["accessions_conflict_skipped"]` added for
programmatic callers.

Two new unit tests in
`tests/unit/test_targeted_resync_accession_conflict_isolation.py`:
one confirms an immutable-object conflict on one accession (out of
three) doesn't abort the run and the other two still process and merge;
the other confirms a *different* error type on one accession still
aborts the whole run (proving the isolation is narrowly scoped, not a
blanket catch-all). Both verified against the pre-fix code (first test
fails, matching the original bug; second already passed, since it
exercises behavior that didn't change). Full suite green: 1751 passed, 4
skipped, only the pre-existing unrelated `test_go_live_wizard.py`
failure.

Not yet deployed to prod or live-verified with a real conflict --
pending explicit confirmation, matching this workstream's live-action
convention.
