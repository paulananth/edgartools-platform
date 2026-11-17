# sec.ipo onboarding log

## The source

The SEC's own filings, read from the captured submissions documents (`sec.submissions.company/all-76230`, the files
`sec.company` reads): no provider request. The IPO calendars named in the research note (OpenBB, Nasdaq, PageCrawl,
Pineify) are vendors' pages; Nasdaq states its expected dates are estimates from company filings; the note found no
sourcing statement for the others. The filings are the free, authoritative source (operator, 2026-11-17 13:16 ET: "pick free authoritive source").

Research: `.scratch/rebuild-priorities/research/149-174-registration-and-final-prospectus.md` (Rule 424, Form S-1,
"How others model an IPO pipeline").

## Identify

- Source `sec.ipo`, silver only, one table `ipo_filing`; no new kind, no Dataset Contract (no MDM record).
- A stage is a form: draft (DRS, DRS/A), filed (S-1, F-1, S-11), amended (their /A), effective (EFFECT), listed (8-A12B,
  CERT), priced (424B4, 424B1), withdrawn (RW).
- Only a company whose filing list holds an IPO registration (S-1, F-1, S-11 or DRS) has rows: EFFECT, 8-A12B and RW
  are filed for other registrations too.

## Profile (counts only, configured reading)

- A 3,001-document sample of the 76,230 (every 25th, plus the test issuer): 183 companies, 2,919 stage filings, every
  filing date filled, every CIK ten digits; 17.4 s.
- The test issuer's 11 filings read in order: draft (2), filed, amended (2), listed (4), effective, priced.

## Gaps found, and what was done

- `overlap` with a `const` list read null; a `sequence` of `const` values builds the list (READING.md).
- A parallel list's anchor is a column only when named in `fields` (READING.md).
- `pad` takes both `left` and `right`.
- A submissions document's `filings.recent` holds its latest filings only; a company with a long history keeps older
  filings in further pages the capture does not hold, so an old IPO's early stages may be missing.
- EFFECT, 424B and RW are filed for every registration (an S-8, an S-3 shelf). The first reading kept them for any
  company with an IPO registration, so its latest stage could turn "effective" years after it priced (Spec review).
  Now a pass lists every IPO registration's file number (`ipo-registrations.yaml`), and the stage pass keeps these
  forms only for those file numbers: a lookup set, which cuts the stage pass into groups of 16 files.
- 8-A12B and CERT carry the exchange's 001- file number, not the registration's: kept for a company with an IPO
  registration, so a later listing of another class is a "listed" row too.
- A company whose IPO registration has aged out of `filings.recent` gets no rows at all.
- An S-1 is also filed by a listed company to register a resale; its filings read as an IPO registration's.
