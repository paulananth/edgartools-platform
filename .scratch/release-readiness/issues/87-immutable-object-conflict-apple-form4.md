Type: task
Status: open

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
