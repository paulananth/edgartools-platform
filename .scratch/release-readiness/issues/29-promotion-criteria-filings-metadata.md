# 29 — Product-ready promotion criteria for Filings metadata (F2)

Type: grilling
Status: resolved
Blocked by: 27

## Question

What is the complete, product-ready set of acceptance criteria that must all pass before
Filings metadata is promoted from Partial to Covered in the coverage matrix? Concrete platform
surface per the matrix footnote: gold `FILING_ACTIVITY`, `FILING_DETAIL`, `dim_filing`; silver
`sec_company_filing`, daily index `stg_daily_index_filing`. Matrix note: "Form, accession,
filing/report dates, XBRL flags, primary doc; ER index section not yet on Subject Bundle."

Write this as a numbered list of criteria (coverage breadth, form-type completeness,
accession/date correctness, XBRL-flag accuracy, primary-doc resolvability, Subject Bundle
index-section gap disposition), each with a concrete, checkable acceptance query or procedure,
following the exact method and rigor of `erdp-coverage-promotion` tickets 03–06 — grounded in
real schema, cross-checked against ticket 27's ER-skill survey findings for this product,
adversarially stress-tested for what a naive checklist would miss.

## Answer

Grounded in the real schema (`EDGARTOOLS_GOLD.FILING_ACTIVITY`, `FILING_DETAIL` — live-checked
2026-07-29) and ticket 27's ER-skill survey findings (F2 section). Every criterion below must
pass. Two adversarial findings shaped this checklist away from a naive version: (a) `dim_filing`
(named in the matrix footnote) does not exist as a Snowflake object at all — the real gold
surface is only `FILING_ACTIVITY`/`FILING_DETAIL`, near-identical row-for-row (2,713,414 rows
each); (b) of the 9 ER skills, only **2** (earnings-analysis, initiating-coverage) have an
explicit, textual need for filing metadata as such — the other 7 reference filing-*triggered
events* (M&A, management change) never the metadata fields themselves, so this checklist is
calibrated to what those two skills actually demand, not an assumed need across all 9.

1. **A documented read path must exist — same shape as ticket 28's Identity gate, and it fails
   today for the same reason.** Per the matrix's own definition, "Covered" requires a documented
   ER read path, not just healthy data in a gold table. Checked `docs/subject-bundle-read.md`
   directly: it has **zero** dedicated filing-index section — the only "accession" reference is
   as internal provenance for the unrelated `insiders` section. This matches the matrix's own
   footnote ("ER index section not yet on Subject Bundle") and confirms it's still current.
   **This criterion fails until a filing-index section is added to the Subject Bundle (or an
   equivalent documented ER-facing contract) — the underlying data is otherwise healthy (see
   criteria 2-7), but "Covered" cannot be claimed on data health alone.**
   Acceptance: a filing-index section (form, accession, filing_date, report_date, is_xbrl per
   the grain earnings-analysis actually uses) is named in `docs/subject-bundle-read.md` or an
   equivalent documented contract, with a Bundle Coverage Flag (present/empty/unavailable).

2. **Coverage — scoped to the filing-eligible universe, same lesson as ticket 28.** Do not gate
   on 100% of the full active/tracked universe (26,300 active CIKs, ~89% of which are non-issuer
   types per ticket 40's entity_type breakdown and structurally never file 10-Ks). Bar: **≥95%**
   of active `entity_type='operating'` companies have at least one 10-K or
   10-Q filing in `FILING_ACTIVITY`. Live check: 2,429 of 2,462 (98.7%) — comfortably clears a
   95% bar with room for the ~33 gap (plausibly recent IPOs pending a first annual report, not
   independently verified here).
   Acceptance: `SELECT COUNT(DISTINCT fa.cik) * 1.0 / COUNT(DISTINCT c.cik) >= 0.95 FROM COMPANY
   c LEFT JOIN FILING_ACTIVITY fa ON fa.cik = c.cik AND fa.form IN ('10-K','10-Q') WHERE
   c.tracking_status = 'active' AND c.entity_type = 'operating'`.

3. **No full-tracked-universe coverage criterion exists, and none should be added.** Explicit
   negative criterion mirroring ticket 28's: a future revision requiring "X% of all active
   companies have filings" (unscoped to the operating/issuer subset) is wrong on its face.

4. **The 4 explicitly-needed form types are present with real volume.** earnings-analysis and
   initiating-coverage together name 10-K, 10-Q, 8-K, and DEF 14A as the forms they read (no
   other form type is named by any surveyed skill). Live counts confirm all four present at
   real scale: 8-K 203,094 · 10-Q 55,973 · 10-K 20,749 · DEF 14A 17,687.
   Acceptance: `SELECT form, COUNT(*) FROM FILING_ACTIVITY WHERE form IN ('10-K','10-Q','8-K','DEF 14A') GROUP BY form` returns all 4 forms with `COUNT(*) > 0`.

5. **Accession-number format validity (EDGAR-link resolvability proxy).** No skill needs a
   stored primary-document URL column — earnings-analysis's own quoted link format
   (`https://www.sec.gov/cgi-bin/viewer?accession=[accession-number]`) is computed from
   `accession_number` alone at read time, not a separate stored field. The correctness bar is
   therefore that every `accession_number` is a real, correctly-shaped SEC accession (so the
   computed link actually resolves). Live check: 0 of 2,713,414 rows fail
   `^[0-9]{10}-[0-9]{2}-[0-9]{6}$` — 100% valid today.
   Acceptance: `SELECT COUNT(*) FROM FILING_ACTIVITY WHERE NOT REGEXP_LIKE(accession_number,
   '^[0-9]{10}-[0-9]{2}-[0-9]{6}$')` = 0.

6. **Join integrity to `COMPANY`.** 100% of `FILING_ACTIVITY`/`FILING_DETAIL` rows resolve to a
   real company on `cik`. Live check: 0 orphans today.
   Acceptance: `SELECT COUNT(*) FROM FILING_ACTIVITY fa LEFT JOIN COMPANY c ON c.cik = fa.cik
   WHERE c.cik IS NULL` = 0 (repeat for `FILING_DETAIL`).

7. **Filing-date freshness for actively-reporting companies, bounded by real SEC filing
   deadlines — not an arbitrary window.** Neither earnings-analysis nor initiating-coverage
   states a numeric freshness bound directly, but both explicitly want the *most recent* 10-K
   or 10-Q, and earnings-analysis's own correctness gate implies filings must track actual
   reporting cadence, not go silently stale. Bar: for any `entity_type='operating'` company with
   a 10-K/10-Q in the last 3 fiscal years, no gap between consecutive expected filings exceeds
   **120 days** past the relevant SEC deadline (10-Q: 40/45 days after quarter-end depending on
   filer size; 10-K: 60/75/90 days after fiscal year-end) — a generous multiple of the deadline
   itself, catching a genuinely stalled pipeline, not chasing same-day freshness no skill asked
   for.

**Cross-reference, not a duplicate criterion:** earnings-analysis's stated hard, checklist-gated
correctness bar ("10-Q/10-K filing date: _______ MUST be same quarter as release") and its named
RED FLAG ("materials show different quarters") are fundamentally a cross-check between this
product (F2) and `EARNINGS_RELEASE`/F5 (Earnings 8-K GAAP snapshot) — not verifiable from F2's
own schema alone. Ticket 32 (F5's promotion checklist) should own the actual acceptance query
for this; this ticket only flags that the dependency exists so it isn't silently dropped by
either ticket.

**Explicitly not required for promotion:**
- **XBRL-flag correctness against actual XBRL parse results.** The matrix footnote names "XBRL
  flags" as part of the platform surface, and `IS_XBRL` is ~100% populated (2,713,207 of
  2,713,414 rows) — but per ticket 27's survey, **no skill anywhere asks for XBRL-flag-level
  filing metadata**. Population health is worth a cheap sanity check (already passing), but this
  checklist does not require verifying `IS_XBRL`'s correctness against real XBRL parse output —
  that would be gating on a field no ER consumer actually reads.
- **A stored primary-document URL/filename column.** No skill needs one beyond the
  accession-derived viewer link (criterion 5).
- **Coverage-universe-wide filing sweeps.** Every skill's stated need is per-request/
  single-company (latest filing lookup), never a sweep across the whole tracked universe.
- **Filing-index section coverage for non-operating entity types** (insiders, advisers,
  broker-dealers) — they generally don't file 10-Ks/10-Qs/8-Ks as issuers; F2's scope is the
  operating/issuer subset, same reasoning as criterion 2.

**Known residual risk, not closable by any acceptance query:** criterion 1 (documented read
path) is a hard gate on work that has not happened yet, same as ticket 28. Until a filing-index
section lands on the Subject Bundle (or equivalent), Filings metadata remains **not promotable
to Covered**, regardless of how well criteria 2-7 score against the currently-healthy gold
data. Also: `FILING_ACTIVITY` and `FILING_DETAIL` are row-for-row identical in count
(2,713,414) with almost entirely overlapping columns (`FILING_DETAIL` adds only `SIZE`) — this
looks like schema duplication rather than two genuinely distinct products, but reconciling that
is a data-modeling question outside this checklist's scope, not a promotion blocker by itself.
