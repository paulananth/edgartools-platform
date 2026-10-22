# 03 As reported or as restated: the time model

Priority: 35, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/03-time-model-as-reported-or-restated.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-21 21:10 ET, operator rulings below). Blocked by: 33. Map: [map](../../company-financials/map.md).

## Question

A fact for a fiscal year can be reported several times (the original 10-K, then later 10-Ks restating it). Which value does a CAGR use: the latest restated, the first reported, or both kept (as of the fiscal period, as at the filing date) with the latest as the default? What are the period keys (fiscal year and period from `fy`/`fp`, or the period's start and end dates), and how are 52/53-week years and changed fiscal year ends handled?

From research: the two differ for 152 of 307 filers on net income, and on every per-share series across a split (only the latest-filed series is consistent); years are keyed on the period end, not `fy` (sections 1 and 2).

## Checklist

- [x] Which figure silver keeps and CAGR uses (operator, 2026-10-21 21:04 ET: "Keep all, latest by default (Recommended)") (2026-10-21 21:10 ET)
- [x] How a year is identified (operator, 2026-10-21 21:05 ET: "Period end, 364–371 days (Recommended)") (2026-10-21 21:10 ET)
- [x] A changed fiscal year end: researched on the operator's instruction ("research how others do like factset or bloomberg ar data set"), measured on the cohort, then ruled (operator, 2026-10-21 21:08 ET: "Compustat-style, null if missing (Recommended)") (2026-10-21 21:10 ET)
- [x] Learning → skill: the new `skills/company-financials/SKILL.md`, "The time model" (operator, 2026-10-21: "New company-financials skill (Recommended)", after "this cannot be in a general skill be careful"); the general data-modeling skill is unchanged (2026-10-21 21:24 ET)

## Answer

1. **Every filed copy is kept; the latest is the default.** Silver keeps each filed figure, as of its period (start, end) and as at its filing (filed date, accession). Measures use the latest-filed copy by default, which keeps per-share series consistent across a split; the first-reported figure can be read back from the kept copies.
2. **A year is keyed on the period's end date.** A figure belongs to the fiscal year whose end falls in calendar year Y; the filing's `fy` and `fp` are never the key. A period is annual when it is 364–371 days long. CAGR counts years, not days, so a 53-week year keeps its extra week.
3. **A changed fiscal year end, Compustat-style.** A transition period is kept as filed but is not a year. When two annual periods end in one calendar year, that year is the later one (the new year end). A window that needs a year with no annual period gives null with the reason "fiscal year changed"; it never uses a nearby year.

### Research (2026-10-21)

- Compustat keys an annual record on FYEAR, set by the month the fiscal year ends (minus one for January–May); a short transition period is not a year. After a change two records can share an FYEAR, and researchers keep the one for the new year end ([WRDS, fiscal and calendar dates](https://wrds-support.wharton.upenn.edu/hc/en-us/articles/115003135371-Compustat-Identifying-Fiscal-and-Calendar-Dates); [GVKEY and FYEAR duplicates](https://robsonglasscock.wordpress.com/2018/04/12/gvkey-and-datadate-or-fyear-duplicates-in-compustat/); [removing duplicate GVKEY-DATADATE](http://kaichen.work/?p=387)).
- FactSet's and Bloomberg's manuals are behind logins; no public text on transition periods was found. Their usual practice (a stub column, growth "not meaningful", a separate calendarised view) is unverified. A calendarised view was offered and not chosen.

### Measured on the captured cohort (annual-length `NetIncomeLoss`, USD; counts only)

- 8 of 317 filers filed a transition report (10-KT): 20 short periods; 10 more 10-KT periods are annual length.
- 5 filers have two annual periods ending in one calendar year more than 14 days apart (6 years): a real change of year end.
- 47 filers have 284 missing years inside their span. Most are not a change of year end; ticket 38 (the concept lists per line item) should check how many a second concept fills.
