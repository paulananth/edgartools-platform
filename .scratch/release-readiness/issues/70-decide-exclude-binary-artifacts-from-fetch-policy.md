# Decide whether to exclude binary presentation artifacts from the default fetch policy

Type: grilling
Status: resolved

## Question

Found while investigating [ticket 69](69-reuse-s3-client-in-artifact-fetch-loop.md)
(artifact-fetch pipeline latency): the default `--artifact-policy all_attachments`
downloads and stores *every* document attached to a filing, including binary
investor-presentation images that no parser in this repo reads.

Live example from `daily-incremental-ticket67-verify-1785709701`: accession
`0000719220-26-000090` attached 5 real documents (`.htm`, `.xsd`, `_lab.xml`,
`_pre.xml`, plus the primary doc) and **24 individual JPG slides**
(`a2q26stbainvestorpresent001.jpg` through `024.jpg`, 46KB-242KB each) from an
investor presentation exhibit. At current per-document cost, the JPGs alone were
~4.3 of the filing's ~5.2 total seconds -- 83% of one filing's fetch time, for
content nothing downstream consumes (this repo's parsers cover ownership XML, ADV,
Item 5.02 8-K, and XBRL -- none read image exhibits).

`--artifact-policy` already exists as the control surface (`all_attachments` vs.
narrower policies -- see `edgar_warehouse/application/commands` for current
values). Excluding binary presentation content is plausibly a bigger latency win
than ticket 69's client-reuse fix, and would also reduce the S3 storage growth
[ticket 65](65-clean-up-orphaned-staged-promotion-blobs.md) is tracking.

Decide:
1. Should the default policy stop fetching binary presentation/image attachments
   (jpg/png/pdf-slide-deck-style exhibits), or is "capture everything SEC attaches"
   a deliberate completeness guarantee worth keeping regardless of parser coverage?
2. If narrowing: what's the exact exclusion rule (file extension? MIME type?
   `is_primary` plus a small allowlist of structured-data extensions?), and does it
   apply to new fetches only (go-forward, matching the `_staging/`->`silverstage/`
   rename precedent) or is there any retroactive cleanup expectation?
3. Does this interact with CLAUDE.md's "SEC data idempotency" / additive-immutable
   bronze convention -- i.e. is *not capturing* something at all a different kind
   of decision than *how* already-captured content is treated?

This is a HITL grilling ticket -- per `advisor`'s explicit recommendation while
resolving ticket 69, this is a genuine operator trade-off (completeness vs. cost),
not an engineering judgment call, and should not be bundled into the pure
performance fix.

## Answer

Resolved via HITL exchange with the operator (2026-08-03):

1. **Yes, exclude by default.** "Capture everything SEC attaches" is not kept as an
   unconditional guarantee where the content is binary presentation material no
   parser reads.
2. **Rule: image extensions only** — `.jpg`/`.jpeg`/`.png`/`.gif`, the narrowest
   option. PDFs, zips, XBRL, and every other attachment type are unaffected.
   The primary document is *never* excluded, regardless of its own extension.
3. **Both go-forward and retroactive.** The fetch-policy change applies
   immediately to new fetches; a follow-up task to find and remove already-
   captured binary exhibits from S3 bronze was also requested — filed separately
   as [ticket 71](71-cleanup-existing-binary-attachments-in-bronze.md) rather than
   done inline here, since a bulk-delete against prod S3 needs its own scoped
   investigation (how many objects, how much data, confirmation nothing already
   depends on them) before executing anything destructive.

## Implementation

`edgar_warehouse/bronze_filing_artifacts.py`: new `_is_excluded_binary_attachment`
helper (checked against `document_name`'s extension, case-insensitive; always
`False` for `is_primary` rows) filters `attachment_rows` right after
`_map_edgartools_attachments` returns, before the fetch loop -- excluded documents
are never downloaded, never written to S3, and never registered in
`sec_filing_attachment` at all (not "captured but marked skipped"). A new
`binary_attachments_excluded` event (matching this session's established
per-call/per-table event-logging convention from tickets 67-69) logs the excluded
document names and count per accession for observability.

Two new regression tests in `tests/unit/test_loader_idempotency.py`:
- `test_binary_image_exhibits_are_excluded_from_fetch_and_registry` — a filing with
  a primary `.htm`, a real `.xsd`, and two image exhibits (`.jpg`, uppercase
  `.PNG`) fetches and registers only the two real documents.
- `test_primary_document_is_never_excluded_even_with_an_image_extension` — a
  filing whose primary document itself has a `.jpg` extension is still fetched
  and registered (the one document every filing is required to have is never
  dropped by this rule).

Both pass; full suite validated alongside the commit (see commit message for exact
count).

## Done when

Done — decision made with the operator, implemented, tested. Not yet deployed to
prod as of this entry. Retroactive cleanup is out of this ticket's scope, tracked
separately in ticket 71.
