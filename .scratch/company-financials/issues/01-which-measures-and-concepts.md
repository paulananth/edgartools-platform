# 01 Which measures analysts use, and the reported concepts behind each

Type: research. Status: resolved. Blocked by: none. Map: [map](../map.md).

## Question

Which fundamental measures do analysts use most (growth: revenue, earnings, EPS, cash flow, book value CAGR; margins; returns; leverage; per-share), and for each, which reported XBRL concepts carry its inputs (us-gaap tags and their common variants, dei tags), with how often each variant appears? Evidence: primary sources (SEC Financial Statement Data Sets and company facts documentation, the us-gaap taxonomy, FASB), the old gold models `financial_facts.sql`, `financial_derived.sql`, `financial_factors.sql` as a record of past usage (git history), and edgartools' own standardisation if any. Also: CAGR definition choices that change results (fiscal vs calendar years, window ends, negative or zero bases, restatements).

## Answer

Research note: [research/01-measures-and-concepts.md](../research/01-measures-and-concepts.md) (2026-10-12 08:10 ET; primary sources and the 368 captured filers; no sec.gov data requests). In short:

- Annual series are built from each fact's start and end dates, never the filing's `fy`/`fp` (64% of annual net income facts carry a `fy` other than the year they end; over half of 10-K "FY" facts are quarters). Deduplicate on concept, unit, start, end; keep the latest filed; `frame` only as a cross-check.
- Values differ across filings for 152 of 307 filers (restatements, split-adjusted EPS, scale errors): the as-reported or restated choice is ticket 03.
- Nineteen standard line items in analyst-usage order, each with an ordered concept list chosen per company and period (section 6), with the chosen concept and accession recorded beside each value.
- Measure definitions from primary sources (section 4): CAGR `(end/start)^(1/years) - 1`; ROE on beginning equity; ROIC after tax on capital less cash; FCF = OCF - capex (non-GAAP).
- CAGR choices that change results (section 2): years keyed on the period end; exact N-year windows; a "not meaningful" reason where a base is zero or negative (net income CAGR for 128 of 307 filers, equity for 54 of 294); 52/53-week years counted as years.
- Nine hazards in the old code and edgartools that must not carry over (section 5): borrowing capacity as debt, liabilities-and-equity as liabilities, shares issued as outstanding, taxes paid as tax expense, the current portion of debt counted twice, ending equity in ROE, among others.
