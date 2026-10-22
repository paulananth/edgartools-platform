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
- [ ] The operator approves research 04's lists
- [ ] Each chosen company's cases checked by hand against its facts (a differing figure is not always a restatement)
- [ ] Open definition questions, one at a time: the ROIC tax rate when pretax income is zero or negative; average-balance returns when the start balance is missing; which measures are not meaningful for financial services beyond the four ruled
- [ ] The oracle: every line item and measure by the rulings (35, 38, 39, 42), each value with every candidate fact tried and why the chosen one won; local key, sha256 in the repo
- [ ] Every null reason appears at least once (no concept filed, missing year, fiscal year changed, not meaningful, mixed currencies, not meaningful for financial services, a denominator of zero or less)
- [ ] One value per hard case recomputed by hand from the raw facts, recorded here
- [ ] PR, CI green, merge
- [ ] Learning → skill
