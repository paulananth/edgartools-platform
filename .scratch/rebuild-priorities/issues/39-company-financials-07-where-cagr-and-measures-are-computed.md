# 07 Where CAGR and the other measures are computed, and their definitions

Priority: 39, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/07-where-cagr-and-measures-are-computed.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: grilling. Status: open. Blocked by: 38. Map: [map](../../company-financials/map.md).

## Question

Are CAGR, margins and ratios stored (silver or a gold layer) or computed when read (the agent `context` command or the analyst's query)? For each measure: its exact definition (window, year basis, what happens with a negative or missing base), and the test that proves it on the cohort against a hand-computed answer key.

From research section 2: the window and year basis, a "not meaningful" reason where a base is zero or negative (net income CAGR for 128 of 307 filers), 52/53-week years counted as years or annualised by days; section 4 gives each measure's formula from primary sources (ROE on beginning equity, ROIC after tax less cash).
