# 254: The IPO pipeline from the SEC's own filings

Priority: 254. Map: [Rebuild priorities](../map.md). Opened 2026-11-17 13:16 ET (operator: "Create a pipeline for ipo using skills and config only … pick free authoritive source").

Type: task (configuration only). Status: resolved. Blocked by: none. Related: 149 (`sec.registration`), 174 (`sec.prospectus`).

## Question

Which free, authoritative source gives a company's IPO stages, and can a pipeline land them with configuration only?

## Answer

The SEC's own filings, already captured in the submissions documents: free, and the record each stage is. The
calendars named (OpenBB, Nasdaq, PageCrawl, Pineify) are vendors' pages; Nasdaq states its expected dates are
estimates from company filings, and the research note found no sourcing statement for the others. Each stage is a dated filing: draft (DRS),
filed (S-1, F-1, S-11), amended, effective (EFFECT), listed (8-A12B, CERT), priced (424B4, 424B1), withdrawn (RW).
Log: `.scratch/onboarding/sec.ipo/onboarding-log.md`.

## Parts

- [x] 2026-11-17 13:16 ET Source chosen: the SEC submissions documents, captured; no provider request (onboarding log, "The source")
- [x] 2026-11-17 13:42 ET `sec.ipo`: source, reading `ipo-filings.yaml` and silver spec `silver-filing.yaml` (`ipo_filing`, one row a filing and CIK, linked to the Company by CIK); `rules check` ok; configuration only
- [x] 2026-11-17 13:42 ET The reading on invented documents: `tests/engine/test_ipo_filings_reading.py` (5 tests: each stage, the CIK with its zeros, a company with no IPO registration gives none, and the CIK is the record key `sec.company.v1` makes from the same CIK, so the link finds the Company; a withdrawal of the IPO registration is its withdrawn stage)
- [x] 2026-11-17 13:42 ET Mapping Document generated; `rules mapdoc check` clean; `sec.ipo` in the source sequence, the load chain (`ipo`, capture `sec.submissions.company/all-76230`) and the tests that pin the source list
- [x] 2026-11-17 13:42 ET The proof on a fresh disposable store (`ipo2`), on the reading the Spec review corrected: the test issuer's Company mastered from its one-filer slice, then `sec.ipo` over the whole capture (149 bundles; about 8 minutes at 2 bundles once a 3-minute trial had loaded 22): 63,325 stage filings of 4,752 companies (amended 19,950, draft 8,365, effective 12,235, filed 9,934, listed 7,508, priced 4,496, withdrawn 837), no filing date empty; 296 companies priced from 2026; the 11 rows of the one Company mastered in that store linked to it. A second pass: "0 documents loaded, 76230 already loaded before". The first reading, which kept every EFFECT, 424B and RW of a company with an IPO registration, landed 9,540 more effective, 432 more priced and 569 more withdrawn rows on the first store (`ipo`)
- [x] 2026-11-17 13:42 ET Spec review fixed: effective, priced and withdrawn kept only for an IPO registration's own file number (`ipo-registrations.yaml`, a same-file lookup). Failed before: `test_each_stage_filing_of_an_ipo_registration_is_a_row_with_its_stage_date_and_file_number` (the unrelated RW and the later EFFECT of an S-8 read as stages)
- [x] 2026-11-17 13:42 ET Stores and containers the proof leaves are removed: `local-test-stores.py stop ipo` and `stop ipo2`
- [ ] ~~Each company's latest stage as one row~~ deferred to 212: a query over `silver.ipo_filing` today; a gold model once a consumer asks for it
- [x] 2026-11-17 13:42 ET Learning → skill: `data-platform` READING.md (a parallel list's anchor is a column only when named; a fixed list for `overlap` is a `sequence`; a same-file lookup between two passes)
