# 254: The IPO pipeline from the SEC's own filings

Priority: 254. Map: [Rebuild priorities](../map.md). Opened 2026-11-17 13:16 ET (operator: "Create a pipeline for ipo using skills and config only … pick free authoritive source").

Type: task (configuration only). Status: resolved. Blocked by: none. Related: 149 (`sec.registration`), 174 (`sec.prospectus`).

## Question

Which free, authoritative source gives a company's IPO stages, and can a pipeline land them with configuration only?

## Answer

The SEC's own filings, already captured in the submissions documents. The calendars (OpenBB, Nasdaq, PageCrawl,
Pineify) are compiled from them; Nasdaq states its dates are estimates. Each stage is a dated filing: draft (DRS),
filed (S-1, F-1, S-11), amended, effective (EFFECT), listed (8-A12B, CERT), priced (424B4, 424B1), withdrawn (RW).
Log: `.scratch/onboarding/sec.ipo/onboarding-log.md`.

## Parts

- [x] 2026-11-17 13:16 ET Source chosen: the SEC submissions documents, captured; no provider request (onboarding log, "The source")
- [x] 2026-11-17 13:16 ET `sec.ipo`: source, reading `ipo-filings.yaml` and silver spec `silver-filing.yaml` (`ipo_filing`, one row a filing and CIK, linked to the Company by CIK); `rules check` ok; configuration only
- [x] 2026-11-17 13:16 ET The reading on invented documents: `tests/engine/test_ipo_filings_reading.py` (3 tests: each stage, the CIK with its zeros, a company with no IPO registration gives none)
- [x] 2026-11-17 13:16 ET Mapping Document generated; `sec.ipo` in the source sequence, the load chain (`ipo`, capture `sec.submissions.company/all-76230`) and the tests that pin the source list
- [x] 2026-11-17 13:16 ET The proof on a fresh disposable store (`ipo`): the test issuer's Company mastered from its one-filer slice, then `sec.ipo` over the whole capture: 76,230 documents in about 6 minutes (2 workers, 2 bundles at once); 73,866 stage filings of 4,732 companies (amended 19,950, draft 8,365, effective 21,775, filed 9,934, listed 7,508, priced 4,928, withdrawn 1,406), no filing date empty; 305 companies priced from 2026; the 11 rows of the one Company mastered in that store linked to it. A second pass: "0 documents loaded, 76230 already loaded before" in 47 s
- [x] 2026-11-17 13:16 ET Stores and containers the proof leaves are removed: `local-test-stores.py stop ipo`
- [x] 2026-11-17 13:16 ET Learning → skill: `data-platform` READING.md (a parallel list's anchor is a column only when named; a fixed list for `overlap` is a `sequence`)
