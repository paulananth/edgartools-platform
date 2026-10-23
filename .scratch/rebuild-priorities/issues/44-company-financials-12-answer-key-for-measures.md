# 12 A hand-computed answer key for the measures

Priority: 44, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/12-answer-key-for-measures.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: in progress (Claude, 2026-10-22; operator: "Resume financials (44)"). Blocked by: 39 (resolved). Map: [map](../../company-financials/map.md).

## Question

Before any build: for cohort companies, as few as cover the hard cases (a 52/53-week year, a non-December year end, a changed fiscal year end, a restatement, a stock split, a negative base, a non-USD filer, an IFRS filer, a financial-services filer, mixed currencies; added 2026-10-22 from tickets 35 and 42), compute by hand from the long-form facts each line item and each measure by ticket 07's definitions, with the facts used. Written and committed before the build tickets start (as Trials A and B were).

## The key stays local; the repo holds its method and its sha256

The repository is public, so the key's figures and company names stay in the
local proving folder beside the captured company facts. The repo holds the
method, the oracle, the hard cases described without names, the coverage
counts and the key file's sha256, so ticket 48 scores against that exact key.

## Checklist

- [x] Exact values: the long-form table kept each figure as a float (`val DOUBLE`); `to_facts_parquet.py` now keeps the filed text (`parse_float=str`), regenerated locally: 5,134,979 facts, the one figure past 17 significant digits now exact (operator, 2026-10-22: "Fix the data type issue") (2026-10-22 16:43 ET)
- [x] How long a year is: "364–371 days" counts a period's first and last day; by subtraction the cohort's years are 363 (52-week, 31 filers), 364, 365 and 370 (53-week, 28 filers), so only that reading keeps both 52- and 53-week years (skill clarified) (2026-10-22 16:43 ET)
- [x] Hard cases found (`answer-key/find_cases.py`, counts only): 52/53-week 28 companies, non-December 68, changed year end 16, restatement 133, stock split 43, negative base 173, non-USD 19, IFRS 6, financial services 42, mixed currencies 18; three companies cover all ten (local file) (2026-10-22 16:43 ET)
- [x] IFRS concept lists proposed from the IFRS taxonomy and the cohort's 6 IFRS filers (operator: "Propose from IFRS taxonomy (Recommended)"): research 04 (2026-10-22 16:43 ET)
- [x] The operator approves research 04's lists: "Approve the lists (Recommended)" (2026-10-22 16:55 ET)
- [x] The line items as an RDM code set crosswalked to their concepts; the order and fallbacks stay rules (operator, 2026-10-22: "Yes, code set + crosswalk (Recommended)"; ticket 46 scope) (2026-10-22 17:30 ET)
- [x] Fiscal years keyed by Compustat's FYEAR: a year ending January to May belongs to the previous calendar year (operator, 2026-10-22: "Compustat FYEAR (Recommended)"); found by the oracle: under "the calendar year of the end" a 52/53-week year ending 1-3 January left gaps and false year-end changes (2026-10-22 17:30 ET)
- [x] The chosen companies' cases read from their facts: A covers changed year ends (two), mixed currencies and a move from IFRS to US GAAP; B covers 52/53-week years, a changed year end and a stock split; C is a financial-services filer reporting under IFRS outside USD with a non-December year end. A year's taxonomy is the one most facts of its latest filing use (a filer on IFRS files a stray us-gaap fact) (2026-10-22 17:30 ET)
- [x] Each chosen company's restatement and stock split confirmed by hand from its filings' copies (`answer-key/hand_check.py`, every filed copy of the period re-read from the raw facts): the two restating filers have 3 and 21 line-item years with differing filed copies, the key takes the latest-filed copy in all 24; the split filer shows the split as a whole-number ratio between its copies (share counts up, per-share figures down by the same factor) and the key keeps the split-adjusted latest copy in all 68 line-item years whose copies differ (2026-10-22 21:19 ET)
- [x] ROIC's tax rate when pretax income is zero or negative, or the effective rate falls outside 0–100%: the filer's country's statutory rate (operator, 2026-10-22: "Statutory rate (new source)"), held in RDM from the OECD table ("RDM, OECD source (Recommended)"; ticket [133](133-statutory-tax-rates-in-rdm.md)); until it exists the key marks those years "waiting for the statutory rate" (2026-10-22 16:57 ET)
- [x] Average-balance returns when the prior balance is missing: null, "missing year" (or "fiscal year changed"), as CAGR's endpoints (operator, 2026-10-22: "Null, \"missing year\" (Recommended)") (2026-10-22 16:57 ET)
- [x] Not meaningful for financial services: gross margin, ROIC, total debt and its ratios, and the current ratio (operator, 2026-10-22: "The four, plus current ratio (Recommended)"); operating margin follows its inputs (2026-10-22 16:57 ET)
- [x] The oracle (`answer-key/oracle.py`): 3 companies, 40 fiscal years, every line item with every candidate fact tried; measures 867 with a value; local key `proving/company-facts/answer-key.json`, sha256 `3274559d67f5f55e0f2783f2ad24f39af46946c98f6786f661f4814b361ee804` (2026-10-22 17:30 ET)
- [x] Every null reason appears: no concept filed 224, missing year 311, fiscal year changed 26, not meaningful 85, mixed currencies 6, not meaningful for financial services 60, denominator zero or less 5; and "waiting for the statutory rate" 16 (ticket 133) (2026-10-22 17:30 ET)
- [x] One value per hard case recomputed by hand from the raw facts (`answer-key/recompute.py`; each input the latest-filed raw copy, the arithmetic written out): 10 of 10 agree, namely a 371-day year's 1-year revenue CAGR, diluted EPS CAGR across the split, a CAGR not meaningful on a negative end, a window beside the year-end change, net margin on restated copies, ROE on the prior year end's equity, revenue kept in its reporting currency, revenue from `ifrs-full`, gross margin not meaningful for the bank, and a CAGR across two currencies null as mixed currencies (2026-10-22 21:19 ET)
- [x] Found by the recomputation: `oracle.py`'s `missing()` blamed the later year when the earlier year existed without its figure, so a window two years before a year-end change read "fiscal year changed". Fixed (the gap is always the earlier year; callers ask only once the later figure is known); key regenerated: 15 null reasons move (10 to "missing year", 5 to "fiscal year changed", each beside a real change), no value and no line item moves; new local key sha256 `dece38e588223e2172eb7725d7772a87a421ab4e22e1bfc68d204ee11d010bee`; reasons now missing year 316, fiscal year changed 21, the rest unchanged (2026-10-22 21:19 ET)
- [ ] PR, CI green, merge
- [ ] Learning → skill
