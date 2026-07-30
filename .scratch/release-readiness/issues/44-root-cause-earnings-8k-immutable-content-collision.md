# 44 — Root-cause orphaned 8-K bronze writes colliding with the immutable-object guard

Type: research
Status: resolved
Blocked by: (none)

## Question

Ticket 42's Item-2.02 selection fix (see ticket 42's Answer, and the merged fix in
`_is_configured_parser_form`/`_is_item_202_candidate_form`) was re-verified live against prod
2026-07-29 by re-running `bootstrap-batch --cik-list 320193 --artifact-policy all_attachments`
after redeploying the fixed warehouse image. The selection fix itself **works correctly** —
Apple's Item-2.02 earnings 8-Ks are now genuinely selected and SEC-fetched (confirmed via
`artifact_call_started`/`artifact_call_completed` events with real byte counts, e.g.
`aapl-20260430_htm.xml`, the XBRL zip, etc.).

**But every single one of Apple's 45 selected earnings-8-K accessions failed identically** with
`WarehouseRuntimeError("immutable object '.../primary/<doc>.htm' already exists with different
content")` — the new immutability guard added by PR #298 (`fetch_filing_artifacts` writes via
`ObjectStorage`, conditional S3 `PutObject` with `IfNoneMatch: "*"`, byte-compares on conflict).

Live-checked the actual S3 objects directly (not guessed): every colliding primary-document key
(e.g. `warehouse/bronze/filings/sec/cik=320193/accession=0000320193-26-000011/primary/
aapl-20260430.htm`) **already exists** in `edgartools-prod-bronze-690839588395`, written in a
tight ~3-second window on **2026-07-19T20:13:19–22Z** — a single prior bulk-write event that
touched every one of Apple's 8-K primary documents (spot-checked 4 different accessions
spanning 2019–2026, all landed in that same 3-second window). Fetched and inspected the actual
existing bronze content — it's genuine, real inline-XBRL Apple 8-K content (Workiva-generated),
not corrupted or a stub/error page.

**Open questions, not yet answered:**
1. What process wrote these objects on 2026-07-19? `sec_filing_attachment` has zero rows for
   every one of these accessions (confirmed in ticket 42), so whatever wrote them did NOT go
   through `fetch_filing_artifacts`/`_run_configured_form_artifact_pipeline` — some other,
   currently-unidentified bronze-write path independently fetched and stored these documents,
   for all item types (not just item-502/ownership/etc.), without ever registering the
   `sec_filing_attachment` metadata row. A `sec_filing_text` table was noticed to exist in
   silver during this investigation (found via `information_schema.tables`) — ticket 30
   concluded no Snowflake filing-text surface exists, but never checked whether a *silver*
   `sec_filing_text` ingestion path exists and could be this orphaned writer. Not confirmed,
   just the most plausible lead — needs to be checked directly (grep for what writes
   `sec_filing_text`, and whether that code path also writes to the same bronze S3 key
   namespace).
2. Why does re-fetching the same logical document via `fetch_filing_artifacts`/edgartools'
   `get_filing().attachments` path produce **different bytes** than whatever fetched it on
   2026-07-19? Same document, same accession, same primary filename — collision, not a
   different document. Likely a serialization/rendering difference between two different
   edgartools API surfaces (e.g. raw attachment bytes vs. a parsed-then-re-rendered HTML path),
   but not confirmed — the two byte streams were not diffed in this pass.
3. Does this collision affect only Apple, or every company whose 8-Ks were touched by
   whatever ran on 2026-07-19? If it's universal, the Item-2.02 fix (ticket 42) is necessary
   but not sufficient — every earnings 8-K in prod would need this orphaned-write collision
   resolved (likely via a `--force` repair pass, once the content discrepancy itself is
   understood, not blindly) before `sec_earnings_release` can actually populate.

**Not attempted in this ticket:** identifying the exact 2026-07-19 writer, diffing the two byte
streams, or any repair action. This is a research ticket — investigate before deciding a fix.
Blocks ticket 42's F5 backfill from actually landing real earnings-release rows even with the
selection bug fixed.

## Answer

Full findings, method, and live-reproduced evidence in the sibling file
`issues/44-research-findings.md`. All three open questions answered with direct evidence, not
speculation:

1. **Writer:** the 2026-07-19T20:13:19–22Z timestamp is an **S3-copy artifact**, not a fetch
   time — it's from the documented `prodb→prod` production cutover
   (`docs/prodb-to-prod-promotion.md`, `.scratch/prodb-prod-cutover/issues/02-*.md`): a
   server-side `aws s3 sync` of the entire `edgartools-prodb-bronze` bucket into canonical prod
   on that exact date. `aws s3 sync` does not preserve source `LastModified`, which fully
   explains the "single ~3-second bulk-write burst spanning many filing years" anomaly — that's
   what a bulk key-preserving copy looks like, not per-filing chronological writes. The *original*
   prodb-era write (before the copy) was most likely an ad-hoc, form-agnostic `targeted_resync`
   run against Apple specifically — the only code path (`_run_accession_resync`) that ever
   fetches filing attachments without going through the Item-2.02-blind
   `_is_configured_parser_form` gate, and Apple is independently documented elsewhere in this
   workstream as the dedicated single-CIK smoke-test subject. Established by elimination of every
   other call path in the codebase, not by a surviving execution log (prodb's own history no
   longer exists to check directly — `edgartools-prodb-bronze` bucket confirmed torn down).
2. **Byte diff:** exactly **one trailing-newline byte** (`0x0a`), fully reproduced live: a raw
   `curl` fetch of the same SEC URL is byte-identical (sha256 match) to the existing bronze
   object; running the actual installed `edgartools==5.30.0` through the same code path
   `bronze_filing_artifacts.py` uses produces content exactly 1 byte shorter, due to an explicit
   `.strip()` in edgartools' `get_content_between_tags()` (`edgar/sgml/tools.py:49,56`). This
   became collision-prone specifically because commit `f6c40f1` (ticket 06, "edgartools-only
   filing document gateway," 2026-07-17 — two days *before* the migration) removed the old
   raw-HTTP `download_bytes` fast path that had produced byte-exact content; every capture since
   then goes through the `.strip()`-affected `attachment.content` path instead. The 2026-07-19
   migration copied in bytes captured under the older, byte-exact mechanism; PR #299 (2026-07-29)
   triggered the first-ever fetch attempt through the newer path for these accessions, which
   collides with what's already there.
3. **Scope:** **empirically Apple-specific, not universal.** Of 53,649 non-Apple Item-2.02 8-K
   accessions in prod silver, 99.5% were never fetched at all (expected, since Item-2.02 selection
   was broken until today); a live sample of 32 of those (7 recent + 25 random, 2005–2026) found
   **zero** pre-existing bronze objects to collide with — a fresh fetch for any of them would
   simply succeed. All 45 of Apple's accessions, by contrast, do have pre-existing bronze content.
   Ticket 42's F5 backfill is not blocked at the whole-universe level by this — it needs a scoped
   repair for Apple's 45 accessions specifically (the pilot CIK), not a blanket assumption that
   every earnings 8-K in prod needs this treatment.

**Adjacent finding, outside this ticket's three questions but material to release-readiness:**
between 2026-07-19 (migration) and 2026-07-28 (PR #298's immutability guard deployed), any
re-fetch of a migrated pre-existing bronze object through the post-ticket-06 pipeline would have
hit this same 1-byte-short content — but with no guard in place yet, the old `write_bytes` would
have **silently overwritten** the byte-exact migrated original with the `.strip()`-normalized
version, no error, no application-level audit trail. Whether this actually happened to any *other*
migrated, already-registered accession in that 9-day window was not checked in this pass —
graduated into ticket 47.

**Bottom line:** root cause is understood, not just described — a same-logical-document,
whitespace-normalization mismatch between two historical capture mechanisms, surfaced by three
independently correct changes landing in sequence (ticket 06's gateway consolidation, the July 19
migration, PR #298's immutability guard). Not corruption, not a wrong-document collision, not a
universal blocker. No repair action taken in this research pass — graduated into ticket 46 (decide
how to repair Apple's 45 accessions).

Status: resolved.
