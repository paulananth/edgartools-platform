# 07 Where CAGR and the other measures are computed, and their definitions

Priority: 39, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/07-where-cagr-and-measures-are-computed.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: resolved (2026-10-21 22:11 ET, operator rulings below). Blocked by: 38. Map: [map](../../company-financials/map.md).

## Question

Are CAGR, margins and ratios stored (silver or a gold layer) or computed when read (the agent `context` command or the analyst's query)? For each measure: its exact definition (window, year basis, what happens with a negative or missing base), and the test that proves it on the cohort against a hand-computed answer key.

From research section 2: the window and year basis, a "not meaningful" reason where a base is zero or negative (net income CAGR for 128 of 307 filers), 52/53-week years counted as years or annualised by days; section 4 gives each measure's formula from primary sources (ROE on beginning equity, ROIC after tax less cash).

## Checklist

- [x] Outside standards researched first (WRDS on Compustat, Damodaran, the Nasdaq growth convention): research 02 section 3 (2026-10-21 22:11 ET)
- [x] Stored or computed when read (operator, 2026-10-21: "Stored, built from silver (Recommended)") (2026-10-21 22:11 ET)
- [x] The denominator for a return (operator: "can we have both") (2026-10-21 22:11 ET)
- [x] CAGR windows (operator: "1, 3, 5 and 10 years (Recommended)") (2026-10-21 22:11 ET)
- [x] Learning → skill: `skills/company-financials/SKILL.md`, "Measures" (2026-10-21 22:11 ET)

## Answer

1. **Stored, built from silver.** A measures table holds one row per company, measure, fiscal year and window, built from the silver line items. Each row names its inputs (the line-item values, their concepts and accessions) and the measure definition's version. The definitions are rules configuration, like the line-item map; the table is rebuilt when silver changes. Ratios are raw, with no truncation or smoothing (as WRDS publishes firm-level ratios).
2. **Returns in both forms.** ROE, ROA and ROIC each carry two named measures: one on the average of the start and end balance (as WRDS does), one on the beginning balance (as Damodaran does). Either is null with a reason when a balance it needs is missing or its denominator is zero or negative.
3. **CAGR** = `(end / start)^(1/n) − 1` over exactly `n` annual years by period end (ticket 35), for windows of 1, 3, 5 and 10 years. It is "not meaningful" when the first or last value is zero or negative (the vendor convention), and null with the reason "missing year" or "fiscal year changed" when an endpoint year is missing; never a nearby year.
4. **Definitions** (research 01 section 4): margins on revenue (gross, operating, net); ROIC = operating income × (1 − tax rate) / (debt + parent equity − cash), the tax rate from income tax over pretax income; FCF = operating cash flow − capital expenditure (non-GAAP); per-share measures on the latest-filed, split-adjusted series; leverage and current ratio as research 01 lists them.
5. **The test:** each measure, and each of its null reasons, is proved on the cohort against ticket 44's hand-computed answer key: one test per measure and per reason.
