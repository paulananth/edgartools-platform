# 02 — 10-K scope: metadata vs. structured document parse

Type: grilling
Status: resolved

## Question

10-K filing *metadata* (accession, filing date, period) is already captured
for free for every CIK via the standard submissions-based filing capture
(`sec_company_filing` rows exist regardless of form-specific parsing).

Does "load 10-K" mean:

(a) Nothing beyond that existing metadata capture — the actual financial
    content comes entirely from the `entity-facts` (XBRL companyfacts)
    ingestion covered by "fundamentals," or

(b) A dedicated 10-K document/section parse (e.g., business description,
    MD&A, risk factors, item-level text) beyond what the companyfacts XBRL
    API already provides — which would need new parsing work, likely via
    `edgar.xbrl` / `edgar.files` document APIs already used elsewhere in this
    repo (see `scripts/batch/batch_test_10ks10qs.py`, `batch_xbrl_stitching.py`
    for existing patterns to draw from).

## Blocked by

None — can start immediately.

## Answer

(a) — filing metadata (already free via `sec_company_filing`) plus XBRL
companyfacts financial facts (already covered by "fundamentals"/`entity-facts`)
is the full scope. No dedicated 10-K document/section text parse (MD&A, risk
factors, business description) — no confirmed consumer for narrative text
exists yet, and building it now would be speculative new parsing work with
no named need.
