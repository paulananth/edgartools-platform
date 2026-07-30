# 30 — Product-ready promotion criteria for Filing / research text (F3)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Filing/research text is promoted from Partial to Covered in the coverage matrix? Concrete
platform surface per the matrix footnote: bronze filing primary/attachments; silver/text
`sec_filing_text` (normalized text path). Matrix note: "Text projection is **manual/backfill-
only** (`targeted-resync --include-text`); not automated agent product." This is likely the
hardest F1–F12 product to promote as-is, since the matrix explicitly flags it as manual/backfill,
not an automated pipeline — the checklist may need to conclude "not promotable without an
automation change" rather than assume promotion is reachable purely via acceptance criteria.

Write this as a numbered list of criteria (or, if warranted, an explicit finding that promotion
requires a prerequisite automation change before any checklist applies), grounded in real
schema/code, cross-checked against ticket 27's ER-skill survey findings for this product,
adversarially stress-tested for what a naive checklist would miss — following the method of
`erdp-coverage-promotion` tickets 03–06.

## Answer

### Finding: not promotable — no Snowflake surface exists at all, not just an undocumented one

This is a step further than tickets 28/29's "data healthy, read path undocumented" gate. Live
check: `SELECT table_schema, table_name FROM EDGARTOOLS_PROD.INFORMATION_SCHEMA.TABLES WHERE
table_name ILIKE '%TEXT%'` returns **zero rows** — there is no `sec_filing_text` (or any
filing-text) table anywhere in `EDGARTOOLS_SOURCE` or `EDGARTOOLS_GOLD`. The matrix footnote's
own framing is accurate and current: this is a **manual/backfill-only** silver artifact
(`targeted-resync --include-text`), never exported to Snowflake at all. There is nothing an ER
skill could query even if a Subject Bundle section were written for it.

Per ticket 27's survey, only **one** skill (initiating-coverage, Task 1) has a real, explicit
prose-mining need — reading business description/risk factors/MD&A content from the latest
10-K, single company, no history/freshness bar. The other 5 skills the matrix marks Partial on
this row (catalyst-calendar, earnings-preview, morning-note, earnings-analysis, sector-overview)
reference filing *events* (does a filing exist, when), which is F2's (Filings metadata)
territory, not F3's — the matrix's own classification notes already frame it this way
(`coverage-matrix.md:147`), so this isn't a mismatch to fix, just a scope boundary to preserve.

### This ticket does not resolve with a numbered checklist

Per the ticket's own framing and confirmed by this grounding: promotion requires a prerequisite
**automation and Snowflake-export change** before any acceptance criteria apply — there is no
partial-credit path (e.g., "50% coverage of the eligible subset") when the product doesn't exist
as a queryable table at all. Recording the shape the eventual checklist should take, once that
prerequisite exists:

1. A `sec_filing_text` (or equivalent) table must exist in `EDGARTOOLS_SOURCE`/`EDGARTOOLS_GOLD`,
   fed by an **automated** pipeline, not `targeted-resync --include-text`'s manual/backfill path.
2. Given only initiating-coverage Task 1 has a real, stated need, and it's single-company/
   latest-10-K/no-history — the eventual product only needs to guarantee the **latest** annual
   filing's text is available on request, not a historical sweep or coverage-universe-wide
   ingestion. A future checklist should resist scope-creeping this into a full-text-search
   product no skill actually asked for.
3. A documented Subject Bundle section (or equivalent) naming the specific text sections
   (business description, risk factors, MD&A) — the same "documented read path" gate as tickets
   28/29, applied once the data itself exists.

**Recommendation:** do not attempt to promote F3 until a separate, dedicated task ticket
automates filing-text capture end-to-end (bronze → silver → Snowflake export). This ticket's
job — determining whether promotion is reachable via acceptance criteria alone — is answered:
**no**, a prerequisite build is required first, consistent with how this ticket was originally
scoped.
