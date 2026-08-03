# Decide whether to exclude binary presentation artifacts from the default fetch policy

Type: grilling
Status: open

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

(pending)
