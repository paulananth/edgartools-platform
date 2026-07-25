# 04 — Seed and freeze coverage matrix

Type: research  
Status: resolved  
Blocked by:  

## Question

Using `assets/er-skills-io.md`, `assets/er-edgartools-gap-analysis.md`, `docs/data-architecture.md`, gold schemas, MDM, Neo4j, and Subject Bundle docs: **refine** `coverage-matrix.md` so every cell has a non-blank classification and every **Covered/Partial** cell names the actual product (table/section). List any new data classes discovered. Do not implement code.

## Answer

**Gist:** Coverage matrix frozen with zero blank cells across 9 ER skills × data classes. No cells are **Covered** yet (ER-facing read path + acceptance await ERDP-05); all existing Gold/MDM/Bundle surfaces are **Partial** with product footnotes F1–F12 (`TICKER_REFERENCE`/`mdm_company`, `FILING_*`, bronze/`sec_filing_text`, `SEC_FINANCIAL_DERIVED`/`FACT`, `EARNINGS_RELEASE`, ownership gold + Bundle `insiders`, 13F + `holders_of_subject`, graph/Bundle neighborhood, raw `segment` on facts, `EXECUTIVE_RECORD`, `ACCOUNTING_FLAG`, `subject_features`). Phase-1 Gaps map to ERDP-01…04 (consensus, guidance values, calendar, transcript); non-GAAP values Gap pending enrichment; IR deck / peer comps / segment mart Out of scope phase-1. Market prices, options, Street ratings/PT, macro, news, competitive set/TAM reclassified **External** (firm/vendor join; gold MARKET deferred per map). Workflow state (Excel path, thesis store) remains **N/A**.

**New data classes:** executive/management & pay; accounting forensic scores; pure-SEC subject features; competitive set/TAM/industry; non-SEC news/wire.

**Matrix path:** [`.scratch/er-data-plane/coverage-matrix.md`](../coverage-matrix.md)
